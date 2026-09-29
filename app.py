import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

# ==========================================
# CONFIGURATION DE LA PAGE & STYLE
# ==========================================
st.set_page_config(
    page_title="Gestion de Portefeuille",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==========================================
# INITIALISATION & CONNEXION BDD
# ==========================================
DB_PATH = "portfolio.db"


def get_connection():
  return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
  conn = get_connection()
  conn.executescript("""
    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        isin TEXT,
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
  conn.commit()
  conn.close()


init_db()

# ==========================================
# FONCTIONS API YAHOO FINANCE
# ==========================================


@st.cache_data(ttl=3600)
def search_yahoo_tickers(query):
  """Recherche auto-complétée d'actions via l'API Yahoo Finance."""
  if not query or len(query) < 2:
    return []
  url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=8&newsCount=0"
  headers = {"User-Agent": "Mozilla/5.0"}
  try:
    r = requests.get(url, headers=headers, timeout=5)
    data = r.json()
    results = []
    for q in data.get("quotes", []):
      if q.get("quoteType") in ["EQUITY", "ETF"]:
        symbol = q.get("symbol")
        name = q.get("longname") or q.get("shortname") or symbol
        exch = q.get("exchDisp", "")
        sector = q.get("sector", "Non renseigné")
        results.append({
            "label": f"{name} ({symbol} - {exch})",
            "symbol": symbol,
            "name": name,
            "sector": sector,
        })
    return results
  except Exception:
    return []


@st.cache_data(ttl=900)
def get_live_market_data(tickers):
  """Récupère les cours actuels et les ratios fondamentaux (PER, Dividende, etc.)."""
  data = {}
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
      data[t] = {
          "price": float(price),
          "currency": info.get("currency", "EUR"),
          "sector": info.get("sector") or "Autre",
          "pe": info.get("trailingPE", None),
          "forward_pe": info.get("forwardPE", None),
          "div_yield": (info.get("dividendYield") or 0.0) * 100,
          "day_change": info.get("regularMarketChangePercent", 0.0),
      }
    except Exception:
      data[t] = {
          "price": 0.0,
          "currency": "EUR",
          "sector": "Autre",
          "pe": None,
          "forward_pe": None,
          "div_yield": 0.0,
          "day_change": 0.0,
      }
  return data


# ==========================================
# CALCULS DU PORTEFEUILLE
# ==========================================


def load_portfolio_summary():
  conn = get_connection()
  df_tx = pd.read_sql_query(
      """
        SELECT t.*, a.ticker, a.name, a.sector, a.currency 
        FROM transactions t
        JOIN assets a ON t.asset_id = a.id
        ORDER BY t.date ASC
    """,
      conn,
  )
  conn.close()

  if df_tx.empty:
    return pd.DataFrame(), pd.DataFrame()

  positions = {}
  for _, row in df_tx.iterrows():
    tk = row["ticker"]
    if tk not in positions:
      positions[tk] = {
          "ticker": tk,
          "name": row["name"],
          "sector": row["sector"],
          "currency": row["currency"],
          "qty": 0.0,
          "total_cost": 0.0,
          "dividends": 0.0,
      }
    p = positions[tk]
    if row["type"] == "BUY":
      cost = (row["quantity"] * row["price"] + row["fees"]) * row[
          "exchange_rate"
      ]
      p["total_cost"] += cost
      p["qty"] += row["quantity"]
    elif row["type"] == "SELL":
      if p["qty"] > 0:
        pru_actuel = p["total_cost"] / p["qty"]
        p["qty"] -= row["quantity"]
        p["total_cost"] = max(0.0, p["qty"] * pru_actuel)
    elif row["type"] == "DIVIDEND":
      p["dividends"] += (row["quantity"] * row["price"] - row["fees"]) * row[
          "exchange_rate"
      ]

  # Filtrer les positions actives
  active_pos = [v for v in positions.values() if v["qty"] > 0.0001]
  if not active_pos:
    return pd.DataFrame(), df_tx

  df_pos = pd.DataFrame(active_pos)
  market_data = get_live_market_data(df_pos["ticker"].tolist())

  df_pos["PRU (€)"] = df_pos["total_cost"] / df_pos["qty"]
  df_pos["Cours Actuel"] = df_pos["ticker"].map(lambda x: market_data[x]["price"])
  df_pos["Var. Jour (%)"] = df_pos["ticker"].map(
      lambda x: market_data[x]["day_change"]
  )
  df_pos["PER"] = df_pos["ticker"].map(lambda x: market_data[x]["pe"])
  df_pos["Rendement (%)"] = df_pos["ticker"].map(
      lambda x: market_data[x]["div_yield"]
  )

  df_pos["Valorisation (€)"] = df_pos["qty"] * df_pos["Cours Actuel"]
  df_pos["+/- Value Latente (€)"] = (
      df_pos["Valorisation (€)"] - df_pos["total_cost"]
  )
  df_pos["+/- Value (%)"] = (
      df_pos["+/- Value Latente (€)"] / df_pos["total_cost"]
  ) * 100

  total_val = df_pos["Valorisation (€)"].sum()
  df_pos["Poids (%)"] = (
      (df_pos["Valorisation (€)"] / total_val * 100) if total_val > 0 else 0.0
  )

  return df_pos, df_tx


# ==========================================
# INTERFACE PRINCIPALE
# ==========================================

st.title("📊 Terminal de Gestion de Portefeuille")

df_pos, df_tx = load_portfolio_summary()

tab_home, tab_portfolio, tab_perf = st.tabs([
    "🏠 Accueil & Vue d'ensemble",
    "💼 Portefeuille & Ordres",
    "📈 Performance & Journal",
])

# ------------------------------------------
# ONGLET 1 : ACCUEIL
# ------------------------------------------
with tab_home:
  if df_pos.empty:
    st.info(
        "👋 Bienvenue sur ton espace ! Ton portefeuille est vide pour"
        " l'instant. Rendez-vous dans l'onglet **💼 Portefeuille & Ordres**"
        " pour ajouter ta première ligne."
    )
  else:
    total_investi = df_pos["total_cost"].sum()
    total_valo = df_pos["Valorisation (€)"].sum()
    pv_latente = total_valo - total_investi
    pv_pct = (pv_latente / total_investi * 100) if total_investi > 0 else 0.0
    total_div = df_pos["dividends"].sum()
    rendement_moyen = (
        df_pos["Valorisation (€)"] * df_pos["Rendement (%)"]
    ).sum() / total_valo

    # Bandeau de KPIs
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "💰 Valorisation Totale",
        f"{total_valo:,.2f} €",
        f"{pv_latente:+,.2f} €",
    )
    col2.metric(
        "📈 Performance Latente",
        f"{pv_pct:+.2f} %",
        f"Investi : {total_investi:,.2f} €",
    )
    col3.metric(
        "🎁 Dividendes Perçus",
        f"{total_div:,.2f} €",
        f"Rdt estimé : {rendement_moyen:.2f} %/an",
    )
    col4.metric(
        "🏢 Lignes en Portefeuille",
        f"{len(df_pos)} valeurs",
        f"{df_pos['sector'].nunique()} secteurs",
    )

    st.divider()

    # Graphiques de répartition
    c_left, c_right = st.columns(2)
    with c_left:
      st.subheader("Répartition par Valeur")
      fig_val = px.pie(
          df_pos,
          values="Valorisation (€)",
          names="name",
          hole=0.45,
          color_discrete_sequence=px.colors.qualitative.Prism,
      )
      fig_val.update_traces(textposition="inside", textinfo="percent+label")
      st.plotly_chart(fig_val, use_container_width=True)

    with c_right:
      st.subheader("Allocation Sectorielle")
      fig_sec = px.pie(
          df_pos,
          values="Valorisation (€)",
          names="sector",
          hole=0.45,
          color_discrete_sequence=px.colors.qualitative.Safe,
      )
      fig_sec.update_traces(textposition="inside", textinfo="percent+label")
      st.plotly_chart(fig_sec, use_container_width=True)

    # Radar Fondamental Value
    st.subheader("🔍 Radar Fondamental des Lignes (Temps réel Yahoo Finance)")
    df_fund = df_pos[[
        "name",
        "ticker",
        "sector",
        "Cours Actuel",
        "PER",
        "Rendement (%)",
        "Poids (%)",
    ]].copy()
    st.dataframe(
        df_fund.style.format({
            "Cours Actuel": "{:.2f} €",
            "PER": lambda x: f"{x:.1f}x" if pd.notnull(x) else "N/A",
            "Rendement (%)": "{:.2f} %",
            "Poids (%)": "{:.1f} %",
        }),
        use_container_width=True,
        hide_index=True,
    )

# ------------------------------------------
# ONGLET 2 : PORTEFEUILLE & AJOUT D'ORDRES
# ------------------------------------------
with tab_portfolio:
  col_form, col_table = st.columns([1, 2])

  with col_form:
    st.subheader("➕ Enregistrer un mouvement")

    # 1. Barre de recherche intelligente hors formulaire pour auto-complétion directe
    search_query = st.text_input(
        "🔎 Rechercher une action (ex: Eiffage, Alstom, Viel, Sanofi...)"
    )
    suggestions = search_yahoo_tickers(search_query)

    selected_stock = None
    if suggestions:
      labels = [s["label"] for s in suggestions]
      choice = st.selectbox("Valeurs proposées :", labels)
      selected_stock = next(s for s in suggestions if s["label"] == choice)

    # 2. Formulaire de transaction
    with st.form("add_tx_form", clear_on_submit=True):
      tx_type = st.selectbox(
          "Type d'opération",
          ["BUY", "SELL", "DIVIDEND"],
          format_func=lambda x: {
              "BUY": "🟢 Achat",
              "SELL": "🔴 Vente",
              "DIVIDEND": "🎁 Dividende",
          }[x],
      )
      tx_date = st.date_input("Date de l'ordre", value=datetime.today())

      c1, c2 = st.columns(2)
      qty = c1.number_input("Quantité", min_value=0.0001, value=1.0, step=1.0)
      price = c2.number_input(
          "Prix unitaire (€)", min_value=0.0001, value=100.0, step=0.5
      )

      c3, c4 = st.columns(2)
      fees = c3.number_input(
          "Frais de courtage (€)", min_value=0.0, value=0.0, step=0.5
      )
      fx = c4.number_input(
          "Taux de change (1 si EUR)", min_value=0.0001, value=1.0
      )

      reason = st.selectbox(
          "Motif principal",
          [
              "Ouverture de ligne (Value / Décote)",
              "Renforcement sur repli",
              "Croissance / Momentum",
              "Prise de bénéfices",
              "Invalidation de la thèse",
              "Dividende",
          ],
      )
      notes = st.text_area(
          "Thèse d'investissement & Ratios clés (PER, ROCE, FCF...)",
          placeholder=(
              "Ex: Acheté à PER 9x suite crainte surtaxe autoroutes, FCF"
              " solide..."
          ),
      )

      submitted = st.form_submit_button(
          "Valider et enregistrer en BDD", use_container_width=True
      )

      if submitted:
        if not selected_stock:
          st.error(
              "⚠️ Recherche et sélectionne d'abord une valeur dans la barre"
              " ci-dessus."
          )
        else:
          tk_sym = selected_stock["symbol"]
          tk_name = selected_stock["name"]

          # Récupération automatique des vraies métadonnées via yfinance
          try:
            info = yf.Ticker(tk_sym).info
            currency = info.get("currency", "EUR")
            sector = info.get("sector") or selected_stock["sector"]
          except Exception:
            currency = "EUR"
            sector = selected_stock["sector"]

          conn = get_connection()
          cur = conn.cursor()
          cur.execute(
              """
                        INSERT INTO assets (ticker, name, currency, sector)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(ticker) DO UPDATE SET sector=excluded.sector
                    """,
              (tk_sym, tk_name, currency, sector),
          )

          cur.execute("SELECT id FROM assets WHERE ticker = ?", (tk_sym,))
          asset_id = cur.fetchone()[0]

          cur.execute(
              """
                        INSERT INTO transactions (asset_id, type, date, quantity, price, fees, exchange_rate, reason, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
              (
                  asset_id,
                  tx_type,
                  tx_date.strftime("%Y-%m-%d"),
                  qty,
                  price,
                  fees,
                  fx,
                  reason,
                  notes,
              ),
          )

          conn.commit()
          conn.close()
          st.cache_data.clear()
          st.success(f"✅ Ordre enregistré sur **{tk_name} ({tk_sym})** !")
          st.rerun()

  with col_table:
    st.subheader("📋 Mes Positions Actuelles")
    if df_pos.empty:
      st.write("Aucune position ouverte.")
    else:
      display_df = df_pos[[
          "ticker",
          "name",
          "qty",
          "PRU (€)",
          "Cours Actuel",
          "Valorisation (€)",
          "+/- Value Latente (€)",
          "+/- Value (%)",
          "Poids (%)",
      ]].rename(
          columns={
              "ticker": "Ticker",
              "name": "Entreprise",
              "qty": "Qté",
          }
      )

      st.dataframe(
          display_df.style.format({
              "Qté": "{:.2f}",
              "PRU (€)": "{:.2f} €",
              "Cours Actuel": "{:.2f} €",
              "Valorisation (€)": "{:,.2f} €",
              "+/- Value Latente (€)": "{:+,.2f} €",
              "+/- Value (%)": "{:+.2f} %",
              "Poids (%)": "{:.1f} %",
          }).map(
              lambda v: "color: #16a34a; font-weight: bold;"
              if isinstance(v, (int, float)) and v > 0
              else (
                  "color: #dc2626; font-weight: bold;"
                  if isinstance(v, (int, float)) and v < 0
                  else ""
              ),
              subset=["+/- Value Latente (€)", "+/- Value (%)"],
          ),
          use_container_width=True,
          hide_index=True,
      )

      # Graphique Barres des +/- values par ligne
      fig_bar = px.bar(
          df_pos.sort_values("+/- Value (%)", ascending=True),
          x="+/- Value (%)",
          y="name",
          orientation="h",
          title="Performance latente par ligne (%)",
          color="+/- Value (%)",
          color_continuous_scale=["#dc2626", "#f3f4f6", "#16a34a"],
          color_continuous_midpoint=0,
      )
      st.plotly_chart(fig_bar, use_container_width=True)

# ------------------------------------------
# ONGLET 3 : PERFORMANCE & JOURNAL
# ------------------------------------------
with tab_perf:
  if df_tx.empty:
    st.info(
        "Ajoute des transactions pour générer la courbe de performance"
        " historique."
    )
  else:
    st.subheader(
        "📈 Évolution de la Valorisation du Portefeuille vs Apports Cumulés"
    )

    # Reconstitution de la courbe historique depuis le 1er achat
    start_date = pd.to_datetime(df_tx["date"].min()) - timedelta(days=2)
    tickers_list = df_tx["ticker"].unique().tolist()

    with st.spinner("Calcul de l'historique boursier en cours..."):
      hist_prices = yf.download(
          tickers_list, start=start_date, progress=False
      )["Close"]
      if isinstance(hist_prices, pd.Series):
        hist_prices = hist_prices.to_frame(name=tickers_list[0])
      hist_prices = hist_prices.ffill().bfill()

      date_range = hist_prices.index
      portfolio_history = []

      for current_date in date_range:
        sub_tx = df_tx[pd.to_datetime(df_tx["date"]) <= current_date]
        invested = 0.0
        val_jour = 0.0

        for tk in tickers_list:
          tk_tx = sub_tx[sub_tx["ticker"] == tk]
          q_buy = tk_tx[tk_tx["type"] == "BUY"]["quantity"].sum()
          q_sell = tk_tx[tk_tx["type"] == "SELL"]["quantity"].sum()
          net_qty = max(0.0, q_buy - q_sell)

          cost_buy = (
              tk_tx[tk_tx["type"] == "BUY"]["quantity"]
              * tk_tx[tk_tx["type"] == "BUY"]["price"]
          ).sum()
          cost_sell = (
              tk_tx[tk_tx["type"] == "SELL"]["quantity"]
              * tk_tx[tk_tx["type"] == "SELL"]["price"]
          ).sum()
          invested += max(0.0, cost_buy - cost_sell)

          if net_qty > 0 and tk in hist_prices.columns:
            px_day = hist_prices.loc[current_date, tk]
            if pd.notnull(px_day):
              val_jour += net_qty * float(px_day)

        portfolio_history.append({
            "Date": current_date,
            "Valorisation Portefeuille (€)": val_jour,
            "Capital Investi (€)": invested,
        })

      df_hist = pd.DataFrame(portfolio_history)

      fig_perf = go.Figure()
      fig_perf.add_trace(
          go.Scatter(
              x=df_hist["Date"],
              y=df_hist["Valorisation Portefeuille (€)"],
              mode="lines",
              name="Valorisation (€)",
              line=dict(color="#2563eb", width=2.5),
              fill="tonexty",
          )
      )
      fig_perf.add_trace(
          go.Scatter(
              x=df_hist["Date"],
              y=df_hist["Capital Investi (€)"],
              mode="lines",
              name="Capital Investi (€)",
              line=dict(color="#64748b", width=2, dash="dash"),
          )
      )
      fig_perf.update_layout(hovermode="x unified", yaxis_title="Euros (€)")
      st.plotly_chart(fig_perf, use_container_width=True)

    st.divider()
    st.subheader("📓 Journal des Ordres & Thèses d'Investissement")
    st.dataframe(
        df_tx[[
            "date",
            "type",
            "ticker",
            "name",
            "quantity",
            "price",
            "fees",
            "reason",
            "notes",
        ]].sort_values("date", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
