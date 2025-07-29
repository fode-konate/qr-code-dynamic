import sqlite3
import os

DB_PATH = 'urls.db'

# Connexion à la base de données existante
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Fonction utilitaire pour savoir si une colonne existe déjà
def column_exists(table, column):
    c.execute(f"PRAGMA table_info({table})")
    return column in [info[1] for info in c.fetchall()]

# Ajout des colonnes si elles n'existent pas
if not column_exists('urls', 'folder'):
    c.execute("ALTER TABLE urls ADD COLUMN folder TEXT DEFAULT 'Général'")
    print("[✓] Colonne 'folder' ajoutée.")

if not column_exists('urls', 'deleted'):
    c.execute("ALTER TABLE urls ADD COLUMN deleted INTEGER DEFAULT 0")
    print("[✓] Colonne 'deleted' ajoutée.")

if not column_exists('urls', 'filename'):
    c.execute("ALTER TABLE urls ADD COLUMN filename TEXT")
    print("[✓] Colonne 'filename' ajoutée.")

if not column_exists('urls', 'created_at'):
    c.execute("ALTER TABLE urls ADD COLUMN created_at TEXT")
    print("[✓] Colonne 'created_at' ajoutée.")

conn.commit()
conn.close()

print("\n🎉 Migration terminée avec succès !")
