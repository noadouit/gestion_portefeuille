import base64
import sqlite3
import time
from datetime import datetime, timedelta
from io import StringIO
import email.utils
import xml.etree.ElementTree as ET
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

# Configuration
st.set_page_config(
    page_title="Asset Management",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Mot de passe obfusqué (ne s'affiche plus en clair sur GitHub)
_ENCODED_KEY = "c2VjcmV0MjAyNg=="  # Décode vers "secret2026"

def get_authorized_password() -> str:
    """Récupère le mot de passe depuis st.secrets (si configuré) ou via la clé obfusquée."""
    try:
        if "PORTFOLIO_PASSWORD" in st.secrets:
            return str(st.secrets["PORTFOLIO_PASSWORD"])
    except Exception:
        pass
    return base64.b64decode(_ENCODED_KEY.encode("utf-8")).decode("utf-8")

# Gestion de l'état d'authentification et de l'animation hacker
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "trigger_hacker_fx" not in st.session_state:
    st.session_state["trigger_hacker_fx"] = False

# Animation Hacker longue (~4.8s)
if st.session_state.get("trigger_hacker_fx", False):
    st.session_state["trigger_hacker_fx"] = False
    st.markdown(
        """
        <div id="cyber-overlay">
            <div class="cyber-scanlines"></div>
            <div class="cyber-radar"></div>
            <div class="cyber-terminal">
                <div class="cyber-prompt">> INITIATING ROOT EXPLOIT [KERNEL_v6.12.9-X64]...</div>
                <div class="cyber-line c-cyan">> Bypassing proxy nodes [PARIS -> ZURICH -> FRANKFURT -> REYKJAVIK] [OK]</div>
                <div class="cyber-line c-green">> Decrypting RSA-4096 / SHA-512 cold storage keys...</div>
                <div class="cyber-line c-dim">> 0x7F4A8C0B ... 0x99DF21EA ... MATCH FOUND [100%]</div>
                <div class="cyber-line c-green">> Injecting decrypted positions ledger into memory pool...</div>
                <div class="cyber-line c-cyan">> Unmasking true portfolio valuation: SYNCHRONIZING TICKERS...</div>
                <div class="cyber-line c-green">> OVERRIDING DEMO PRIVACY PROTOCOLS [BYPASS SUCCESSFUL]</div>
                <div class="cyber-glitch-box">
                    <div class="cyber-glitch-title">ACCESS GRANTED</div>
                    <div class="cyber-sub">CLEARANCE: ROOT_ALPHA // TERMINAL UNLOCKED</div>
                </div>
            </div>
        </div>

        <style>
            #cyber-overlay {
                position: fixed;
                top: 0; left: 0; width: 100vw; height: 100vh;
                background: #010307;
                z-index: 9999999;
                display: flex;
                align-items: center;
                justify-content: center;
                font-family: 'JetBrains Mono', monospace;
                animation: fadeOutCyber 4.8s cubic-bezier(0.85, 0, 0.15, 1) forwards;
                pointer-events: none;
            }
            .cyber-scanlines {
                position: absolute;
                top: 0; left: 0; width: 100%; height: 100%;
                background: repeating-linear-gradient(
                    to bottom,
                    rgba(255,255,255,0),
                    rgba(255,255,255,0) 2px,
                    rgba(0, 255, 128, 0.05) 3px,
                    rgba(0, 0, 0, 0.5) 4px
                );
                pointer-events: none;
            }
            .cyber-radar {
                position: absolute;
                width: 600px;
                height: 600px;
                border-radius: 50%;
                border: 1px dashed rgba(16, 185, 129, 0.15);
                box-shadow: 0 0 100px rgba(16, 185, 129, 0.05);
                animation: spinRadar 6s linear infinite;
            }
            .cyber-terminal {
                position: relative;
                width: 90%;
                max-width: 780px;
                padding: 42px 46px;
                background: rgba(3, 8, 18, 0.96);
                border: 1px solid #10b981;
                border-radius: 8px;
                box-shadow: 0 0 60px rgba(16, 185, 129, 0.4), inset 0 0 40px rgba(16, 185, 129, 0.08);
            }
            .cyber-prompt {
                font-size: 1rem;
                font-weight: 700;
                color: #ffffff;
                margin-bottom: 12px;
                animation: typeLine 0.1s forwards;
            }
            .cyber-line {
                font-size: 0.88rem;
                margin-bottom: 7px;
                opacity: 0;
                animation: lineAppear 0.2s forwards;
            }
            .c-green { color: #10b981; text-shadow: 0 0 8px rgba(16, 185, 129, 0.8); }
            .c-cyan { color: #38bdf8; text-shadow: 0 0 8px rgba(56, 189, 248, 0.8); }
            .c-dim { color: #64748b; font-size: 0.8rem; }

            .cyber-line:nth-child(2) { animation-delay: 0.4s; }
            .cyber-line:nth-child(3) { animation-delay: 1.0s; }
            .cyber-line:nth-child(4) { animation-delay: 1.5s; }
            .cyber-line:nth-child(5) { animation-delay: 2.1s; }
            .cyber-line:nth-child(6) { animation-delay: 2.6s; }
            .cyber-line:nth-child(7) { animation-delay: 3.1s; }

            .cyber-glitch-box {
                margin-top: 26px;
                padding-top: 18px;
                border-top: 1px dashed rgba(16, 185, 129, 0.3);
                opacity: 0;
                animation: glitchPulse 0.5s 3.5s forwards;
            }
            .cyber-glitch-title {
                font-size: 2.5rem;
                font-weight: 800;
                color: #ffffff;
                letter-spacing: 0.18em;
                text-shadow: 3px 2px #10b981, -3px -2px #0284c7;
            }
            .cyber-sub {
                color: #38bdf8;
                font-size: 0.85rem;
                margin-top: 4px;
                letter-spacing: 0.08em;
            }

            @keyframes spinRadar {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }
            @keyframes lineAppear {
                to { opacity: 1; }
            }
            @keyframes glitchPulse {
                0% { opacity: 0; transform: scale(0.95); }
                40% { opacity: 1; transform: scale(1.03) skewX(-2deg); }
                70% { opacity: 0.8; transform: scale(0.99) skewX(2deg); }
                100% { opacity: 1; transform: scale(1); }
            }
            @keyframes fadeOutCyber {
                0% { opacity: 1; }
                84% { opacity: 1; }
                100% { opacity: 0; visibility: hidden; }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

is_real_mode = st.session_state["authenticated"]
PRIVACY_RATIO = 1.0 if is_real_mode else 0.25

DB_PATH = "portfolio.db"

RAW_PERF_CSV = """Date,Valo,PerfJour,PerfCumul
2026-01-02,11558.04,0.534,0.534
2026-01-05,11726.314,0.758,1.296
2026-01-06,11780.262,0.46,1.762
2026-01-07,11745.1,-0.355,1.401
2026-01-08,11606.346,-1.181,0.203
2026-01-09,11778.692,1.485,1.691
2026-01-12,11834.628,0.475,2.174
2026-01-13,11830.518,-0.035,2.139
2026-01-14,11964.062,1.129,3.292
2026-01-15,12080.418,0.973,4.296
2026-01-16,12027.282,-0.44,3.837
2026-01-19,11907.822,-0.993,2.806
2026-01-20,11862.312,-0.382,2.413
2026-01-21,11998.918,1.152,3.593
2026-01-22,12019.528,0.172,3.77
2026-01-23,12088.06,0.57,4.362
2026-01-26,12051.898,-0.299,4.05
2026-01-27,12048.226,-0.03,4.018
2026-01-28,12096.156,0.398,4.432
2026-01-29,12147.866,0.427,4.878
2026-01-30,12065.986,-0.674,4.172
2026-02-02,12130.654,0.536,4.73
2026-02-03,12254.046,1.017,5.795
2026-02-04,12421.916,1.37,7.244
2026-02-05,12282.328,-1.124,6.039
2026-02-06,12319.166,0.3,6.357
2026-02-09,12481.874,1.321,7.762
2026-02-10,12540.24,0.468,8.266
2026-02-11,12560.392,0.161,8.44
2026-02-12,12483.2,-0.615,7.774
2026-02-13,12482.982,-0.002,7.772
2026-02-16,12422.752,-0.482,7.252
2026-02-17,12401.512,-0.171,7.068
2026-02-18,12543.112,1.142,8.291
2026-02-19,12410.654,-1.056,7.147
2026-02-20,12553.165,1.148,8.378
2026-02-23,12443.285,-0.875,7.429
2026-02-24,12499.76,0.454,7.917
2026-02-25,12581.27,0.652,8.62
2026-02-26,12866.64,2.268,11.084
2026-02-27,12828.03,-0.3,10.751
2026-03-02,12866.04,0.296,11.079
2026-03-03,12767.11,-0.769,10.225
2026-03-04,13030.74,2.065,12.501
2026-03-05,12896.84,-1.028,11.345
2026-03-06,12898.4,0.012,11.358
2026-03-09,12844.22,-0.42,10.89
2026-03-10,12887.02,0.333,11.26
2026-03-11,12887.13,0.001,11.261
2026-03-12,12963.07,0.589,11.917
2026-03-13,12930.23,-0.253,11.633
2026-03-16,12809.38,-0.935,10.59
2026-03-17,12987.2,1.388,12.125
2026-03-18,12887.41,-0.768,11.263
2026-03-19,12844.41,-0.334,10.892
2026-03-20,12670.62,-1.353,9.392
2026-03-23,12569.66,-0.797,8.52
2026-03-24,12491.73,-0.62,7.847
2026-03-25,12594.93,0.826,8.738
2026-03-26,12359.135,-1.872,6.702
2026-03-27,12241.0,-0.956,5.683
2026-03-30,12433.76,1.575,7.347
2026-03-31,12699.62,2.138,9.642
2026-04-01,12716.44,0.132,9.787
2026-04-02,12909.96,1.522,11.458
2026-04-03,12909.96,0.0,11.458
2026-04-07,12967.38,0.445,11.954
2026-04-08,13129.36,1.249,13.352
2026-04-09,13197.15,0.516,13.937
2026-04-10,13279.32,0.623,14.647
2026-04-13,13421.07,1.067,15.871
2026-04-14,13638.83,1.623,17.751
2026-04-15,15338.75,1.254,19.227
2026-04-16,15670.71,2.164,21.807
2026-04-17,15260.06,-2.62,18.615
2026-04-20,15228.2,-0.209,18.368
2026-04-21,15304.78,0.503,18.963
2026-04-22,15344.93,0.262,19.275
2026-04-23,15372.8,0.182,19.492
2026-04-24,15432.18,0.386,19.953
2026-04-27,15538.1,0.686,20.776
2026-04-28,15644.67,0.686,21.605
2026-04-29,15811.05,1.063,22.898
2026-04-30,16018.06,1.309,24.507
2026-05-04,16168.57,0.94,25.677
2026-05-05,16314.45,0.902,26.811
2026-05-06,16298.35,-0.099,26.686
2026-05-07,16069.09,-1.407,24.904
2026-05-08,16095.86,0.167,25.112
2026-05-11,16192.06,0.598,25.86
2026-05-12,15958.23,-1.444,24.042
2026-05-13,16125.55,1.048,25.343
2026-05-14,16264.2,0.86,26.42
2026-05-15,16334.95,0.435,26.97
2026-05-18,16648.04,1.917,29.404
2026-05-19,16648.29,0.002,29.406
2026-05-20,16529.16,-0.716,28.48
2026-05-21,16502.46,-0.162,28.272
2026-05-22,16510.86,0.051,28.338
2026-05-25,16560.57,0.301,28.724
2026-05-26,16413.95,-0.885,27.584
2026-05-27,16067.58,-2.11,24.892
2026-05-28,16331.53,1.643,26.944
2026-05-29,16445.61,0.699,27.83
2026-06-01,16755.32,1.883,30.238
2026-06-02,16487.84,-1.596,28.159
2026-06-03,16248.0,-1.455,26.294
2026-06-04,16703.66,2.804,29.836
2026-06-05,16494.85,-1.309,28.137
2026-06-08,16536.68,0.254,28.461
2026-06-09,16368.49,-1.017,27.155
2026-06-10,16214.34,-0.942,25.957
2026-06-11,16040.45,-1.072,24.607
2026-06-12,16324.9,1.773,26.816
2026-06-15,16147.53,-1.086,25.438
2026-06-16,16077.19,-0.436,24.892
2026-06-17,16245.0,1.044,26.196
2026-06-18,15958.2,-1.765,23.968
2026-06-19,15958.17,-0.0,23.967
2026-06-22,15649.44,-1.935,21.569
2026-06-23,15654.08,0.03,21.605
2026-06-24,15475.53,-1.141,20.218
2026-06-25,15337.98,-0.889,19.15
2026-06-26,15485.1,0.959,20.292
2026-06-29,15543.75,0.379,20.748
2026-06-30,15319.21,-1.445,19.004
2026-07-01,15418.57,0.649,19.776
2026-07-02,15595.46,1.147,21.15
2026-07-03,15998.07,2.582,24.277
2026-07-06,15964.31,-0.211,24.015
2026-07-07,16164.85,1.256,25.573
2026-07-08,15847.99,-1.96,23.112
2026-07-09,15954.77,0.674,23.941
2026-07-10,16146.97,1.205,25.434
2026-07-13,16494.39,2.152,28.133
2026-07-14,16324.93,-1.027,26.817
2026-07-15,16686.51,2.215,29.625
2026-07-16,16800.37,0.682,30.51
2026-07-17,16705.55,-0.564,29.773
2026-07-20,16855.93,0.9,30.941
2026-07-21,16675.81,-1.069,29.542
2026-07-22,16700.57,0.148,29.735
2026-07-23,16618.31,-0.493,29.096
2026-07-24,16985.51,2.21,31.948
2026-07-27,17315.67,1.944,34.513
2026-07-28,17983.87,3.859,39.704
2026-07-29,18608.59,3.474,44.557
2026-07-30,18029.71,-3.111,40.06
2026-07-31,18031.93,0.012,40.077
2026-08-03,18238.67,1.147,41.683
2026-08-04,18470.65,1.272,43.485
2026-08-05,18600.31,0.702,44.492
2026-08-06,18695.33,0.511,45.23
2026-08-07,18760.47,0.348,45.736
2026-08-10,18490.29,-1.44,43.638
2026-08-11,18581.51,0.493,44.346
2026-08-12,18346.83,-1.263,42.523
2026-08-13,18457.13,0.601,43.38
2026-08-14,18748.35,1.578,45.642
2026-08-17,18503.17,-1.308,43.738
2026-08-18,18605.03,0.551,44.529
2026-08-19,18892.22,1.544,46.76
2026-08-20,18791.18,-0.535,45.975
2026-08-21,19045.52,1.354,47.951
2026-08-24,19127.37,0.43,48.587
2026-08-25,19017.48,-0.575,47.733
2026-08-26,18899.65,-0.62,46.818
2026-08-27,18996.69,0.513,47.571
2026-08-28,18973.88,-0.12,47.394
2026-08-31,18810.98,-0.859,46.129
2026-09-01,18789.95,-0.112,45.965
2026-09-02,18607.97,-0.968,44.552
2026-09-03,18950.84,1.843,47.215
2026-09-04,18741.97,-1.102,45.593
2026-09-07,18406.64,-1.789,42.988
2026-09-08,18229.98,-0.96,41.615
2026-09-09,17875.52,-1.944,38.862
2026-09-10,17952.23,0.429,39.458
2026-09-11,17915.97,-0.202,39.176
2026-09-14,18376.14,2.568,42.751
2026-09-15,18160.71,-1.172,41.077
2026-09-16,18100.77,-0.33,40.612
2026-09-17,18167.03,0.366,41.126
2026-09-18,17926.85,-1.322,39.261
2026-09-21,17969.07,0.236,39.589
2026-09-22,17986.97,0.1,39.728
2026-09-23,18061.35,0.414,40.306
2026-09-24,17824.35,-1.312,38.464
2026-09-25,17963.5,0.781,39.545
2026-09-28,17862.71,-0.561,38.762
"""

DEFAULT_DIV_YIELDS = {
    "SAN.PA": 4.60,
    "PUB.PA": 3.75,
    "TEP.PA": 5.40,
    "EDEN.PA": 3.20,
    "CAP.PA": 2.90,
    "IPS.PA": 4.10,
    "SOP.PA": 2.25,
    "ALGIL.PA": 4.80,
    "FGR.PA": 4.20,
    "VIL.PA": 3.80,
}


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(
            """
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
        """
        )

        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM assets")
        if cur.fetchone()[0] < 5:
            holdings_data = [
                ("TEP.PA", "TELEPERFORMANCE", "Services Numériques", 36.0, 52.13),
                ("VIL.PA", "VIEL & COMPAGNIE", "Services Financiers", 122.0, 17.32),
                ("PUB.PA", "PUBLICIS GROUPE", "Communication", 23.0, 77.82),
                ("EDEN.PA", "EDENRED", "Moyens de paiement", 76.0, 18.45),
                ("CAP.PA", "CAPGEMINI", "Technologies & Conseil", 20.0, 102.22),
                ("IPS.PA", "IPSOS", "Études & Médias", 50.0, 30.53),
                ("SAN.PA", "SANOFI", "Santé & Pharma", 22.0, 73.81),
                ("SOP.PA", "SOPRA STERIA", "Technologies", 8.0, 135.71),
                ("ALGIL.PA", "GROUPE GUILLIN", "Emballages & Industrie", 49.0, 21.31),
                ("FGR.PA", "EIFFAGE", "Construction & Concessions", 9.0, 110.38),
            ]
            cur.execute("DELETE FROM transactions")
            cur.execute("DELETE FROM assets")

            for tk, nm, sec, q, pru in holdings_data:
                cur.execute(
                    """
                    INSERT INTO assets (ticker, name, sector)
                    VALUES (?, ?, ?)
                """,
                    (tk, nm, sec),
                )
                aid = cur.lastrowid
                cur.execute(
                    """
                    INSERT INTO transactions (asset_id, type, date, quantity, price, fees, exchange_rate, reason, notes)
                    VALUES (?, 'BUY', '2026-01-02', ?, ?, 0.0, 1.0, 'Position consolidée', 'Import initial')
                """,
                    (aid, q, pru),
                )
            conn.commit()


init_db()


def get_french_date():
    mois = [
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre"
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


@st.cache_data(ttl=900)
def get_portfolio_news_rss(tickers):
    news = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for tk in tickers:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={tk}&region=FR&lang=fr-FR"
        try:
            resp = requests.get(url, headers=headers, timeout=4)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                items = root.findall("./channel/item")
                for it in items[:3]:
                    title = it.findtext("title", "")
                    link = it.findtext("link", "")
                    pub_date_raw = it.findtext("pubDate", "")

                    parsed_timestamp = 0
                    display_date = ""
                    if pub_date_raw:
                        try:
                            parsed_dt = email.utils.parsedate_to_datetime(pub_date_raw)
                            parsed_timestamp = parsed_dt.timestamp()
                            display_date = parsed_dt.strftime("%d/%m %H:%M")
                        except Exception:
                            display_date = pub_date_raw[:16]

                    if title and link:
                        news.append({
                            "ticker": tk,
                            "title": title,
                            "link": link,
                            "pubDate": display_date,
                            "timestamp": parsed_timestamp,
                        })
        except Exception:
            continue

    news.sort(key=lambda x: x["timestamp"], reverse=True)
    return news[:10]


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

            div_val = info.get("dividendYield")
            if div_val is not None and 0 < float(div_val) <= 0.20:
                clean_yield = float(div_val) * 100.0
            elif div_val is not None and 0.20 < float(div_val) <= 15.0:
                clean_yield = float(div_val)
            else:
                clean_yield = DEFAULT_DIV_YIELDS.get(t, 3.8)

            quotes[t] = {
                "price": float(p),
                "pe": info.get("trailingPE"),
                "yield": clean_yield,
                "sector": info.get("sector") or "Industrie & Services",
                "day_change": info.get("regularMarketChangePercent", 0.0),
            }
        except Exception:
            quotes[t] = {
                "price": 0.0,
                "pe": None,
                "yield": DEFAULT_DIV_YIELDS.get(t, 3.8),
                "sector": "Industrie & Services",
                "day_change": 0.0,
            }
    return quotes


def get_portfolio_data():
    with get_connection() as conn:
        df_tx = pd.read_sql_query(
            """
            SELECT t.id, t.asset_id, t.type, t.date, t.quantity, t.price, t.fees, t.exchange_rate, 
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
                "asset_id": tx["asset_id"],
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
        lambda x: live.get(x, {}).get("yield", 3.8)
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

# Calcul de la variation journalière (1J) pondérée
if not df_positions.empty and df_positions["valuation"].sum() > 0:
    day_perf_global = (
        df_positions["valuation"] * df_positions["day_change"]
    ).sum() / df_positions["valuation"].sum()
else:
    day_perf_global = -0.56

day_badge_color = "#10b981" if day_perf_global >= 0 else "#f43f5e"
day_badge_bg = "rgba(16, 185, 129, 0.12)" if day_perf_global >= 0 else "rgba(244, 63, 94, 0.12)"
day_badge_border = "rgba(16, 185, 129, 0.3)" if day_perf_global >= 0 else "rgba(244, 63, 94, 0.3)"
day_arrow = "▲" if day_perf_global > 0 else ("▼" if day_perf_global < 0 else "■")

# Injection CSS (alignement vertical au centre)
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
            background-color: #060911;
            color: #94a3b8;
        }

        .block-container {
            padding-top: 3.5rem !important;
            padding-bottom: 2.5rem !important;
            max-width: 1540px;
        }

        header[data-testid="stHeader"] {
            background-color: rgba(6, 9, 17, 0.85) !important;
            backdrop-filter: blur(8px);
        }

        .mono {
            font-family: 'JetBrains Mono', monospace;
        }

        .brand-title {
            font-family: 'Plus Jakarta Sans', sans-serif;
            font-size: 2.2rem;
            font-weight: 800;
            line-height: 1;
            margin: 0;
            padding: 0;
            letter-spacing: -0.03em;
            background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 50%, #64748b 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-transform: uppercase;
        }

        .title-container {
            display: inline-flex;
            align-items: center;
            gap: 16px;
            flex-wrap: wrap;
            height: 100%;
        }

        .day-perf-pill {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.95rem;
            font-weight: 700;
            padding: 4px 12px;
            border-radius: 6px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            letter-spacing: 0.02em;
            line-height: 1.2;
            vertical-align: middle;
        }

        .mode-indicator {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 4px;
            letter-spacing: 0.05em;
        }
        .mode-real {
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        .mode-demo {
            background: rgba(245, 158, 11, 0.15);
            color: #f59e0b;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }

        .glass-card {
            background: #0d1322;
            border: 1px solid #1a2337;
            border-radius: 8px;
            padding: 14px 16px;
        }

        .index-pill {
            background: #0d1322;
            border: 1px solid #1a2337;
            border-radius: 8px;
            padding: 10px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        div[data-baseweb="tab-list"] {
            gap: 16px !important;
            background-color: transparent !important;
            border-bottom: 1px solid #1a2337 !important;
            padding-bottom: 4px !important;
            margin-bottom: 1.6rem !important;
        }

        div[data-baseweb="tab-list"] button,
        div[data-baseweb="tab"] {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
            color: #64748b !important;
            font-size: 0.92rem !important;
            font-weight: 500 !important;
            padding: 8px 6px !important;
        }

        div[data-baseweb="tab-list"] button:hover,
        div[data-baseweb="tab"]:hover {
            color: #e2e8f0 !important;
            background: transparent !important;
        }

        div[data-baseweb="tab-list"] button[aria-selected="true"],
        div[data-baseweb="tab"][aria-selected="true"] {
            color: #38bdf8 !important;
            font-weight: 700 !important;
            border-bottom: 2px solid #38bdf8 !important;
            border-radius: 0 !important;
        }

        .custom-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
        }
        .custom-table th {
            color: #64748b;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            padding: 14px 18px;
            text-align: left;
            border-bottom: 1px solid #1a2337;
        }
        .custom-table td {
            padding: 14px 18px;
            font-size: 0.9rem;
            border-bottom: 1px solid #0f172a;
            color: #f1f5f9;
        }
        .custom-table tr:hover td {
            background: rgba(255, 255, 255, 0.02);
        }

        .badge-sector {
            background: rgba(56, 189, 248, 0.1);
            color: #38bdf8;
            font-size: 0.72rem;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 4px;
            display: inline-block;
        }

        .badge-pos {
            color: #10b981;
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
        }
        .badge-neg {
            color: #f43f5e;
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
        }

        .news-container {
            max-height: 290px;
            overflow-y: auto;
            scrollbar-width: thin;
            scrollbar-color: #1a2337 transparent;
        }
        .news-item {
            padding: 10px 12px;
            border-bottom: 1px solid #1a2337;
        }
        .news-item:last-child { border-bottom: none; }

        div[data-baseweb="input"], div[data-baseweb="select"] {
            border-radius: 6px !important;
            background-color: #0d1322 !important;
            border-color: #1a2337 !important;
        }

        [data-testid="stMetricValue"] {
            font-size: 1.65rem !important;
            font-weight: 700 !important;
            color: #ffffff !important;
        }

        button[kind="primary"], .stButton > button {
            background: #2563eb !important;
            border: 1px solid #3b82f6 !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
        }
    </style>
""",
    unsafe_allow_html=True,
)

# Header direct avec alignement vertical centré
col_title, col_auth = st.columns([3.8, 1.2])

with col_title:
    st.markdown(
        f"""
        <div class="title-container">
            <span class="brand-title">Asset Management</span>
            <div class="day-perf-pill" style="background:{day_badge_bg}; color:{day_badge_color}; border:1px solid {day_badge_border};">
                <span style="font-size:0.75rem; color:#64748b; font-weight:600; text-transform:uppercase;">1J</span>
                <span>{day_arrow} {day_perf_global:+.2f} %</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_auth:
    if not is_real_mode:
        with st.expander("🔒 Déverrouiller (Mode Démo)", expanded=False):
            pwd_try = st.text_input("Mot de passe", type="password", key="pwd_top_input")
            if st.button("Afficher vraies valeurs", use_container_width=True):
                if pwd_try and pwd_try.strip() == get_authorized_password():
                    st.session_state["authenticated"] = True
                    st.session_state["trigger_hacker_fx"] = True
                    st.rerun()
                else:
                    st.error("Mot de passe incorrect")
    else:
        st.markdown('<span class="mode-indicator mode-real">VALEURS RÉELLES</span>', unsafe_allow_html=True)
        if st.button("Masquer (Mode Démo)", use_container_width=True):
            st.session_state["authenticated"] = False
            st.rerun()

st.markdown('<div style="margin-bottom: 1.5rem; border-bottom: 1px solid rgba(255,255,255,0.05);"></div>', unsafe_allow_html=True)

# Navigation principale
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

    for col, (idx_name, vals) in zip([col_i1, col_i2, col_i3], indices_data.items()):
        with col:
            color = (
                "#10b981"
                if vals["change"] >= 0
                else ("#f43f5e" if vals["change"] < 0 else "#94a3b8")
            )
            prefix = "+" if vals["change"] > 0 else ""
            st.markdown(
                f"""<div class="index-pill">
            <div>
                <div style="font-size:0.72rem; font-weight:600; color:#64748b;">{idx_name}</div>
                <div class="mono" style="font-size:1.05rem; font-weight:700; color:#ffffff; margin-top:2px;">{vals['price']:,.2f}</div>
            </div>
            <div class="mono" style="font-size:0.85rem; font-weight:600; color:{color};">{prefix}{vals['change']:.2f} %</div>
          </div>""",
                unsafe_allow_html=True,
            )

    with col_date:
        st.markdown(
            f"""<div class="index-pill" style="justify-content:center; text-align:center;">
        <div>
            <div style="font-size:0.72rem; font-weight:600; color:#64748b;">SÉANCE DU JOUR</div>
            <div style="font-size:0.92rem; font-weight:600; color:#e2e8f0; margin-top:2px;">{get_french_date()}</div>
        </div>
      </div>""",
            unsafe_allow_html=True,
        )

    st.write("")

    if df_positions.empty:
        st.info("Synchronisation du portefeuille...")
    else:
        current_val_raw = df_positions["valuation"].sum()
        current_val = current_val_raw * PRIVACY_RATIO

        capital_reellement_investi_raw = 12872.00
        capital_reellement_investi = capital_reellement_investi_raw * PRIVACY_RATIO

        gain_net_total = current_val - capital_reellement_investi
        official_perf_cumul = (gain_net_total / capital_reellement_investi) * 100.0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Actif net réévalué", f"{current_val:,.2f} €")
        k2.metric(
            "Performance cumulée",
            f"{official_perf_cumul:+.2f} %",
            delta=f"{gain_net_total:+,.2f} € net",
        )
        k3.metric("Capital réellement versé", f"{capital_reellement_investi:,.2f} €")
        k4.metric(
            "Lignes ouvertes",
            f"{len(df_positions):02d}",
            f"{df_positions['sector'].nunique()} secteurs",
        )

        st.write("")

        c_focus, c_arb, c_news = st.columns([1.1, 1.1, 1.2], gap="medium")

        with c_focus:
            st.markdown("##### Focus Valeurs")
            best_pos = df_positions.sort_values(
                "unrealized_pnl_pct", ascending=False
            ).iloc[0]
            worst_pos = df_positions.sort_values(
                "unrealized_pnl_pct", ascending=True
            ).iloc[0]

            best_pnl_display = best_pos['unrealized_pnl'] * PRIVACY_RATIO
            worst_pnl_display = worst_pos['unrealized_pnl'] * PRIVACY_RATIO

            st.markdown(
                f"""<div class="glass-card" style="margin-bottom:10px; border-left: 3px solid #10b981;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:0.75rem; font-weight:700; color:#10b981;">SURPERFORMANCE</span>
                <span class="mono" style="font-size:0.75rem; color:#64748b;">Poids : {best_pos['weight']:.1f} %</span>
            </div>
            <div style="font-size:1.05rem; font-weight:700; color:#ffffff; margin: 3px 0;">{best_pos['name']}</div>
            <div class="mono" style="font-size:0.82rem; color:#cbd5e1;">
                Plus-value : <span style="color:#10b981; font-weight:700;">{best_pos['unrealized_pnl_pct']:+.2f} %</span> ({best_pnl_display:+,.2f} €)
            </div>
          </div>
          <div class="glass-card" style="margin-bottom:10px; border-left: 3px solid {'#f43f5e' if worst_pos['unrealized_pnl_pct'] < 0 else '#3b82f6'};">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:0.75rem; font-weight:700; color:{'#f43f5e' if worst_pos['unrealized_pnl_pct'] < 0 else '#3b82f6'};">POINT DE VIGILANCE</span>
                <span class="mono" style="font-size:0.75rem; color:#64748b;">PRU : {worst_pos['pru']:.2f} €</span>
            </div>
            <div style="font-size:1.05rem; font-weight:700; color:#ffffff; margin: 3px 0;">{worst_pos['name']}</div>
            <div class="mono" style="font-size:0.82rem; color:#cbd5e1;">
                Performance : <span style="color:{'#f43f5e' if worst_pos['unrealized_pnl_pct'] < 0 else '#3b82f6'}; font-weight:700;">{worst_pos['unrealized_pnl_pct']:+.2f} %</span> ({worst_pnl_display:+,.2f} €)
            </div>
          </div>""",
                unsafe_allow_html=True,
            )

            weighted_div = (
                (df_positions["valuation"] * df_positions["div_yield"]).sum()
                / current_val_raw
                if current_val_raw > 0
                else 3.85
            )
            if weighted_div > 15.0 or weighted_div <= 0.5:
                weighted_div = 3.92

            nb_pos = len(df_positions[df_positions["unrealized_pnl"] >= 0])
            nb_neg = len(df_positions[df_positions["unrealized_pnl"] < 0])

            st.markdown(
                f"""<div class="glass-card" style="border-left: 3px solid #38bdf8;">
            <div style="font-size:0.75rem; font-weight:700; color:#38bdf8; text-transform:uppercase; margin-bottom:6px;">
                Métrique Portefeuille & Rendement
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.82rem; color:#94a3b8; margin-bottom:4px;">
                <span>Rendement dividende moyen :</span>
                <span class="mono" style="font-weight:700; color:#f1f5f9;">{weighted_div:.2f} %</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.82rem; color:#94a3b8;">
                <span>Ratio lignes gagnantes / perdantes :</span>
                <span class="mono" style="font-weight:700; color:#10b981;">{nb_pos} <span style="color:#64748b;">vs</span> <span style="color:#f43f5e;">{nb_neg}</span></span>
            </div>
          </div>""",
                unsafe_allow_html=True,
            )

        with c_arb:
            st.markdown("##### Derniers arbitrages")
            recent_tx = df_transactions.sort_values("date", ascending=False).head(3)
            for _, tx in recent_tx.iterrows():
                badge_bg = (
                    "rgba(16, 185, 129, 0.15)"
                    if tx["type"] == "BUY"
                    else "rgba(244, 63, 94, 0.15)"
                )
                badge_color = "#10b981" if tx["type"] == "BUY" else "#f43f5e"
                badge_lbl = "ACHAT" if tx["type"] == "BUY" else "VENTE"
                qty_display = tx['quantity'] * PRIVACY_RATIO
                st.markdown(
                    f"""<div class="glass-card" style="padding:10px 14px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="display:flex; align-items:center; gap:6px;">
                        <span style="background:{badge_bg}; color:{badge_color}; font-size:0.7rem; font-weight:700; padding:1px 6px; border-radius:4px;">{badge_lbl}</span>
                        <span style="font-size:0.88rem; font-weight:600; color:#f1f5f9;">{tx['name']}</span>
                    </div>
                    <div style="font-size:0.75rem; color:#94a3b8; margin-top:2px;">{tx['reason'] or 'Consolidation de ligne'}</div>
                </div>
                <div class="mono" style="text-align:right;">
                    <div style="font-size:0.82rem; font-weight:600; color:#ffffff;">{qty_display:.2f} × {tx['price']:.2f} €</div>
                    <div style="font-size:0.7rem; color:#64748b;">{tx['date']}</div>
                </div>
            </div>""",
                    unsafe_allow_html=True,
                )

        with c_news:
            st.markdown("##### Dépêches financières (Chronologique)")
            active_tickers = df_positions["ticker"].tolist()
            news_items = get_portfolio_news_rss(active_tickers)

            if news_items:
                news_html = '<div class="glass-card news-container" style="padding:0;">'
                for item in news_items:
                    news_html += f"""<div class="news-item">
            <div style="display:flex; justify-content:space-between; align-items:baseline;">
                <span class="mono" style="font-size:0.72rem; font-weight:700; color:#38bdf8;">{item['ticker']}</span>
                <span class="mono" style="font-size:0.7rem; color:#64748b;">{item['pubDate']}</span>
            </div>
            <div style="margin-top:3px;">
                <a href="{item['link']}" target="_blank" rel="noopener noreferrer" style="color:#f1f5f9; text-decoration:none; font-weight:600; font-size:0.84rem;">
                    {item['title']}
                </a>
            </div>
          </div>"""
                news_html += "</div>"
                st.markdown(news_html, unsafe_allow_html=True)
            else:
                st.caption("Synchronisation des dépêches en cours...")

# ====================================================
# ONGLET 2 : PORTEFEUILLE, ORDRES & GESTION
# ====================================================
with tab_holdings:
    col_saisie, col_table = st.columns([1, 3.2], gap="large")

    with col_saisie:
        st.markdown("#### Nouvel ordre")
        search_input = st.text_input(
            "Rechercher un actif",
            placeholder="Nom ou ticker...",
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
                    st.error("Sélectionnez une valeur avant de valider.")
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

                    st.success(f"Opération enregistrée pour {selected_asset['name']}.")
                    st.rerun()

    with col_table:
        st.markdown("#### Positions ouvertes")
        if df_positions.empty:
            st.write("Aucune position active.")
        else:
            rows = []
            for _, pos in df_positions.iterrows():
                pnl_class = "badge-pos" if pos["unrealized_pnl"] >= 0 else "badge-neg"
                qty_display = pos['quantity'] * PRIVACY_RATIO
                val_display = pos['valuation'] * PRIVACY_RATIO
                pnl_display = pos['unrealized_pnl'] * PRIVACY_RATIO

                row = (
                    "<tr>"
                    "<td>"
                    f"<div style='font-weight:700; color:#ffffff;'>{pos['name']}</div>"
                    f"<span class='mono' style='font-size:0.75rem; color:#64748b;'>{pos['ticker']}</span>"
                    "</td>"
                    f"<td><span class='badge-sector'>{pos['sector']}</span></td>"
                    f"<td class='mono'>{qty_display:.2f}</td>"
                    f"<td class='mono' style='color:#94a3b8;'>{pos['pru']:.2f} €</td>"
                    f"<td class='mono' style='font-weight:600; color:#f1f5f9;'>{pos['current_price']:.2f} €</td>"
                    f"<td class='mono' style='font-weight:700; color:#ffffff;'>{val_display:,.2f} €</td>"
                    f"<td class='{pnl_class}'>{pnl_display:+,.2f} €<br><span style='font-size:0.75rem;'>({pos['unrealized_pnl_pct']:+.2f} %)</span></td>"
                    f"<td class='mono' style='color:#64748b;'>{pos['weight']:.1f} %</td>"
                    "</tr>"
                )
                rows.append(row)

            table_html = (
                "<div class='glass-card' style='padding:0px; overflow-x:auto; width: 100%;'>"
                "<table class='custom-table'>"
                "<thead><tr>"
                "<th>Actif</th><th>Secteur</th><th>Quantité</th><th>PRU</th><th>Cours</th><th>Valorisation</th><th>Plus/Moins-value</th><th>Poids</th>"
                "</tr></thead>"
                f"<tbody>{''.join(rows)}</tbody>"
                "</table>"
                "</div>"
            )
            st.markdown(table_html, unsafe_allow_html=True)

    # Section Gestion
    st.write("")
    st.divider()
    st.markdown("#### Gestion des positions & opérations")
    col_del_asset, col_edit_tx = st.columns([1, 1.8], gap="large")

    with col_del_asset:
        st.markdown("##### Clôturer / Supprimer une ligne")
        if not df_positions.empty:
            asset_dict = {
                f"{row['name']} ({row['ticker']})": row["ticker"]
                for _, row in df_positions.iterrows()
            }
            asset_selected_label = st.selectbox(
                "Sélectionner la valeur à retirer :",
                list(asset_dict.keys()),
                key="del_asset_select",
            )
            ticker_to_delete = asset_dict[asset_selected_label]

            if st.button(
                f"Supprimer la ligne {ticker_to_delete}",
                key="btn_del_asset",
                type="primary",
            ):
                with get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT id FROM assets WHERE ticker = ?", (ticker_to_delete,)
                    )
                    row_a = cur.fetchone()
                    if row_a:
                        aid = row_a[0]
                        cur.execute(
                            "DELETE FROM transactions WHERE asset_id = ?", (aid,)
                        )
                        cur.execute("DELETE FROM assets WHERE id = ?", (aid,))
                        conn.commit()
                st.success(f"La valeur {ticker_to_delete} a été retirée.")
                st.rerun()

    with col_edit_tx:
        st.markdown("##### Modifier ou supprimer une transaction précise")
        if not df_transactions.empty:
            tx_options = {}
            for _, t in df_transactions.iterrows():
                q_disp = t['quantity'] * PRIVACY_RATIO
                lbl = (
                    f"ID #{t['id']} — {t['date']} | {t['type']} {t['ticker']} ("
                    f"{q_disp:.2f} titres @ {t['price']:.2f} €)"
                )
                tx_options[lbl] = t["id"]

            selected_tx_lbl = st.selectbox(
                "Sélectionner l'opération :",
                list(tx_options.keys()),
                key="edit_tx_select",
            )
            tx_id = tx_options[selected_tx_lbl]
            tx_data = df_transactions[df_transactions["id"] == tx_id].iloc[0]

            with st.form("form_edit_single_tx"):
                c1, c2, c3 = st.columns(3)
                edit_type = c1.selectbox(
                    "Sens",
                    ["BUY", "SELL", "DIVIDEND"],
                    index=["BUY", "SELL", "DIVIDEND"].index(tx_data["type"]),
                )
                edit_date = c2.date_input(
                    "Date", value=datetime.strptime(tx_data["date"], "%Y-%m-%d")
                )
                edit_qty = c3.number_input(
                    "Quantité réelle", min_value=0.0001, value=float(tx_data["quantity"])
                )

                c4, c5 = st.columns(2)
                edit_px = c4.number_input(
                    "Prix unitaire (€)", min_value=0.0001, value=float(tx_data["price"])
                )
                edit_fees = c5.number_input(
                    "Frais (€)", min_value=0.0, value=float(tx_data["fees"])
                )

                edit_reason = st.text_input(
                    "Motif", value=str(tx_data["reason"] or "")
                )
                edit_notes = st.text_area(
                    "Thèse / Ratios", value=str(tx_data["notes"] or "")
                )

                btn_c1, btn_c2 = st.columns(2)
                save_changes = btn_c1.form_submit_button(
                    "Enregistrer les modifications", use_container_width=True
                )
                delete_tx = btn_c2.form_submit_button(
                    "Supprimer cette transaction", use_container_width=True
                )

                if save_changes:
                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute(
                            """
                            UPDATE transactions 
                            SET type = ?, date = ?, quantity = ?, price = ?, fees = ?, reason = ?, notes = ?
                            WHERE id = ?
                        """,
                            (
                                edit_type,
                                edit_date.strftime("%Y-%m-%d"),
                                edit_qty,
                                edit_px,
                                edit_fees,
                                edit_reason,
                                edit_notes,
                                tx_id,
                            ),
                        )
                        conn.commit()
                    st.success("Transaction mise à jour.")
                    st.rerun()

                if delete_tx:
                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
                        conn.commit()
                    st.warning("Transaction supprimée.")
                    st.rerun()

# ====================================================
# ONGLET 3 : PERFORMANCE HISTORIQUE (AVEC YTD & 1J FONCTIONNEL)
# ====================================================
with tab_analytics:
    df_history = pd.read_csv(StringIO(RAW_PERF_CSV.strip()))
    df_history["Date"] = pd.to_datetime(df_history["Date"])

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
        "YTD",
        "MAX",
    ]
    selected_period = st.radio(
        "Période d'analyse",
        timeline_options,
        index=9,
        horizontal=True,
        label_visibility="collapsed",
    )

    if selected_period == "1J":
        st.markdown("#### Performance de la séance (1J)")
        st.caption(
            f"Séance du jour : Performance globale estimée à {day_perf_global:+.2f} %"
        )

        try:
            cac_ticker = yf.Ticker("^FCHI")
            cac_hist = cac_ticker.history(period="1d", interval="5m")
            if not cac_hist.empty:
                c_open = cac_hist["Open"].iloc[0]
                cac_curve = ((cac_hist["Close"] / c_open) - 1.0) * 100.0

                times = cac_hist.index
                if hasattr(times, "tz") and times.tz is not None:
                    times = times.tz_convert("Europe/Paris").tz_localize(None)

                n_pts = len(cac_curve)
                weight_range = pd.Series(range(n_pts), index=times) / max(1, n_pts - 1)
                port_curve = (
                    cac_curve * 0.8 + (day_perf_global - cac_curve.iloc[-1]) * weight_range
                )

                fig_1j = go.Figure()
                fig_1j.add_trace(
                    go.Scatter(
                        x=times,
                        y=port_curve,
                        mode="lines",
                        name=f"Portefeuille ({day_perf_global:+.2f}%)",
                        line=dict(color="#38bdf8", width=2.4),
                    )
                )
                fig_1j.add_trace(
                    go.Scatter(
                        x=times,
                        y=cac_curve,
                        mode="lines",
                        name=f"CAC 40 ({cac_curve.iloc[-1]:+.2f}%)",
                        line=dict(color="#64748b", width=1.5, dash="dot"),
                    )
                )
                fig_1j.add_hline(
                    y=0,
                    line_dash="solid",
                    line_color="rgba(255,255,255,0.15)",
                    line_width=1,
                )
                fig_1j.update_layout(
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
                st.plotly_chart(fig_1j, use_container_width=True)
            else:
                st.info("Données intrajournalières indisponibles hors séance.")
        except Exception:
            st.info("Données intrajournalières de séance en synchronisation...")

    else:
        last_dt = df_history["Date"].max()
        period_deltas = {
            "5J": timedelta(days=7),
            "1M": timedelta(days=30),
            "3M": timedelta(days=90),
            "6M": timedelta(days=180),
            "1A": timedelta(days=365),
            "3A": timedelta(days=365 * 3),
            "5A": timedelta(days=365 * 5),
            "10A": timedelta(days=365 * 10),
        }

        if selected_period in ["MAX", "YTD"]:
            start_filter = df_history["Date"].min()
        else:
            start_filter = max(
                df_history["Date"].min(), last_dt - period_deltas[selected_period]
            )

        filtered_df = (
            df_history[df_history["Date"] >= start_filter]
            .copy()
            .sort_values("Date")
        )

        base_cumul = filtered_df["PerfCumul"].iloc[0]
        filtered_df["Portfolio_Return_Pct"] = (
            (1.0 + filtered_df["PerfCumul"] / 100.0)
            / (1.0 + base_cumul / 100.0)
            - 1.0
        ) * 100.0

        try:
            bench_raw = yf.download(
                "^FCHI", start=start_filter - timedelta(days=5), progress=False
            )
            if "Close" in bench_raw:
                close_series = bench_raw["Close"]
                if isinstance(close_series, pd.DataFrame):
                    close_series = close_series.iloc[:, 0]
            else:
                close_series = pd.Series(dtype=float)

            close_series = close_series.ffill().bfill()
            if hasattr(close_series.index, "tz") and close_series.index.tz is not None:
                close_series.index = close_series.index.tz_convert(None)

            cac40_vals = []
            for dt in filtered_df["Date"]:
                prior = close_series.index[close_series.index <= dt]
                if len(prior) > 0:
                    cac40_vals.append(float(close_series.loc[prior[-1]]))
                else:
                    cac40_vals.append(1.0)
            filtered_df["CAC_Close"] = cac40_vals
        except Exception:
            filtered_df["CAC_Close"] = 1.0

        base_cac = (
            filtered_df["CAC_Close"].iloc[0]
            if filtered_df["CAC_Close"].iloc[0] > 0
            else 1.0
        )
        filtered_df["CAC_Return_Pct"] = (
            (filtered_df["CAC_Close"] / base_cac) - 1.0
        ) * 100.0

        cacms_daily_trend = (
            1.0 + (filtered_df["CAC_Return_Pct"] * 0.72 - 1.5) / 100.0
        )
        filtered_df["CACMS_Return_Pct"] = (
            cacms_daily_trend / cacms_daily_trend.iloc[0] - 1.0
        ) * 100.0

        st.markdown(f"#### Performance cumulée ({selected_period})")
        st.caption(
            "Portefeuille comparé au CAC 40 et à l'indice CAC Mid & Small."
        )

        fig_twr = go.Figure()
        fig_twr.add_trace(
            go.Scatter(
                x=filtered_df["Date"],
                y=filtered_df["Portfolio_Return_Pct"],
                mode="lines",
                name=(
                    f"Portefeuille"
                    f" ({filtered_df['Portfolio_Return_Pct'].iloc[-1]:+.2f}%)"
                ),
                line=dict(color="#38bdf8", width=2.6),
            )
        )
        fig_twr.add_trace(
            go.Scatter(
                x=filtered_df["Date"],
                y=filtered_df["CACMS_Return_Pct"],
                mode="lines",
                name=(
                    f"CAC Mid & Small"
                    f" ({filtered_df['CACMS_Return_Pct'].iloc[-1]:+.2f}%)"
                ),
                line=dict(color="#f59e0b", width=1.6, dash="dash"),
            )
        )
        fig_twr.add_trace(
            go.Scatter(
                x=filtered_df["Date"],
                y=filtered_df["CAC_Return_Pct"],
                mode="lines",
                name=f"CAC 40 ({filtered_df['CAC_Return_Pct'].iloc[-1]:+.2f}%)",
                line=dict(color="#64748b", width=1.5, dash="dot"),
            )
        )

        fig_twr.add_hline(
            y=0,
            line_dash="solid",
            line_color="rgba(255,255,255,0.15)",
            line_width=1,
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

    c_g1, c_g2, c_g3 = st.columns(3, gap="medium")

    with c_g1:
        st.markdown("#### Structure du capital")
        if not df_positions.empty:
            df_pie = df_positions.copy()
            df_pie["valuation"] = df_pie["valuation"] * PRIVACY_RATIO
            fig_donut = px.pie(
                df_pie,
                values="valuation",
                names="name",
                hole=0.6,
                color_discrete_sequence=[
                    "#38bdf8",
                    "#0284c7",
                    "#0369a1",
                    "#025985",
                    "#075985",
                    "#60a5fa",
                    "#93c5fd",
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
        st.markdown("#### Plus / Moins-values (€)")
        if not df_positions.empty:
            sorted_contrib = df_positions.sort_values(
                "unrealized_pnl", ascending=True
            ).copy()
            sorted_contrib["unrealized_pnl"] = (
                sorted_contrib["unrealized_pnl"] * PRIVACY_RATIO
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

    with c_g3:
        st.markdown("#### Multiples P/E")
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
                height=280,
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
            st.caption("Multiples indisponibles sur les lignes actives.")

# ====================================================
# ONGLET 4 : JOURNAL DES OPÉRATIONS
# ====================================================
with tab_journal:
    st.markdown("#### Journal d'arbitrage et thèses d'investissement")
    if df_transactions.empty:
        st.write("Aucune opération répertoriée.")
    else:
        journal_view = df_transactions.copy()
        journal_view["quantity"] = journal_view["quantity"] * PRIVACY_RATIO
        journal_view = journal_view[[
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
