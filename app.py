import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

# Configuration
st.set_page_config(
    page_title="Portfolio Analytics", layout="wide", initial_sidebar_state="collapsed"
)

# Style sobre et moderne sans fioritures
st.markdown(
    """
    <style>
        .block-container { padding-top: 2rem; padding-bottom: 2rem; }
        [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 600; }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; }
        .stTabs [data-baseweb="tab"] {
            padding: 8px 16px;
            border-radius: 6px;
            background-color: rgba(255, 255, 255, 0.03);
        }
    </style>
""",
    unsafe_allow_html=True,
)

DB_PATH = "portfolio.db"


def get_connection():
  conn = sqlite3.connect(DB_PATH, check_same_thread=False)
  conn.row_factory = sqlite3.Row
  return conn


def init_db():
  with get_connection() as conn:
    conn.executescript("""
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                currency TEXT DEFAULT 'EUR',
                sector TEXT
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                date TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                fees REAL DEFAULT 0.0,
                exchange_rate REAL DEFAULT 1.0,
                reason TEXT,
                notes TEXT,
                FOREIGN KEY (asset_id) REFERENCES assets(id)
            );
        """)


init_db()


def search_yahoo(query):
  if not query or len(query) < 2:
    return []
  url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=6&newsCount=0"
  try:
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
    data = res.json()
    items = []
    for q in data.get("quotes", []):
      if q.get("quoteType") in ["EQUITY", "ETF"]:
        items.append({
            "ticker": q.get("symbol"),
            "name": q.get("longname") or q.get("shortname") or q.get("symbol"),
            "sector": q.get("sector", "Industrie / Services"),
        })
    return items
  except Exception:
    return []


def fetch_live_quotes(tickers):
  quotes = {}
  for t in tickers:
    try:
      tk = yf.Ticker(t)
      info = tk.info
      price = (
          info.get("currentPrice")
          or info.get("regularMarketPrice")
          or info.get("previousClose")
          or 0.0
      )
      quotes[t] = {
          "price": float(price),
          "pe": info.get("trailingPE"),
          "yield": (info.get("dividendYield") or 0.0) * 100,
          "sector": info.get("sector") or "Non classé",
      }
    except Exception:
      quotes[t] = {"price": 0.0, "pe": None, "yield": 0.0, "sector": "Non classé"}
  return quotes


def get_portfolio_data():
  with get_connection() as conn:
    df_tx = pd.read_sql_query(
        """
            SELECT t.id, t.type, t.date, t.quantity, t.price, t.fees, t.exchange_rate, 
                   t.reason, t.notes, a.ticker, a.name, a.sector
            FROM transactions t
            JOIN assets a ON t.asset_id = a.id
            ORDER BY t.date ASC, t.id ASC
        """,
        conn,
    )

  if df_tx.empty:
    return pd.DataFrame(), pd.DataFrame()

  positions = {}
  for _, tx in df_tx.iterrows():
    tk = tx["ticker"]
    if tk not in positions:
      positions[tk] = {
          "ticker": tk,
          "name": tx["name"],
          "sector": tx["sector"],
          "quantity": 0.0,
          "total_cost": 0.0,
          "realized_pnl": 0.0,
      }

    pos = positions[tk]
    q, p, f = float(tx["quantity"]), float(tx["price"]), float(tx["fees"])

    if tx["type"] == "BUY":
      pos["total_cost"] += (q * p) + f
      pos["quantity"] += q
    elif tx["type"] == "SELL":
      if pos["quantity"] > 0:
        avg_cost = pos["total_cost"] / pos["quantity"]
        pos["realized_pnl"] += (p - avg_cost) * q - f
        pos["quantity"] -= q
        pos["total_cost"] = max(0.0, pos["quantity"] * avg_cost)

  active = [p for p in positions.values() if p["quantity"] > 0.0001]
  if not active:
    return pd.DataFrame(), df_tx

  df_pos = pd.DataFrame(active)
  live = fetch_live_quotes(df_pos["ticker"].tolist())

  df_pos["pru"] = df_pos["total_cost"] / df_pos["quantity"]
  df_pos["current_price"] = df_pos["ticker"].map(
      lambda x: live.get(x, {}).get("price", 0.0)
  )
  df_pos["pe"] = df_pos["ticker"].map(lambda x: live.get(x, {}).get("pe"))
  df_pos["div_yield"] = df_pos["ticker"].map(
      lambda x: live.get(x, {}).get("yield", 0.0)
  )

  df_pos["valuation"] = df_pos["quantity"] * df_pos["current_price"]
  df_pos["unrealized_pnl"] = df_pos["valuation"] - df_pos["total_cost"]
  df_pos["unrealized_pnl_pct"] = (
      df_pos["unrealized_pnl"] / df_pos["total_cost"]
  ) * 100

  tot_val = df_pos["valuation"].sum()
  df_pos["weight"] = (df_pos["valuation"] / tot_val * 100) if tot_val > 0 else 0.0

  return df_pos, df_tx


