import sqlite3

conn = sqlite3.connect("portfolio.db")
cursor = conn.cursor()

cursor.executescript("""
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    isin TEXT UNIQUE,
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

CREATE TABLE IF NOT EXISTS market_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    close_price REAL NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id),
    UNIQUE (asset_id, date)
);
""")

conn.commit()
conn.close()
print("Base de données initialisée !")
