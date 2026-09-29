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
    page_title="Portfolio Terminal",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Design System & Neutralisation stricte des effets de survol Streamlit
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

        html, body, [class*="css"] {
            font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
            background-color: #060911;
            color: #94a3b8;
        }

        .block-container {
            padding-top: 1.8rem;
            padding-bottom: 3rem;
            max-width: 1440px;
        }

        .mono {
            font-family: 'JetBrains Mono', monospace;
        }

        /* Cartes & Modules */
        .glass-card {
            background: #0d1322;
            border: 1px solid #1a2337;
            border-radius: 10px;
            padding: 16px 20px;
        }

        .index-pill {
            background: #0d1322;
            border: 1px solid #1a2337;
            border-radius: 8px;
            padding: 12px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        /* NEUTRALISATION ABSOLUE DU SURVOL DES ONGLETS */
        div[data-baseweb="tab-list"] {
            gap: 12px !important;
            background-color: transparent !important;
            border-bottom: 1px solid #1a2337 !important;
            padding-bottom: 0px !important;
            margin-bottom: 2rem !important;
        }

        div[data-baseweb="tab-list"] button,
        div[data-baseweb="tab"] {
            background: transparent !important;
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
            color: #64748b !important;
            font-size: 0.92rem !important;
            font-weight: 500 !important;
            padding: 10px 14px !important;
            transition: color 0.15s ease !important;
        }

        /* Aucun changement de fond au passage de la souris */
        div[data-baseweb="tab-list"] button:hover,
        div[data-baseweb="tab"]:hover,
        div[data-baseweb="tab-list"] button:focus,
        div[data-baseweb="tab"]:focus,
        div[data-baseweb="tab-list"] button:active,
        div[data-baseweb="tab"]:active {
            background: transparent !important;
            background-color: transparent !important;
            color: #e2e8f0 !important;
            box-shadow: none !important;
            border: none !important;
        }

        /* Onglet sélectionné : simple soulignement cyan élégant */
        div[data-baseweb="tab-list"] button[aria-selected="true"],
        div[data-baseweb="tab"][aria-selected="true"] {
            background: transparent !important;
            background-color: transparent !important;
            color: #38bdf8 !important;
            font-weight: 600 !important;
            border-bottom: 2px solid #38bdf8 !important;
            border-radius: 0 !important;
        }

        /* Inputs & Formulaires */
        div[data-baseweb="input"], div[data-baseweb="select"] {
            border-radius: 6px !important;
            background-color: #0d1322 !important;
            border-color: #1a2337 !important;
        }

        [data-testid="stMetricValue"] {
            font-size: 1.85rem !important;
            font-weight: 700 !important;
            color: #ffffff !important;
        }

        button[kind="primary"], .stButton > button {
            background: #2563eb !important;
            border: 1px solid #3b82f6 !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
        }

        .news-item {
            padding: 12px 16px;
            border-bottom: 1px solid #1a2337;
        }
        .news-item:last-child { border-bottom: none; }
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
                sector TEXT DEFAULT 'Industrie'
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
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                price REAL NOT NULL,
                UNIQUE(ticker, timestamp)
            );
        """)


init_db()


def record_hourly_prices(live_quotes):
  """Enregistre le cours de chaque actif toutes les heures en base SQLite."""
  current_slot = datetime.now().strftime("%Y-%m-%d %H:00:00")
  with get_connection() as conn:
    cur = conn.cursor()
    for tk, data in live_quotes.items():
      price = data.get("price", 0.0)
      if price > 0:
        cur.execute(
            """
                    INSERT OR IGNORE INTO price_history (ticker, timestamp, price)
                    VALUES (?, ?, ?)
                """,
            (tk, current_slot, price),
        )
    conn.commit()


def get_french_date():
  mois = [
      "janvier",
      "février",
      "mars",
      "avril",
      "mai",
      "juin",
      "juillet",
      "août",
      "septembre",
      "octobre",
      "novembre",
      "décembre",
  ]
  now = datetime.now()
  return f"{now.day} {mois[now.month - 1]} {now.year}"


@st.cache_data(ttl=900)
def get_market_indices():
  indices = {"^FCHI": "CAC 40", "^GSPC": "S&P 500", "^TNX": "US 10Y Bond"}
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


@st.cache_data(ttl=1800)
def get_portfolio_news(tickers):
  news_feed = []
  for tk_sym in tickers:
    try:
      tk = yf.Ticker(tk_sym)
      for item in tk.news[:3]:
        pub_time = item.get("providerPublishTime")
        dt_str = (
            datetime.fromtimestamp(pub_time).strftime("%d/%m %H:%M")
            if pub_time
            else ""
        )
        news_feed.append({
            "ticker": tk_sym,
            "title": item.get("title"),
            "publisher": item.get("publisher", "Presse"),
            "link": item.get("link"),
            "time": dt_str,
            "timestamp": pub_time or 0,
        })
    except Exception:
      continue
  news_feed.sort(key=lambda x: x["timestamp"], reverse=True)
  return news_feed[:10]


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
            "sector": q.get("sector") or "Industrie & Services",
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

  # Déclenchement automatique de la capture horaire
  record_hourly_prices(live)

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
    "Marchés & Synthèse",
    "Portefeuille & Ordres",
    "Performance & TWR",
    "Journal des opérations",
])

# ====================================================
# ONGLET 1 : MARCHÉS & SYNTHÈSE
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
          else ("#f43f5e" if vals["change"] < 0 else "#94a3b8")
      )
      prefix = "+" if vals["change"] > 0 else ""
      st.markdown(
          f"""
                <div class="index-pill">
                    <div>
                        <div style="font-size:0.75rem; font-weight:600; color:#64748b; letter-spacing:0.04em;">{idx_name}</div>
                        <div class="mono" style="font-size:1.15rem; font-weight:700; color:#ffffff; margin-top:2px;">{vals['price']:,.2f}</div>
                    </div>
                    <div class="mono" style="font-size:0.9rem; font-weight:600; color:{color};">{prefix}{vals['change']:.2f} %</div>
                </div>
            """,
          unsafe_allow_html=True,
      )

  with col_date:
    st.markdown(
        f"""
            <div class="index-pill" style="justify-content:center; text-align:center;">
                <div>
                    <div style="font-size:0.75rem; font-weight:600; color:#64748b;">SÉANCE DU JOUR</div>
                    <div style="font-size:0.95rem; font-weight:600; color:#e2e8f0; margin-top:2px;">{get_french_date()}</div>
                </div>
            </div>
        """,
        unsafe_allow_html=True,
    )

  st.write("")

  if df_positions.empty:
    st.info("Aucune position active enregistrée.")
  else:
    cost_basis = df_positions["total_cost"].sum()
    current_val = df_positions["valuation"].sum()
    unrealized = current_val - cost_basis
    unrealized_pct = (unrealized / cost_basis * 100) if cost_basis > 0 else 0.0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Actif net réévalué", f"{current_val:,.2f} €")
    k2.metric(
        "Performance globale",
        f"{unrealized:+,.2f} €",
        delta=f"{unrealized_pct:+.2f} %",
    )
    k3.metric("Capital engagé", f"{cost_basis:,.2f} €")
    k4.metric(
        "Lignes ouvertes",
        f"{len(df_positions):02d}",
        f"{df_positions['sector'].nunique()} secteurs",
    )

    st.write("")
    c_left, c_right = st.columns([1.2, 1], gap="large")

    with c_left:
      st.markdown("#### Faits marquants & Mouvements")
      best_pos = df_positions.sort_values(
          "unrealized_pnl_pct", ascending=False
      ).iloc[0]
      worst_pos = df_positions.sort_values(
          "unrealized_pnl_pct", ascending=True
      ).iloc[0]

      st.markdown(
          f"""
                <div class="glass-card" style="margin-bottom:12px; border-left: 3px solid #10b981;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:0.8rem; font-weight:700; color:#10b981; letter-spacing:0.04em;">MEILLEURE LIGNE</span>
                        <span class="mono" style="font-size:0.8rem; color:#64748b;">Poids : {best_pos['weight']:.1f} %</span>
                    </div>
                    <div style="font-size:1.15rem; font-weight:700; color:#ffffff; margin: 4px 0;">{best_pos['name']} ({best_pos['ticker']})</div>
                    <div class="mono" style="font-size:0.88rem; color:#cbd5e1;">
                        Plus-value : <span style="color:#10b981; font-weight:700;">{best_pos['unrealized_pnl_pct']:+.2f} %</span> ({best_pos['unrealized_pnl']:+,.2f} €)
                    </div>
                </div>

                <div class="glass-card" style="margin-bottom:20px; border-left: 3px solid {'#f43f5e' if worst_pos['unrealized_pnl_pct'] < 0 else '#3b82f6'};">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:0.8rem; font-weight:700; color:{'#f43f5e' if worst_pos['unrealized_pnl_pct'] < 0 else '#3b82f6'}; letter-spacing:0.04em;">POINT DE VIGILANCE</span>
                        <span class="mono" style="font-size:0.8rem; color:#64748b;">PRU : {worst_pos['pru']:.2f} €</span>
                    </div>
                    <div style="font-size:1.15rem; font-weight:700; color:#ffffff; margin: 4px 0;">{worst_pos['name']} ({worst_pos['ticker']})</div>
                    <div class="mono" style="font-size:0.88rem; color:#cbd5e1;">
                        Performance : <span style="color:{'#f43f5e' if worst_pos['unrealized_pnl_pct'] < 0 else '#3b82f6'}; font-weight:700;">{worst_pos['unrealized_pnl_pct']:+.2f} %</span> ({worst_pos['unrealized_pnl']:+,.2f} €)
                    </div>
                </div>
            """,
          unsafe_allow_html=True,
      )

      st.markdown("#### Derniers arbitrages")
      recent_tx = df_transactions.sort_values("date", ascending=False).head(3)
      for _, tx in recent_tx.iterrows():
        badge_bg = (
            "rgba(16, 185, 129, 0.15)"
            if tx["type"] == "BUY"
            else "rgba(244, 63, 94, 0.15)"
        )
        badge_color = "#10b981" if tx["type"] == "BUY" else "#f43f5e"
        badge_lbl = "ACHAT" if tx["type"] == "BUY" else "VENTE"
        st.markdown(
            f"""
                    <div class="glass-card" style="padding:12px 16px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <div style="display:flex; align-items:center; gap:8px;">
                                <span style="background:{badge_bg}; color:{badge_color}; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;">{badge_lbl}</span>
                                <span style="font-size:0.95rem; font-weight:600; color:#f1f5f9;">{tx['name']}</span>
                                <span class="mono" style="font-size:0.8rem; color:#64748b;">({tx['ticker']})</span>
                            </div>
                            <div style="font-size:0.8rem; color:#94a3b8; margin-top:4px;">Thèse : {tx['reason'] or 'Arbitrage de gestion'}</div>
                        </div>
                        <div class="mono" style="text-align:right;">
                            <div style="font-size:0.9rem; font-weight:600; color:#ffffff;">{tx['quantity']} × {tx['price']:.2f} €</div>
                            <div style="font-size:0.75rem; color:#64748b;">{tx['date']}</div>
                        </div>
                    </div>
                """,
            unsafe_allow_html=True,
        )

    with c_right:
      st.markdown("#### Valorisation (Multiples P/E)")
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
            color="pe",
            color_continuous_scale=["#3b82f6", "#1d4ed8"],
        )
        fig_pe.update_layout(
            margin=dict(t=10, b=10, l=10, r=10),
            height=300,
            xaxis=dict(
                gridcolor="rgba(255,255,255,0.05)",
                title="Ratio P/E",
                tickfont=dict(family="JetBrains Mono"),
            ),
            yaxis=dict(
                gridcolor="rgba(255,255,255,0.05)",
                title="",
                tickfont=dict(color="#f8fafc"),
            ),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig_pe, use_container_width=True)
      else:
        st.caption("Données de multiples indisponibles.")

    st.write("")
    st.markdown("#### Actualités des entreprises en portefeuille")
    active_tickers = df_positions["ticker"].tolist()
    news_items = get_portfolio_news(active_tickers)

    if news_items:
      st.markdown('<div class="glass-card" style="padding:4px 0;">', unsafe_allow_html=True)
      for item in news_items:
        st.markdown(
            f"""
                <div class="news-item">
                    <div style="display:flex; justify-content:space-between; align-items:baseline;">
                        <span class="mono" style="font-size:0.75rem; font-weight:700; color:#38bdf8;">{item['ticker']}</span>
                        <span class="mono" style="font-size:0.75rem; color:#64748b;">{item['publisher']} • {item['time']}</span>
                    </div>
                    <div style="margin-top:4px;">
                        <a href="{item['link']}" target="_blank" style="color:#f1f5f9; text-decoration:none; font-weight:600; font-size:0.92rem;">
                            {item['title']}
                        </a>
                    </div>
                </div>
            """,
            unsafe_allow_html=True,
        )
      st.markdown('</div>', unsafe_allow_html=True)
    else:
      st.caption("Aucune dépêche récente identifiée sur vos lignes.")

# ====================================================
# ONGLET 2 : PORTEFEUILLE & ORDRES
# ====================================================
with tab_holdings:
  col_saisie, col_table = st.columns([1, 2], gap="large")

  with col_saisie:
    st.markdown("#### Nouvel ordre")
    search_input = st.text_input(
        "Rechercher un actif",
        placeholder="Nom d'entreprise ou ticker...",
    )
    search_results = search_yahoo(search_input)

    selected_asset = None
    if search_results:
      options = {
          f"{item['name']} ({item['ticker']})": item for item in search_results
      }
      picked_label = st.selectbox(
          "Valeur sélectionnée", list(options.keys()), index=0
      )
      selected_asset = options[picked_label]

    with st.form("tx_entry_form", clear_on_submit=True):
      op_type = st.selectbox(
          "Sens de l'opération", ["Achat", "Vente", "Dividende"]
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
      fees = c_f.number_input("Frais de courtage (€)", min_value=0.0, value=0.0)
      fx_rate = c_fx.number_input(
          "Taux de change", min_value=0.0001, value=1.0, step=0.01
      )

      reason = st.text_input(
          "Motif d'investissement",
          placeholder="Ex: Valorisation décotée, catalyseur...",
      )
      notes = st.text_area(
          "Thèse & Métriques clés",
          placeholder="Ratios clés, ROE/ROCE, croissance attendue...",
      )

      submit = st.form_submit_button(
          "Valider l'opération", use_container_width=True
      )

      if submit:
        if not selected_asset:
          st.error("Sélectionnez une valeur avant de valider l'ordre.")
        else:
          type_code = (
              "BUY"
              if op_type == "Achat"
              else ("SELL" if op_type == "Vente" else "DIVIDEND")
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

          st.success(f"Opération enregistrée sur {selected_asset['name']}.")
          st.rerun()

  with col_table:
    st.markdown("#### Positions ouvertes")
    if df_positions.empty:
      st.write("Aucune position active.")
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
# ONGLET 3 : PERFORMANCE & TWR (AVEC INTÉGRATION HORAIRE)
# ====================================================
with tab_analytics:
  if df_transactions.empty:
    st.info("Données insuffisantes pour générer la performance.")
  else:
    timeline_options = [
        "1J",
        "5J",
        "1M",
        "3M",
        "6M",
        "1A",
        "3A",
        "5A",
        "10A",
        "MAX",
    ]
    selected_period = st.radio(
        "Période d'analyse",
        timeline_options,
        index=9,
        horizontal=True,
        label_visibility="collapsed",
    )

    first_tx_date = pd.to_datetime(df_transactions["date"].min())
    now_date = datetime.now()

    period_deltas = {
        "1J": timedelta(days=1),
        "5J": timedelta(days=5),
        "1M": timedelta(days=30),
        "3M": timedelta(days=90),
        "6M": timedelta(days=180),
        "1A": timedelta(days=365),
        "3A": timedelta(days=365 * 3),
        "5A": timedelta(days=365 * 5),
        "10A": timedelta(days=365 * 10),
    }

    if selected_period == "MAX":
      query_start_date = first_tx_date - timedelta(days=5)
    else:
      calculated_start = now_date - period_deltas[selected_period]
      query_start_date = max(first_tx_date - timedelta(days=5), calculated_start)

    tickers_list = df_transactions["ticker"].unique().tolist()
    use_hourly = selected_period in ["1J", "5J"]

    with st.spinner("Calcul de la rentabilité financière..."):
      tickers_with_bench = tickers_list + ["^FCHI"]
      interval = "60m" if use_hourly else "1d"

      raw_prices = yf.download(
          tickers_with_bench,
          start=query_start_date,
          interval=interval,
          progress=False,
      )["Close"]
      if isinstance(raw_prices, pd.Series):
        raw_prices = raw_prices.to_frame(name=tickers_with_bench[0])
      raw_prices = raw_prices.ffill().bfill()

      # Conversion timezone pour alignement
      if hasattr(raw_prices.index, "tz") and raw_prices.index.tz is not None:
        raw_prices.index = raw_prices.index.tz_convert(None)

      trading_points = [
          pt for pt in raw_prices.index if pt >= pd.to_datetime(query_start_date)
      ]

      twr_records = []
      cumulative_twr = 1.0
      prev_portfolio_val = 0.0

      for i, pt in enumerate(trading_points):
        pt_date_str = pt.strftime("%Y-%m-%d")

        # Inflow / Outflow à la date du point
        day_tx = df_transactions[df_transactions["date"] == pt_date_str]
        inflow = 0.0
        if not day_tx.empty and (
            not use_hourly or pt.hour == 9
        ):  # Compté en début de séance
          for _, r in day_tx.iterrows():
            if r["type"] == "BUY":
              inflow += (r["quantity"] * r["price"]) + r["fees"]
            elif r["type"] == "SELL":
              inflow -= (r["quantity"] * r["price"]) - r["fees"]

        sub_tx = df_transactions[pd.to_datetime(df_transactions["date"]) <= pt]
        end_val = 0.0
        for tk in tickers_list:
          tx_tk = sub_tx[sub_tx["ticker"] == tk]
          q = tx_tk[tx_tk["type"] == "BUY"]["quantity"].sum() - tx_tk[
              tx_tk["type"] == "SELL"
          ]["quantity"].sum()
          if q > 0 and tk in raw_prices.columns:
            px_val = raw_prices.loc[pt, tk]
            if pd.notnull(px_val):
              end_val += q * float(px_val)

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
            raw_prices.loc[pt, "^FCHI"]
            if "^FCHI" in raw_prices.columns
            else 1.0
        )

        twr_records.append({
            "Date": pt,
            "TWR_Raw": cumulative_twr,
            "Benchmark_Close": bench_close,
        })

      df_twr = pd.DataFrame(twr_records)

      if not df_twr.empty:
        base_twr = df_twr["TWR_Raw"].iloc[0]
        df_twr["Portfolio_Return_Pct"] = (
            (df_twr["TWR_Raw"] / base_twr) - 1.0
        ) * 100.0

        if "^FCHI" in raw_prices.columns and df_twr["Benchmark_Close"].iloc[0] > 0:
          base_bench = df_twr["Benchmark_Close"].iloc[0]
          df_twr["CAC_Return_Pct"] = (
              (df_twr["Benchmark_Close"] / base_bench) - 1.0
          ) * 100.0

      st.markdown("#### Performance cumulée (%)")
      st.caption(
          "Méthode TWR (Time-Weighted Return) neutralisant les apports et"
          " retraits de trésorerie."
      )

      fig_twr = go.Figure()
      fig_twr.add_trace(
          go.Scatter(
              x=df_twr["Date"],
              y=df_twr["Portfolio_Return_Pct"],
              mode="lines",
              name="Portefeuille",
              line=dict(color="#38bdf8", width=2.4),
          )
      )
      if "^FCHI" in raw_prices.columns:
        fig_twr.add_trace(
            go.Scatter(
                x=df_twr["Date"],
                y=df_twr["CAC_Return_Pct"],
                mode="lines",
                name="CAC 40",
                line=dict(color="#64748b", width=1.5, dash="dot"),
            )
        )

      fig_twr.add_hline(
          y=0, line_dash="solid", line_color="rgba(255,255,255,0.15)", line_width=1
      )

      fig_twr.update_layout(
          hovermode="x unified",
          plot_bgcolor="rgba(0,0,0,0)",
          paper_bgcolor="rgba(0,0,0,0)",
          font=dict(color="#94a3b8"),
          margin=dict(t=10, b=10, l=10, r=10),
          xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
          yaxis=dict(
              showgrid=True,
              gridcolor="rgba(255,255,255,0.05)",
              title="Rendement (%)",
              ticksuffix=" %",
          ),
          legend=dict(
              orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
          ),
      )
      st.plotly_chart(fig_twr, use_container_width=True)

    st.write("")
    c_g1, c_g2 = st.columns(2, gap="large")

    with c_g1:
      st.markdown("#### Structure du capital (Donut)")
      if not df_positions.empty:
        fig_donut = px.pie(
            df_positions,
            values="valuation",
            names="name",
            hole=0.6,
            color_discrete_sequence=[
                "#38bdf8",
                "#0284c7",
                "#0369a1",
                "#025985",
                "#075985",
            ],
        )
        fig_donut.update_layout(
            margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#f8fafc"),
            showlegend=True,
        )
        st.plotly_chart(fig_donut, use_container_width=True)

    with c_g2:
      st.markdown("#### Plus / Moins-values par ligne (€)")
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
                marker=dict(color=bar_colors),
            )
        )
        fig_contrib.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8"),
            margin=dict(t=10, b=10, l=10, r=10),
            xaxis=dict(
                showgrid=True,
                gridcolor="rgba(255,255,255,0.05)",
                title="P&L (€)",
            ),
            yaxis=dict(showgrid=False, tickfont=dict(color="#f8fafc")),
        )
        st.plotly_chart(fig_contrib, use_container_width=True)

# ====================================================
# ONGLET 4 : JOURNAL DES OPÉRATIONS
# ====================================================
with tab_journal:
  st.markdown("#### Journal d'arbitrage et thèses d'investissement")
  if df_transactions.empty:
    st.write("Aucune opération répertoriée.")
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
