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
    page_title="QUANT // PORTFOLIO TERMINAL",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Style Ultra-Technologique / Cyber Financial Terminal
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700&family=Inter:wght@400;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, sans-serif;
            background-color: #030712;
            color: #94a3b8;
        }

        .block-container {
            padding-top: 2.2rem;
            padding-bottom: 2rem;
            max-width: 1480px;
        }

        /* Typography & Chiffres Monospace */
        code, .stMetric, .market-ticker-val, table {
            font-family: 'JetBrains Mono', monospace !important;
        }

        /* Onglets Terminal */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            background-color: transparent;
            border-bottom: 1px solid #1e293b;
            padding-bottom: 8px;
            margin-bottom: 1.8rem;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 8px 18px;
            border-radius: 4px;
            background-color: #0b1329;
            border: 1px solid #1e293b;
            font-size: 0.85rem;
            font-weight: 600;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            transition: all 0.2s ease;
        }
        .stTabs [aria-selected="true"] {
            background-color: #0369a1 !important;
            color: #38bdf8 !important;
            border-color: #38bdf8 !important;
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.25);
        }

        /* Cadres & Modules */
        .quant-box {
            background: linear-gradient(180deg, #090e1a 0%, #050811 100%);
            border: 1px solid #1e293b;
            border-radius: 6px;
            padding: 14px 18px;
            position: relative;
        }
        .quant-box::before {
            content: '';
            position: absolute;
            top: 0; left: 0; width: 4px; height: 100%;
            background: #0284c7;
            border-top-left-radius: 6px;
            border-bottom-left-radius: 6px;
        }
        .quant-title {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.7rem;
            text-transform: uppercase;
            color: #475569;
            font-weight: 700;
            letter-spacing: 0.12em;
        }
        .market-ticker-val {
            font-size: 1.25rem;
            font-weight: 700;
            color: #f1f5f9;
        }

        /* Boutons & Formulaires */
        button[kind="primary"], .stButton > button {
            background-color: #0284c7 !important;
            color: #f8fafc !important;
            border: 1px solid #38bdf8 !important;
            border-radius: 4px !important;
            font-family: 'JetBrains Mono', monospace !important;
            font-weight: 600 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.05em !important;
        }
        button[kind="primary"]:hover, .stButton > button:hover {
            box-shadow: 0 0 14px rgba(56, 189, 248, 0.4) !important;
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
                sector TEXT DEFAULT 'INDUSTRIE'
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
  indices = {"^FCHI": "CAC 40", "^GSPC": "S&P 500", "^TNX": "US 10Y"}
  out = {}
  for symbol, name in indices.items():
    try:
      tk = yf.Ticker(symbol)
      hist = tk.history(period="5d")
      if len(hist) >= 2:
        c = hist["Close"].iloc[-1]
        p = hist["Close"].iloc[-2]
        chg = ((c - p) / p) * 100
        out[name] = {"price": c, "change": chg}
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
            "sector": q.get("sector") or "Divers",
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
      p = (
          info.get("currentPrice")
          or info.get("regularMarketPrice")
          or info.get("previousClose")
          or 0.0
      )
      quotes[t] = {
          "price": float(p),
          "pe": info.get("trailingPE"),
          "yield": (info.get("dividendYield") or 0.0) * 100,
          "sector": info.get("sector") or "Industrie / Divers",
          "day_change": info.get("regularMarketChangePercent", 0.0),
      }
    except Exception:
      quotes[t] = {
          "price": 0.0,
          "pe": None,
          "yield": 0.0,
          "sector": "Divers",
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
          "sector": tx["sector"] if tx["sector"] else "Divers",
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
  # Remplir le secteur s'il était manquant
  df_pos["sector"] = df_pos["ticker"].map(
      lambda x: live.get(x, {}).get("sector")
      or df_pos.loc[df_pos["ticker"] == x, "sector"].iloc[0]
      or "Divers"
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

# Navigation
tab_brief, tab_holdings, tab_analytics, tab_journal = st.tabs([
    "01 // JOURNAL & MARCHÉS",
    "02 // PORTEFEUILLE & ORDRES",
    "03 // ANALYTICS & TWR",
    "04 // JOURNAL DES LOGS",
])

# ====================================================
# ONGLET 1 : JOURNAL & MARCHÉS (ACCUEIL)
# ====================================================
with tab_brief:
  indices_data = get_market_indices()
  col_i1, col_i2, col_i3, col_date = st.columns([1, 1, 1, 1.2])

  for col, (idx_name, vals) in zip(
      [col_i1, col_i2, col_i3], indices_data.items()
  ):
    with col:
      color = (
          "#10b981"
          if vals["change"] >= 0
          else ("#f43f5e" if vals["change"] < 0 else "#64748b")
      )
      prefix = "+" if vals["change"] > 0 else ""
      st.markdown(
          f"""
                <div class="quant-box">
                    <div class="quant-title">{idx_name} // INDEX</div>
                    <div style="display:flex; justify-content:space-between; align-items:baseline; margin-top:4px;">
                        <span class="market-ticker-val">{vals['price']:,.2f}</span>
                        <span style="font-family:'JetBrains Mono',monospace; font-weight:700; color:{color};">{prefix}{vals['change']:.2f}%</span>
                    </div>
                </div>
            """,
          unsafe_allow_html=True,
      )

  with col_date:
    st.markdown(
        f"""
            <div class="quant-box" style="border-left-color: #38bdf8;">
                <div class="quant-title">SYSTEM STATUS // UTC+2</div>
                <div class="market-ticker-val" style="font-size:1rem; margin-top:4px; color:#38bdf8;">
                    {datetime.now().strftime('%Y-%m-%d // %H:%M')}
                </div>
            </div>
        """,
        unsafe_allow_html=True,
    )

  st.write("")

  if df_positions.empty:
    st.info("AUCUNE POSITION ACTIVE // VEUILLEZ SAISIR UN PREMIER ORDRE.")
  else:
    cost_basis = df_positions["total_cost"].sum()
    current_val = df_positions["valuation"].sum()
    unrealized = current_val - cost_basis
    unrealized_pct = (unrealized / cost_basis * 100) if cost_basis > 0 else 0.0

    st.markdown(
        "<div class='quant-title' style='margin-bottom:8px;'>SYNTHÈSE"
        " D'EXPOSITION GLOBALE</div>",
        unsafe_allow_html=True,
    )
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("NAV GLOBALE", f"{current_val:,.2f} €")
    k2.metric(
        "P&L LATENT NET",
        f"{unrealized:+,.2f} €",
        delta=f"{unrealized_pct:+.2f} %",
    )
    k3.metric("CAPITAL INVESTI", f"{cost_basis:,.2f} €")
    k4.metric(
        "LIGNES ACTIVES",
        f"{len(df_positions):02d}",
        f"{df_positions['sector'].nunique()} secteurs",
    )

    st.divider()

    c_left, c_right = st.columns([1.2, 1])
    with c_left:
      st.markdown("### FOCUS VALEURS // SÉANCE")
      best_pos = df_positions.sort_values(
          "unrealized_pnl_pct", ascending=False
      ).iloc[0]
      worst_pos = df_positions.sort_values(
          "unrealized_pnl_pct", ascending=True
      ).iloc[0]

      st.markdown(
          f"""
                <div class="quant-box" style="border-left-color: #10b981; margin-bottom:10px;">
                    <div style="color: #10b981; font-family:'JetBrains Mono',monospace; font-size:0.75rem; font-weight:700;">TOP PERFORMER >> {best_pos['ticker']}</div>
                    <div style="font-size:1.1rem; font-weight:700; color:#f8fafc; margin-top:2px;">{best_pos['name']}</div>
                    <div style="font-family:'JetBrains Mono',monospace; font-size:0.85rem; color:#94a3b8; margin-top:4px;">
                        P&L: <span style="color:#10b981; font-weight:700;">{best_pos['unrealized_pnl_pct']:+.2f}%</span> ({best_pos['unrealized_pnl']:+,.2f} €) | POIDS: {best_pos['weight']:.1f}%
                    </div>
                </div>
                <div class="quant-box" style="border-left-color: {'#f43f5e' if worst_pos['unrealized_pnl_pct'] < 0 else '#0284c7'}; margin-bottom:16px;">
                    <div style="color: {'#f43f5e' if worst_pos['unrealized_pnl_pct'] < 0 else '#0284c7'}; font-family:'JetBrains Mono',monospace; font-size:0.75rem; font-weight:700;">LOW PERFORMER >> {worst_pos['ticker']}</div>
                    <div style="font-size:1.1rem; font-weight:700; color:#f8fafc; margin-top:2px;">{worst_pos['name']}</div>
                    <div style="font-family:'JetBrains Mono',monospace; font-size:0.85rem; color:#94a3b8; margin-top:4px;">
                        P&L: <span style="color:{'#f43f5e' if worst_pos['unrealized_pnl_pct'] < 0 else '#0284c7'}; font-weight:700;">{worst_pos['unrealized_pnl_pct']:+.2f}%</span> ({worst_pos['unrealized_pnl']:+,.2f} €) | PRU: {worst_pos['pru']:.2f} €
                    </div>
                </div>
            """,
          unsafe_allow_html=True,
      )

      st.markdown("### DERNIERS ARBITRAGES")
      recent_tx = df_transactions.sort_values("date", ascending=False).head(3)
      for _, tx in recent_tx.iterrows():
        color_badge = "#10b981" if tx["type"] == "BUY" else "#f43f5e"
        st.markdown(
            f"""
                    <div style="padding: 10px 14px; background:#070d1d; border:1px solid #1e293b; border-radius:4px; margin-bottom:8px; font-family:'JetBrains Mono',monospace; font-size:0.82rem;">
                        <span style="color:{color_badge}; font-weight:700;">[{tx['type']}]</span> 
                        <span style="color:#cbd5e1; font-weight:600;">{tx['date']}</span> // {tx['name']} ({tx['quantity']} @ {tx['price']:.2f} €)
                        <div style="color:#64748b; font-size:0.75rem; margin-top:3px;">MOTIF: {tx['reason'] or 'N/A'}</div>
                    </div>
                """,
            unsafe_allow_html=True,
        )

    with c_right:
      st.markdown("### VALORISATION // MULTIPLES P/E")
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
            color_discrete_sequence=["#0284c7"],
        )
        fig_pe.update_layout(
            margin=dict(t=10, b=10, l=10, r=10),
            height=280,
            xaxis=dict(
                gridcolor="#1e293b",
                title="P/E RATIO",
                tickfont=dict(family="JetBrains Mono"),
            ),
            yaxis=dict(
                gridcolor="#1e293b", title="", tickfont=dict(color="#f8fafc")
            ),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_pe, use_container_width=True)
      else:
        st.caption("MULTIPLES NON DISPONIBLES SUR LES VALEURS DU PORTEFEUILLE.")

# ====================================================
# ONGLET 2 : PORTEFEUILLE & ORDRES
# ====================================================
with tab_holdings:
  col_saisie, col_table = st.columns([1, 2], gap="large")

  with col_saisie:
    st.markdown("### SAISIE D'ORDRE")
    search_input = st.text_input(
        "RECHERCHE ACTIF", placeholder="Rechercher ticker / libellé..."
    )
    search_results = search_yahoo(search_input)

    selected_asset = None
    if search_results:
      options = {
          f"{item['name']} ({item['ticker']})": item for item in search_results
      }
      picked_label = st.selectbox(
          "SÉLECTION DU TITRE :", list(options.keys()), index=0
      )
      selected_asset = options[picked_label]

    with st.form("tx_entry_form", clear_on_submit=True):
      op_type = st.selectbox(
          "NATURE DE L'ORDRE",
          ["Achat (BUY)", "Vente (SELL)", "Dividende (DIVIDEND)"],
      )
      op_date = st.date_input("DATE D'EXÉCUTION", value=datetime.today())

      c_q, c_p = st.columns(2)
      quantity = c_q.number_input(
          "QUANTITÉ", min_value=0.0001, value=1.0, step=1.0
      )
      price = c_p.number_input(
          "PRIX D'EXÉCUTION (€)", min_value=0.0001, value=100.0, step=0.1
      )

      c_f, c_fx = st.columns(2)
      fees = c_f.number_input("FRAIS (€)", min_value=0.0, value=0.0)
      fx_rate = c_fx.number_input(
          "TAUX DE CHANGE", min_value=0.0001, value=1.0, step=0.01
      )

      reason = st.text_input(
          "CATALYSEUR / MOTIF", placeholder="Ex: Ratio EV/EBIT attractif..."
      )
      notes = st.text_area(
          "THÈSE D'INVESTISSEMENT",
          placeholder="Hypothèses de croissance, FCF yield, ROCE...",
      )

      submit = st.form_submit_button(
          "EXÉCUTER L'ORDRE // COMMIT", use_container_width=True
      )

      if submit:
        if not selected_asset:
          st.error("VEUILLEZ SÉLECTIONNER UN ACTIF VALIDE.")
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

          st.success(f"ORDRE VALIDÉ // {selected_asset['ticker']}")
          st.rerun()

  with col_table:
    st.markdown("### POSITIONS EN PORTEFEUILLE")
    if df_positions.empty:
      st.write("AUCUNE POSITION ACTIVE DÉTECTÉE.")
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
# ONGLET 3 : ANALYTICS & TWR (CORRECTIF APPLIQUÉ)
# ====================================================
with tab_analytics:
  if df_transactions.empty:
    st.info("HISTORIQUE INSUFFISANT POUR LE CALCUL TWR.")
  else:
    min_date = pd.to_datetime(df_transactions["date"].min())
    tickers_list = df_transactions["ticker"].unique().tolist()

    with st.spinner("CALCUL DE LA PERFORMANCE QUANTITATIVE (TWR)..."):
      tickers_with_bench = tickers_list + ["^FCHI"]
      raw_prices = yf.download(
          tickers_with_bench,
          start=min_date - timedelta(days=5),
          progress=False,
      )["Close"]
      if isinstance(raw_prices, pd.Series):
        raw_prices = raw_prices.to_frame(name=tickers_with_bench[0])
      raw_prices = raw_prices.ffill().bfill()

      trading_days = [d for d in raw_prices.index if d >= min_date]

      twr_records = []
      cumulative_twr = 1.0
      prev_portfolio_val = 0.0

      for i, d in enumerate(trading_days):
        day_str = d.strftime("%Y-%m-%d")

        # Flux net (achats = apport de cash, ventes = retrait)
        day_tx = df_transactions[df_transactions["date"] == day_str]
        inflow = 0.0
        if not day_tx.empty:
          for _, r in day_tx.iterrows():
            if r["type"] == "BUY":
              inflow += (r["quantity"] * r["price"]) + r["fees"]
            elif r["type"] == "SELL":
              inflow -= (r["quantity"] * r["price"]) - r["fees"]

        # Valorisation fin de journée
        sub_tx = df_transactions[pd.to_datetime(df_transactions["date"]) <= d]
        end_val = 0.0
        for tk in tickers_list:
          tx_tk = sub_tx[sub_tx["ticker"] == tk]
          q = tx_tk[tx_tk["type"] == "BUY"]["quantity"].sum() - tx_tk[
              tx_tk["type"] == "SELL"
          ]["quantity"].sum()
          if q > 0 and tk in raw_prices.columns:
            px_val = raw_prices.loc[d, tk]
            if pd.notnull(px_val):
              end_val += q * float(px_val)

        # Calcul du sous-rendement de période
        if i == 0:
          start_capital = inflow if inflow > 0 else end_val
          sub_return = (
              (end_val / start_capital) - 1.0 if start_capital > 0 else 0.0
          )
        else:
          base = prev_portfolio_val + inflow
          sub_return = (end_val - base) / base if base > 0 else 0.0

        cumulative_twr *= 1.0 + sub_return
        prev_portfolio_val = end_val

        bench_close = (
            raw_prices.loc[d, "^FCHI"] if "^FCHI" in raw_prices.columns else 1.0
        )

        twr_records.append({
            "Date": d,
            "TWR_Index": cumulative_twr * 100.0,
            "Portfolio_Value": end_val,
            "Benchmark_Close": bench_close,
        })

      df_twr = pd.DataFrame(twr_records)

      if not df_twr.empty and df_twr["Benchmark_Close"].iloc[0] > 0:
        base_bench = df_twr["Benchmark_Close"].iloc[0]
        df_twr["Benchmark_Index"] = (
            df_twr["Benchmark_Close"] / base_bench
        ) * 100.0

      # Graphique TWR
      st.markdown("### TIME-WEIGHTED RETURN (TWR) // BASE 100")
      fig_twr = go.Figure()
      fig_twr.add_trace(
          go.Scatter(
              x=df_twr["Date"],
              y=df_twr["TWR_Index"],
              mode="lines",
              name="PORTFOLIO NAV (TWR)",
              line=dict(color="#38bdf8", width=2.2),
          )
      )
      if "^FCHI" in raw_prices.columns:
        fig_twr.add_trace(
            go.Scatter(
                x=df_twr["Date"],
                y=df_twr["Benchmark_Index"],
                mode="lines",
                name="CAC 40 BENCHMARK",
                line=dict(color="#64748b", width=1.5, dash="dot"),
            )
        )

      fig_twr.update_layout(
          hovermode="x unified",
          plot_bgcolor="#050811",
          paper_bgcolor="#050811",
          font=dict(family="JetBrains Mono", color="#94a3b8"),
          margin=dict(t=20, b=20, l=10, r=10),
          xaxis=dict(showgrid=True, gridcolor="#111827"),
          yaxis=dict(
              showgrid=True, gridcolor="#111827", title="INDICE (BASE 100)"
          ),
          legend=dict(
              orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
          ),
      )
      st.plotly_chart(fig_twr, use_container_width=True)

    st.divider()

    # Graphiques d'Allocation corrigés (Sans risque de crash AttributeError)
    c_g1, c_g2 = st.columns(2, gap="large")

    with c_g1:
      st.markdown("### MATRICE D'ALLOCATION SECTORIELLE")
      if not df_positions.empty:
        # Sécurisation stricte des colonnes pour éviter tout crash Treemap
        clean_pos = df_positions.copy()
        clean_pos["sector"] = clean_pos["sector"].fillna("Divers").astype(str)
        clean_pos["name"] = clean_pos["name"].fillna(clean_pos["ticker"]).astype(str)
        clean_pos["valuation"] = clean_pos["valuation"].fillna(0.0).astype(float)
        clean_pos = clean_pos[clean_pos["valuation"] > 0]

        fig_alloc = px.sunburst(
            clean_pos,
            path=["sector", "name"],
            values="valuation",
            color_discrete_sequence=[
                "#0284c7",
                "#0ea5e9",
                "#38bdf8",
                "#0369a1",
                "#075985",
            ],
        )
        fig_alloc.update_layout(
            margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="#050811",
            font=dict(family="JetBrains Mono", color="#f8fafc"),
        )
        st.plotly_chart(fig_alloc, use_container_width=True)

    with c_g2:
      st.markdown("### CONTRIBUTION NETTE P&L (€)")
      if not df_positions.empty:
        sorted_contrib = df_positions.sort_values(
            "unrealized_pnl", ascending=True
        )
        bar_colors = [
            "#10b981" if v >= 0 else "#f43f5e"
            for v in sorted_contrib["unrealized_pnl"]
        ]

        fig_contrib = go.Figure(
            go.Bar(
                x=sorted_contrib["unrealized_pnl"],
                y=sorted_contrib["name"],
                orientation="h",
                marker=dict(
                    color=bar_colors,
                    line=dict(
                        color=["#34d399" if v >= 0 else "#fb7185" for v in sorted_contrib["unrealized_pnl"]],
                        width=1,
                    ),
                ),
            )
        )
        fig_contrib.update_layout(
            plot_bgcolor="#050811",
            paper_bgcolor="#050811",
            font=dict(family="JetBrains Mono", color="#94a3b8"),
            margin=dict(t=10, b=10, l=10, r=10),
            xaxis=dict(
                showgrid=True, gridcolor="#111827", title="P&L LATENT (€)"
            ),
            yaxis=dict(showgrid=False, tickfont=dict(color="#f8fafc")),
        )
        st.plotly_chart(fig_contrib, use_container_width=True)

# ====================================================
# ONGLET 4 : JOURNAL DES LOGS
# ====================================================
with tab_journal:
  st.markdown("### JOURNAL DES TRANSACTIONS // AUDIT TRAIL")
  if df_transactions.empty:
    st.write("AUCUNE OPÉRATION ENREGISTRÉE DANS LA BASE.")
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
