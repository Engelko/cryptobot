import sqlite3
import os
import re

def get_db_path():
    # Try to read from .env directly to avoid package import issues
    db_url = "sqlite:///storage/data.db" # Default
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            content = f.read()
            match = re.search(r'DATABASE_URL\s*=\s*["\']?(.*?)["\']?(\s|$)', content)
            if match:
                db_url = match.group(1)

    return db_url.replace("sqlite:///", "")

def migrate():
    db_path = get_db_path()
    print(f"Targeting database: {db_path}")

    if not os.path.exists(db_path):
        print(f"Database {db_path} does not exist. Creating it...")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        open(db_path, 'a').close()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='risk_state'")
        if not cursor.fetchone():
            print("Table risk_state does not exist yet. Bot will create it on first run.")
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