# Navigation
tab_overview, tab_holdings, tab_analytics = st.tabs(
    ["Vue d'ensemble", "Portefeuille & Saisie", "Historique & Performance"]
)
df_positions, df_transactions = get_portfolio_data()

# ----------------------------------------------------
# ONGLET 1 : VUE D'ENSEMBLE
# ----------------------------------------------------
with tab_overview:
  if df_positions.empty:
    st.info(
        "Portefeuille inactif. Ajoutez une transaction dans l'onglet"
        " Portefeuille pour activer les métriques."
    )
  else:
    cost_basis = df_positions["total_cost"].sum()
    current_val = df_positions["valuation"].sum()
    unrealized = current_val - cost_basis
    unrealized_pct = (unrealized / cost_basis * 100) if cost_basis > 0 else 0.0
    weighted_yield = (
        (df_positions["valuation"] * df_positions["div_yield"]).sum()
        / current_val
        if current_val > 0
        else 0.0
    )

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Valorisation globale", f"{current_val:,.2f} €")
    kpi2.metric(
        "Plus/Moins-value latente",
        f"{unrealized:+,.2f} €",
        delta=f"{unrealized_pct:+.2f} %",
    )
    kpi3.metric("Capital net investi", f"{cost_basis:,.2f} €")
    kpi4.metric("Rendement dividende moyen", f"{weighted_yield:.2f} %")

    st.write("")
    g1, g2 = st.columns(2)

    with g1:
      fig_donut = px.pie(
          df_positions,
          values="valuation",
          names="name",
          hole=0.55,
          title="Exposition par actif",
          color_discrete_sequence=px.colors.sequential.Teal,
      )
      fig_donut.update_layout(
          margin=dict(t=40, b=10, l=10, r=10), showlegend=True
      )
      st.plotly_chart(fig_donut, use_container_width=True)

    with g2:
      fig_sec = px.pie(
          df_positions,
          values="valuation",
          names="sector",
          hole=0.55,
          title="Exposition sectorielle",
          color_discrete_sequence=px.colors.sequential.Blues_r,
      )
      fig_sec.update_layout(
          margin=dict(t=40, b=10, l=10, r=10), showlegend=True
      )
      st.plotly_chart(fig_sec, use_container_width=True)

