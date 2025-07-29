import sqlite3

conn = sqlite3.connect('urls.db')
c = conn.cursor()

# Création de la table principale
c.execute('''
CREATE TABLE IF NOT EXISTS urls (
    id TEXT PRIMARY KEY,
    target_url TEXT
)
''')

conn.commit()
conn.close()

print("✅ Table 'urls' créée avec succès.")