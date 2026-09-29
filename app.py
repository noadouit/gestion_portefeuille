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
    page_title="Terminal Financier & Portefeuille",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Style sombre, typographie épurée type terminal Bloomberg / Morning Brief
st.markdown(
    """
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }
        .market-ticker-box {
            background-color: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 8px;
            padding: 10px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .market-ticker-title { font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; font-weight: 600; letter-spacing: 0.05em; }
        .market-ticker-val { font-size: 1.15rem; font-weight: 700; color: #f8fafc; }
        .news-card {
            background-color: #0f172a;
            border-left: 3px solid #3b82f6;
            border-radius: 4px;
            padding: 12px 16px;
            margin-bottom: 10px;
        }
        [data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
        .stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid #1e293b; }
        .stTabs [data-baseweb="tab"] {
            padding: 8px 18px;
            border-radius: 6px 6px 0 0;
            background-color: transparent;
            font-size: 0.9rem;
            font-weight: 500;
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


@st.cache_data(ttl=900)
def get_market_indices():
  """Récupère les cours des indices de référence pour le bandeau supérieur."""
  indices = {"^FCHI": "CAC 40", "^GSPC": "S&P 500", "^TNX": "US 10Y (Yield)"}
  out = {}
  for symbol, name in indices.items():
    try:
      tk = yf.Ticker(symbol)
      hist = tk.history(period="5d")
      if len(hist) >= 2:
        close = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2]
        chg = ((close - prev) / prev) * 100
        out[name] = {"price": close, "change": chg}
      else:
        out[name] = {"price": 0.0, "change": 0.0}
    except Exception:
      out[name] = {"price": 0.0, "change": 0.0}
  return out


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
          "day_change": info.get("regularMarketChangePercent", 0.0),
      }
    except Exception:
      quotes[t] = {
          "price": 0.0,
          "pe": None,
          "yield": 0.0,
          "sector": "Non classé",
          "day_change": 0.0,
      }
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
  df_pos["day_change"] = df_pos["ticker"].map(
      lambda x: live.get(x, {}).get("day_change", 0.0)
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


df_positions, df_transactions = get_portfolio_data()

# ----------------------------------------------------
# NAVIGATION PAR ONGLETS
# ----------------------------------------------------
tab_brief, tab_holdings, tab_analytics, tab_journal = st.tabs([
    "Journal & Marchés",
    "Portefeuille & Saisie",
    "Performance & Allocation",
    "Historique des opérations",
])

# ====================================================
# ONGLET 1 : JOURNAL & MARCHÉS (ACCUEIL)
# ====================================================
with tab_brief:
  # Bandeau Indices Macro
  indices_data = get_market_indices()
  col_i1, col_i2, col_i3, col_date = st.columns([1, 1, 1, 1.2])

  for col, (idx_name, vals) in zip(
      [col_i1, col_i2, col_i3], indices_data.items()
  ):
    with col:
      color = (
          "#10b981"
          if vals["change"] >= 0
          else ("#ef4444" if vals["change"] < 0 else "#94a3b8")
      )
      prefix = "+" if vals["change"] > 0 else ""
      st.markdown(
          f"""
                <div class="market-ticker-box">
                    <div>
                        <div class="market-ticker-title">{idx_name}</div>
                        <div class="market-ticker-val">{vals['price']:,.2f}</div>
                    </div>
                    <div style="font-weight:700; color:{color};">{prefix}{vals['change']:.2f}%</div>
                </div>
            """,
          unsafe_allow_html=True,
      )

  with col_date:
    st.markdown(
        f"""
            <div class="market-ticker-box" style="justify-content: center; text-align: center;">
                <div>
                    <div class="market-ticker-title">Date de séance</div>
                    <div class="market-ticker-val" style="font-size: 1rem;">{datetime.now().strftime('%d %B %Y')}</div>
                </div>
            </div>
        """,
        unsafe_allow_html=True,
    )

  st.write("")

  # Synthèse Portefeuille
  if df_positions.empty:
    st.info(
        "Édition du jour : Portefeuille en attente de premières lignes. Ajoutez"
        " vos positions dans l'onglet 'Portefeuille & Saisie'."
    )
  else:
    cost_basis = df_positions["total_cost"].sum()
    current_val = df_positions["valuation"].sum()
    unrealized = current_val - cost_basis
    unrealized_pct = (unrealized / cost_basis * 100) if cost_basis > 0 else 0.0

    st.subheader("Synthèse de gestion")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Actif Net Réévalué", f"{current_val:,.2f} €")
    k2.metric(
        "Performance Globale",
        f"{unrealized:+,.2f} €",
        delta=f"{unrealized_pct:+.2f} %",
    )
    k3.metric("Capital Engagé", f"{cost_basis:,.2f} €")
    k4.metric(
        "Diversification",
        f"{len(df_positions)} lignes",
        f"{df_positions['sector'].nunique()} secteurs",
    )

    st.divider()

    # Colonnes style Morning Paper : Faits marquants et Movers
    c_left, c_right = st.columns([1.2, 1])

    with c_left:
      st.markdown("### Focus Valeurs : Derniers Mouvements")
      best_pos = df_positions.sort_values(
          "unrealized_pnl_pct", ascending=False
      ).iloc[0]
      worst_pos = df_positions.sort_values(
          "unrealized_pnl_pct", ascending=True
      ).iloc[0]

      st.markdown(
          f"""
                <div class="news-card" style="border-left-color: #10b981;">
                    <strong style="color: #10b981;">Surperformance :</strong> {best_pos['name']} ({best_pos['ticker']})
                    <p style="margin: 4px 0 0 0; font-size: 0.88rem; color: #cbd5e1;">
                        Plus-value latente de <b>{best_pos['unrealized_pnl_pct']:+.2f}%</b> ({best_pos['unrealized_pnl']:+,.2f} €). Poids dans le portefeuille : {best_pos['weight']:.1f}%.
                    </p>
                </div>
                <div class="news-card" style="border-left-color: {'#ef4444' if worst_pos['unrealized_pnl_pct'] < 0 else '#3b82f6'};">
                    <strong style="color: {'#ef4444' if worst_pos['unrealized_pnl_pct'] < 0 else '#3b82f6'};">Point d'attention :</strong> {worst_pos['name']} ({worst_pos['ticker']})
                    <p style="margin: 4px 0 0 0; font-size: 0.88rem; color: #cbd5e1;">
                        Performance actuelle de <b>{worst_pos['unrealized_pnl_pct']:+.2f}%</b> ({worst_pos['unrealized_pnl']:+,.2f} €). PRU : {worst_pos['pru']:.2f} € vs Dernier cours : {worst_pos['current_price']:.2f} €.
                    </p>
                </div>
            """,
          unsafe_allow_html=True,
      )

      st.markdown("### Carnet d'Arbitrage Récent")
      recent_tx = df_transactions.sort_values("date", ascending=False).head(3)
      for _, tx in recent_tx.iterrows():
        st.markdown(
            f"""
                    <div style="padding: 8px 12px; border-bottom: 1px solid #1e293b; font-size: 0.88rem;">
                        <span style="color: {'#10b981' if tx['type'] == 'BUY' else '#ef4444'}; font-weight: 700;">[{tx['type']}]</span> 
                        <b>{tx['date']}</b> - {tx['name']} ({tx['quantity']} titres @ {tx['price']:.2f} €)
                        <div style="color: #94a3b8; font-style: italic; margin-top: 2px;">Motif : {tx['reason'] or 'Non spécifié'}</div>
                    </div>
                """,
            unsafe_allow_html=True,
        )

    with c_right:
      st.markdown("### Valorisations Relatives (P/E Ratio)")
      pe_df = (
          df_positions.dropna(subset=["pe"])[["name", "pe"]]
          .sort_values("pe")
          .copy()
      )
      if not pe_df.empty:
        fig_pe = px.bar(
            pe_df,
            x="pe",
            y="name",
            orientation="h",
            labels={"pe": "Multiple de résultat (P/E)", "name": ""},
            color_discrete_sequence=["#3b82f6"],
        )
        fig_pe.update_layout(
            margin=dict(t=10, b=10, l=10, r=10),
            height=280,
            xaxis=dict(gridcolor="#1e293b"),
            yaxis=dict(gridcolor="#1e293b"),
        )
        st.plotly_chart(fig_pe, use_container_width=True)
      else:
        st.caption("Données de multiples indisponibles sur les lignes actives.")

# ====================================================
# ONGLET 2 : PORTEFEUILLE & SAISIE D'ORDRES
# ====================================================
with tab_holdings:
  col_saisie, col_table = st.columns([1, 2], gap="large")

  with col_saisie:
    st.subheader("Enregistrer un ordre")

    search_input = st.text_input(
        "Recherche de titre (Yahoo Finance)",
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
          "Sens de l'opération",
          ["Achat (BUY)", "Vente (SELL)", "Dividende (DIVIDEND)"],
      )
      op_date = st.date_input("Date d'exécution", value=datetime.today())

      c_q, c_p = st.columns(2)
      quantity = c_q.number_input(
          "Quantité", min_value=0.0001, value=1.0, step=1.0
      )
      price = c_p.number_input(
          "Prix unitaire (€)", min_value=0.0001, value=100.0, step=0.1
      )

      c_f, c_fx = st.columns(2)
      fees = c_f.number_input("Frais (€)", min_value=0.0, value=0.0)
      fx_rate = c_fx.number_input("Taux de change", min_value=0.0001, value=1.0)

      reason = st.text_input(
          "Motif d'arbitrage",
          placeholder="Ex: Décote sur NAV, repli technique...",
      )
      notes = st.text_area(
          "Thèse d'investissement & Ratios",
          placeholder=(
              "Ex: PER d'entrée 8.5x, FCF yield estimé > 7%, catalyseur plan de"
              " cession..."
          ),
      )

      submit = st.form_submit_button(
          "Exécuter & Enregistrer", use_container_width=True
      )

      if submit:
        if not selected_asset:
          st.error("Veuillez rechercher et sélectionner une action valide.")
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

          st.success(f"Ordre validé pour {selected_asset['name']}.")
          st.rerun()

  with col_table:
    st.subheader("Positions Actives")
    if df_positions.empty:
      st.write("Aucune ligne en portefeuille actuellement.")
    else:
      view_df = df_positions[[
          "ticker",
          "name",
          "sector",
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
              "sector": "Secteur",
              "quantity": "Quantité",
              "pru": "PRU",
              "current_price": "Cours",
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
              "Cours": "{:.2f} €",
              "Valorisation": "{:,.2f} €",
              "P&L (€)": "{:+,.2f} €",
              "P&L (%)": "{:+.2f} %",
              "Poids": "{:.1f} %",
          }),
          use_container_width=True,
          hide_index=True,
      )

# ====================================================
# ONGLET 3 : PERFORMANCE & ALLOCATION
# ====================================================
with tab_analytics:
  if df_transactions.empty:
    st.info("Aucune donnée disponible pour le calcul de performance.")
  else:
    # 1. Courbe interactive d'évolution du portefeuille
    st.subheader("Évolution Temporelle du Portefeuille")

    min_date = pd.to_datetime(df_transactions["date"].min()) - timedelta(
        days=2
    )
    all_tickers = df_transactions["ticker"].unique().tolist()

    with st.spinner("Reconstitution historique des cours..."):
      hist_data = yf.download(all_tickers, start=min_date, progress=False)[
          "Close"
      ]
      if isinstance(hist_data, pd.Series):
        hist_data = hist_data.to_frame(name=all_tickers[0])
      hist_data = hist_data.ffill().bfill()

      timeline = []
      for dt in hist_data.index:
        sub_tx = df_transactions[pd.to_datetime(df_transactions["date"]) <= dt]
        invested = 0.0
        portfolio_val = 0.0

        for tk in all_tickers:
          tk_tx = sub_tx[sub_tx["ticker"] == tk]
          q_buy = tk_tx[tk_tx["type"] == "BUY"]["quantity"].sum()
          q_sell = tk_tx[tk_tx["type"] == "SELL"]["quantity"].sum()
          net_q = max(0.0, q_buy - q_sell)

          c_buy = (
              tk_tx[tk_tx["type"] == "BUY"]["quantity"]
              * tk_tx[tk_tx["type"] == "BUY"]["price"]
          ).sum()
          c_sell = (
              tk_tx[tk_tx["type"] == "SELL"]["quantity"]
              * tk_tx[tk_tx["type"] == "SELL"]["price"]
          ).sum()
          invested += max(0.0, c_buy - c_sell)

          if net_q > 0 and tk in hist_data.columns:
            px_val = hist_data.loc[dt, tk]
            if pd.notnull(px_val):
              portfolio_val += net_q * float(px_val)

        timeline.append({
            "Date": dt,
            "Valorisation (€)": portfolio_val,
            "Capital Engagé (€)": invested,
        })

      df_evo = pd.DataFrame(timeline)

      fig_evo = go.Figure()
      fig_evo.add_trace(
          go.Scatter(
              x=df_evo["Date"],
              y=df_evo["Valorisation (€)"],
              name="Valorisation",
              line=dict(color="#3b82f6", width=2.5),
              fill="tozeroy",
              fillcolor="rgba(59, 130, 246, 0.08)",
          )
      )
      fig_evo.add_trace(
          go.Scatter(
              x=df_evo["Date"],
              y=df_evo["Capital Engagé (€)"],
              name="Capital Engagé",
              line=dict(color="#64748b", width=1.8, dash="dot"),
          )
      )
      fig_evo.update_layout(
          hovermode="x unified",
          margin=dict(t=20, b=20, l=10, r=10),
          xaxis=dict(gridcolor="#1e293b"),
          yaxis=dict(gridcolor="#1e293b", title="Euros (€)"),
          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
      )
      st.plotly_chart(fig_evo, use_container_width=True)

    st.divider()

    # 2. Répartition et P&L
    c_pie1, c_pie2 = st.columns(2)

    with c_pie1:
      st.subheader("Allocation par Actif")
      if not df_positions.empty:
        fig_donut_act = px.pie(
            df_positions,
            values="valuation",
            names="name",
            hole=0.55,
            color_discrete_sequence=px.colors.sequential.Teal,
        )
        fig_donut_act.update_layout(
            margin=dict(t=30, b=10, l=10, r=10), showlegend=True
        )
        st.plotly_chart(fig_donut_act, use_container_width=True)

    with c_pie2:
      st.subheader("Allocation Sectorielle")
      if not df_positions.empty:
        fig_donut_sec = px.pie(
            df_positions,
            values="valuation",
            names="sector",
            hole=0.55,
            color_discrete_sequence=px.colors.sequential.Blues_r,
        )
        fig_donut_sec.update_layout(
            margin=dict(t=30, b=10, l=10, r=10), showlegend=True
        )
        st.plotly_chart(fig_donut_sec, use_container_width=True)

    if not df_positions.empty:
      st.subheader("Contribution à la Performance Latente (%)")
      sorted_pnl = df_positions.sort_values(
          "unrealized_pnl_pct", ascending=True
      )
      fig_bars = px.bar(
          sorted_pnl,
          x="unrealized_pnl_pct",
          y="name",
          orientation="h",
          color="unrealized_pnl_pct",
          color_continuous_scale=["#ef4444", "#334155", "#10b981"],
          color_continuous_midpoint=0,
          labels={"unrealized_pnl_pct": "+/- Value Latente (%)", "name": ""},
      )
      fig_bars.update_layout(
          margin=dict(t=10, b=10, l=10, r=10),
          xaxis=dict(gridcolor="#1e293b"),
          yaxis=dict(gridcolor="#1e293b"),
          coloraxis_showscale=False,
      )
      st.plotly_chart(fig_bars, use_container_width=True)

# ====================================================
# ONGLET 4 : HISTORIQUE DES OPÉRATIONS
# ====================================================
with tab_journal:
  st.subheader("Journal Central des Transactions")
  if df_transactions.empty:
    st.write("Aucune opération enregistrée.")
  else:
    journal_view = df_transactions[[
        "date",
        "type",
        "ticker",
        "name",
        "quantity",
        "price",
        "fees",
        "reason",
        "notes",
    ]].rename(
        columns={
            "date": "Date",
            "type": "Ordre",
            "ticker": "Ticker",
            "name": "Valeur",
            "quantity": "Quantité",
            "price": "Prix Unitaire (€)",
            "fees": "Frais (€)",
            "reason": "Motif",
            "notes": "Thèse & Ratios",
        }
    )

    st.dataframe(
        journal_view.sort_values("Date", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