# ----------------------------------------------------
# ONGLET 2 : PORTEFEUILLE & TRANSACTION
# ----------------------------------------------------
with tab_holdings:
  col_saisie, col_table = st.columns([1, 2], gap="large")

  with col_saisie:
    st.subheader("Enregistrer une opération")

    search_input = st.text_input(
        "Rechercher un actif",
        placeholder="Tapez le nom ou ticker (ex: Eiffage, ALO.PA)...",
    )
    search_results = search_yahoo(search_input)

    selected_asset = None
    if search_results:
      options = {
          f"{item['name']} ({item['ticker']})": item for item in search_results
      }
      picked_label = st.selectbox("Sélectionner la valeur :", list(options.keys()))
      selected_asset = options[picked_label]

    with st.form("tx_entry_form", clear_on_submit=True):
      op_type = st.selectbox(
          "Type d'ordre", ["Achat (BUY)", "Vente (SELL)", "Dividende (DIVIDEND)"]
      )
      op_date = st.date_input("Date d'exécution", value=datetime.today())

      c_q, c_p = st.columns(2)
      quantity = c_q.number_input(
          "Quantité", min_value=0.0001, value=1.0, step=1.0
      )
      price = c_p.number_input(
          "Prix d'exécution (€)", min_value=0.0001, value=100.0, step=0.1
      )

      c_f, c_fx = st.columns(2)
      fees = c_f.number_input("Frais d'ordre (€)", min_value=0.0, value=0.0)
      fx_rate = c_fx.number_input(
          "Taux de change (si hors EUR)", min_value=0.0001, value=1.0
      )

      reason = st.text_input(
          "Motif d'arbitrage",
          placeholder="Ex: Valorisation attractive, renforcement...",
      )
      notes = st.text_area(
          "Thèse d'investissement / Détails fondamentaux",
          placeholder="PER cible, catalyseurs opérationnels, free cash flow...",
      )

      submit = st.form_submit_button(
          "Enregistrer l'opération", use_container_width=True
      )

      if submit:
        if not selected_asset:
          st.error(
              "Veuillez rechercher et sélectionner une action valide avant de"
              " valider."
          )
        else:
          type_code = "BUY" if "Achat" in op_type else (
              "SELL" if "Vente" in op_type else "DIVIDEND"
          )
          with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                            INSERT INTO assets (ticker, name, sector)
                            VALUES (?, ?, ?)
                            ON CONFLICT(ticker) DO UPDATE SET name=excluded.name, sector=excluded.sector
                        """,
                (
                    selected_asset["ticker"],
                    selected_asset["name"],
                    selected_asset["sector"],
                ),
            )

            cur.execute(
                "SELECT id FROM assets WHERE ticker = ?",
                (selected_asset["ticker"],),
            )
            asset_id = cur.fetchone()[0]

            cur.execute(
                """
                            INSERT INTO transactions (asset_id, type, date, quantity, price, fees, exchange_rate, reason, notes)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                (
                    asset_id,
                    type_code,
                    op_date.strftime("%Y-%m-%d"),
                    quantity,
                    price,
                    fees,
                    fx_rate,
                    reason,
                    notes,
                ),
            )
            conn.commit()

          st.success(f"Ordre enregistré pour {selected_asset['name']}.")
          st.rerun()

  with col_table:
    st.subheader("Positions ouvertes")
    if df_positions.empty:
      st.write("Aucune position active.")
    else:
      view_df = df_positions[[
          "ticker",
          "name",
          "quantity",
          "pru",
          "current_price",
          "valuation",
          "unrealized_pnl",
          "unrealized_pnl_pct",
          "weight",
      ]].rename(
          columns={
              "ticker": "Ticker",
              "name": "Actif",
              "quantity": "Quantité",
              "pru": "PRU",
              "current_price": "Dernier cours",
              "valuation": "Valorisation",
              "unrealized_pnl": "P&L (€)",
              "unrealized_pnl_pct": "P&L (%)",
              "weight": "Poids",
          }
      )

      st.dataframe(
          view_df.style.format({
              "Quantité": "{:.2f}",
              "PRU": "{:.2f} €",
              "Dernier cours": "{:.2f} €",
              "Valorisation": "{:,.2f} €",
              "P&L (€)": "{:+,.2f} €",
              "P&L (%)": "{:+.2f} %",
              "Poids": "{:.1f} %",
          }),
          use_container_width=True,
          hide_index=True,
      )

# ----------------------------------------------------
# ONGLET 3 : HISTORIQUE & JOURNAL
# ----------------------------------------------------
with tab_analytics:
  if df_transactions.empty:
    st.write("Aucune transaction enregistrée.")
  else:
    st.subheader("Journal des opérations")
    journal = df_transactions[[
        "date",
        "type",
        "name",
        "ticker",
        "quantity",
        "price",
        "fees",
        "reason",
        "notes",
    ]].rename(
        columns={
            "date": "Date",
            "type": "Sens",
            "name": "Actif",
            "ticker": "Ticker",
            "quantity": "Quantité",
            "price": "Prix unitaire",
            "fees": "Frais",
            "reason": "Motif",
            "notes": "Thèse / Ratios",
        }
    )
    st.dataframe(
        journal.sort_values("Date", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
