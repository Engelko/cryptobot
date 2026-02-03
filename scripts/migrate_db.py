import sqlite3
import os
from antigravity.config import settings

def migrate():
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        print(f"Database {db_path} does not exist. Creating it...")
        # Just create the directory if it doesn't exist
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        # We can let the app initialize it, or just create empty file
        open(db_path, 'a').close()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='risk_state'")
        if not cursor.fetchone():
            print("Table risk_state does not exist yet. It will be created by the app.")
            return

        # Check if column exists
        cursor.execute("PRAGMA table_info(risk_state)")
        columns = [column[1] for column in cursor.fetchall()]

        if "consecutive_loss_days" not in columns:
            print("Adding column consecutive_loss_days to risk_state table...")
            cursor.execute("ALTER TABLE risk_state ADD COLUMN consecutive_loss_days INTEGER DEFAULT 0")
            conn.commit()
            print("Migration successful.")
        else:
            print("Column consecutive_loss_days already exists.")

    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
