import sqlite3
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

# Configuration
st.set_page_config(
    page_title="Portfolio Analytics",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Style épuré type terminal institutionnel
st.markdown(
    """
    <style>
        .block-container { 
            padding-top: 3.5rem; 
            padding-bottom: 2rem; 
            max-width: 1440px;
        }
        .stTabs [data-baseweb="tab-list"] { 
            gap: 12px; 
            border-bottom: 1px solid #334155; 
            padding-bottom: 4px;
            margin-bottom: 1.5rem;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 10px 20px;
            border-radius: 6px;
            background-color: #0f172a;
            border: 1px solid #1e293b;
            font-size: 0.95rem;
            font-weight: 600;
            color: #94a3b8;
        }
        .stTabs [aria-selected="true"] {
            background-color: #1e293b !important;
            color: #38bdf8 !important;
            border-color: #38bdf8 !important;
        }
        .market-ticker-box {
            background-color: #0b1120;
            border: 1px solid #1e293b;
            border-radius: 6px;
            padding: 12px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .market-ticker-title { font-size: 0.72rem; text-transform: uppercase; color: #64748b; font-weight: 700; }
        .market-ticker-val { font-size: 1.15rem; font-weight: 700; color: #f8fafc; }
        .news-card {
            background-color: #0b1120;
            border-left: 3px solid #3b82f6;
            border-radius: 4px;
            padding: 12px 16px;
            margin-bottom: 12px;
        }
        [data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
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
  indices = {"^FCHI": "CAC 40", "^GSPC": "S&P 500", "^TNX": "US 10Y"}
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

# Navigation
tab_brief, tab_holdings, tab_analytics, tab_journal = st.tabs([
    "Journal & Marchés",
    "Portefeuille & Saisie",
    "Performance & Allocation",
    "Historique des opérations",
])

# ====================================================
# ONGLET 1 : JOURNAL & MARCHÉS (NON MODIFIÉ)
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

  if df_positions.empty:
    st.info("Portefeuille en attente d'opérations.")
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
                        Plus-value latente de <b>{best_pos['unrealized_pnl_pct']:+.2f}%</b> ({best_pos['unrealized_pnl']:+,.2f} €). Poids : {best_pos['weight']:.1f}%.
                    </p>
                </div>
                <div class="news-card" style="border-left-color: {'#ef4444' if worst_pos['unrealized_pnl_pct'] < 0 else '#3b82f6'};">
                    <strong style="color: {'#ef4444' if worst_pos['unrealized_pnl_pct'] < 0 else '#3b82f6'};">Point d'attention :</strong> {worst_pos['name']} ({worst_pos['ticker']})
                    <p style="margin: 4px 0 0 0; font-size: 0.88rem; color: #cbd5e1;">
                        Performance de <b>{worst_pos['unrealized_pnl_pct']:+.2f}%</b> ({worst_pos['unrealized_pnl']:+,.2f} €). PRU : {worst_pos['pru']:.2f} € vs Cours : {worst_pos['current_price']:.2f} €.
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
      st.markdown("### Multiples de Résultats (P/E)")
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
            color_discrete_sequence=["#38bdf8"],
        )
        fig_pe.update_layout(
            margin=dict(t=10, b=10, l=10, r=10),
            height=280,
            xaxis=dict(gridcolor="#1e293b", title="Multiple P/E"),
            yaxis=dict(gridcolor="#1e293b", title=""),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_pe, use_container_width=True)

# ====================================================
# ONGLET 2 : PORTEFEUILLE & SAISIE
# ====================================================
with tab_holdings:
  col_saisie, col_table = st.columns([1, 2], gap="large")

  with col_saisie:
    st.subheader("Enregistrer un ordre")
    search_input = st.text_input(
        "Recherche de titre", placeholder="Tapez le nom ou ticker..."
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

      reason = st.text_input("Motif d'arbitrage", placeholder="Ex: Décote NAV...")
      notes = st.text_area(
          "Thèse & Ratios", placeholder="PER d'entrée, prévisions de cash flow..."
      )

      submit = st.form_submit_button(
          "Exécuter & Enregistrer", use_container_width=True
      )

      if submit:
        if not selected_asset:
          st.error("Sélectionnez une action valide.")
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
      st.write("Aucune position ouverte.")
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
# ONGLET 3 : PERFORMANCE (MÉTHODE TWR & GRAPHIQUES ÉPURÉS)
# ====================================================
with tab_analytics:
  if df_transactions.empty:
    st.info("Aucune transaction enregistrée.")
  else:
    min_date = pd.to_datetime(df_transactions["date"].min())
    tickers_list = df_transactions["ticker"].unique().tolist()

    with st.spinner("Calcul des rendements TWR et des cours..."):
      # Téléchargement des cours des actifs + benchmark CAC 40
      tickers_with_bench = tickers_list + ["^FCHI"]
      raw_prices = yf.download(
          tickers_with_bench,
          start=min_date - timedelta(days=5),
          progress=False,
      )["Close"]
      if isinstance(raw_prices, pd.Series):
        raw_prices = raw_prices.to_frame(name=tickers_with_bench[0])
      raw_prices = raw_prices.ffill().bfill()

      # Filtrer les jours ouvrés à partir de la première transaction
      trading_days = [d for d in raw_prices.index if d >= min_date]

      # Reconstitution TWR quotidienne
      # TWR(t) = Produit des (V_fin / (V_deb + Flux_net))
      twr_records = []
      cumulative_twr = 1.0
      prev_portfolio_val = 0.0

      for i, d in enumerate(trading_days):
        day_str = d.strftime("%Y-%m-%d")

        # Flux net du jour (achats = apport de cash, ventes = retrait de cash)
        day_tx = df_transactions[df_transactions["date"] == day_str]
        inflow = 0.0
        if not day_tx.empty:
          for _, r in day_tx.iterrows():
            if r["type"] == "BUY":
              inflow += (r["quantity"] * r["price"]) + r["fees"]
            elif r["type"] == "SELL":
              inflow -= (r["quantity"] * r["price"]) - r["fees"]

        # Valorisation du portefeuille en fin de journée
        sub_tx = df_transactions[pd.to_datetime(df_transactions["date"]) <= d]
        end_val = 0.0
        for tk in tickers_list:
          tx_tk = sub_tx[sub_tx["ticker"] == tk]
          q = tx_tk[tx_tk["type"] == "BUY"]["quantity"].sum() - tx_tk[
              tx_tk["type"] == "SELL"
          ]["quantity"].sum()
          if q > 0 and tk in raw_prices.columns:
            px = raw_prices.loc[d, tk]
            if pd.notnull(px):
              end_val += q * float(px)

        # Calcul du sous-rendement de la période
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

        # Benchmark CAC 40 base 100
        bench_close = (
            raw_prices.loc[d, "^FCHI"] if "^FCHI" in raw_prices.columns else 1.0
        )

        twr_records.append({
            "Date": d,
            "TWR_Index": cumulative_twr * 100.0,
            "TWR_Return_Pct": (cumulative_twr - 1.0) * 100.0,
            "Portfolio_Value": end_val,
            "Benchmark_Close": bench_close,
        })

      df_twr = pd.DataFrame(twr_records)

      # Normaliser le benchmark en base 100
      if not df_twr.empty and df_twr["Benchmark_Close"].iloc[0] > 0:
        base_bench = df_twr["Benchmark_Close"].iloc[0]
        df_twr["Benchmark_Index"] = (
            df_twr["Benchmark_Close"] / base_bench
        ) * 100.0
        df_twr["Benchmark_Return_Pct"] = df_twr["Benchmark_Index"] - 100.0

      # 1. Courbe TWR Institutionnelle
      st.subheader("Performance Pondérée dans le Temps (TWR) — Base 100")
      st.caption(
          "La méthode TWR élimine les distorsions causées par les apports ou"
          " retraits de trésorerie."
      )

      fig_twr = go.Figure()
      fig_twr.add_trace(
          go.Scatter(
              x=df_twr["Date"],
              y=df_twr["TWR_Index"],
              mode="lines",
              name="Portefeuille (TWR)",
              line=dict(color="#38bdf8", width=2.2),
          )
      )
      if "^FCHI" in raw_prices.columns:
        fig_twr.add_trace(
            go.Scatter(
                x=df_twr["Date"],
                y=df_twr["Benchmark_Index"],
                mode="lines",
                name="CAC 40 (Dividendes non réinvestis)",
                line=dict(color="#64748b", width=1.5, dash="dash"),
            )
        )

      fig_twr.update_layout(
          hovermode="x unified",
          plot_bgcolor="#0b1120",
          paper_bgcolor="#0b1120",
          font=dict(color="#94a3b8"),
          margin=dict(t=20, b=20, l=10, r=10),
          xaxis=dict(showgrid=True, gridcolor="#1e293b"),
          yaxis=dict(
              showgrid=True,
              gridcolor="#1e293b",
              title="Indice de performance (Base 100)",
          ),
          legend=dict(
              orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
          ),
      )
      st.plotly_chart(fig_twr, use_container_width=True)

    st.divider()

    # 2. Graphiques sobres : Treemap & Contribution
    c_g1, c_g2 = st.columns(2, gap="large")

    with c_g1:
      st.subheader("Matrice d'Allocation (Secteur & Ligne)")
      if not df_positions.empty:
        fig_tree = px.treemap(
            df_positions,
            path=["sector", "name"],
            values="valuation",
            color="unrealized_pnl_pct",
            color_continuous_scale=["#ef4444", "#1e293b", "#10b981"],
            color_continuous_midpoint=0,
        )
        fig_tree.update_layout(
            margin=dict(t=20, b=10, l=10, r=10),
            paper_bgcolor="#0b1120",
            font=dict(color="#f8fafc"),
        )
        st.plotly_chart(fig_tree, use_container_width=True)

    with c_g2:
      st.subheader("Contribution Nette au Portefeuille (€)")
      if not df_positions.empty:
        sorted_contrib = df_positions.sort_values(
            "unrealized_pnl", ascending=True
        )
        colors = [
            "#10b981" if v >= 0 else "#ef4444"
            for v in sorted_contrib["unrealized_pnl"]
        ]

        fig_contrib = go.Figure(
            go.Bar(
                x=sorted_contrib["unrealized_pnl"],
                y=sorted_contrib["name"],
                orientation="h",
                marker_color=colors,
            )
        )
        fig_contrib.update_layout(
            plot_bgcolor="#0b1120",
            paper_bgcolor="#0b1120",
            font=dict(color="#94a3b8"),
            margin=dict(t=20, b=10, l=10, r=10),
            xaxis=dict(showgrid=True, gridcolor="#1e293b", title="Gain / Perte en €"),
            yaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig_contrib, use_container_width=True)

# ====================================================
# ONGLET 4 : HISTORIQUE DES OPÉRATIONS (NON MODIFIÉ)
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
