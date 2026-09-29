import sqlite3

DATA = [
    ("TEP.PA", "Teleperformance", "Technology", 36.0, 52.13),
    ("VIL.PA", "Viel & Cie", "Financial Services", 122.0, 17.32),
    ("PUB.PA", "Publicis Groupe", "Communication Services", 23.0, 77.82),
    ("EDEN.PA", "Edenred", "Industrials", 76.0, 18.45),
    ("CAP.PA", "Capgemini", "Technology", 20.0, 102.22),
    ("IPS.PA", "Ipsos", "Communication Services", 50.0, 30.53),
    ("SAN.PA", "Sanofi", "Healthcare", 22.0, 73.81),
    ("SOP.PA", "Sopra Steria Group", "Technology", 8.0, 135.71),
    ("ALGIL.PA", "Groupe Guillin", "Consumer Cyclical", 49.0, 21.31),
    ("FGR.PA", "Eiffage", "Industrials", 9.0, 110.38),
]

conn = sqlite3.connect("portfolio.db")
cur = conn.cursor()

# Nettoyer l'ancienne base d'essai
cur.execute("DELETE FROM transactions")
cur.execute("DELETE FROM assets")

for ticker, name, sector, qty, pru in DATA:
  cur.execute(
      """
        INSERT INTO assets (ticker, name, sector)
        VALUES (?, ?, ?)
    """,
      (ticker, name, sector),
  )
  asset_id = cur.lastrowid

  cur.execute(
      """
        INSERT INTO transactions (asset_id, type, date, quantity, price, fees, exchange_rate, reason, notes)
        VALUES (?, 'BUY', '2026-01-02', ?, ?, 0.0, 1.0, 'Entrée consolidée', 'Import automatique PRU')
    """,
      (asset_id, qty, pru),
  )

conn.commit()
conn.close()
print("Importation réussie !")
