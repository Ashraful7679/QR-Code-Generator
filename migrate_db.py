import sqlite3
import os

DB_FILE = 'contacts.db'

def migrate():
    if not os.path.exists(DB_FILE):
        print(f"Database {DB_FILE} not found.")
        return

    conn = sqlite3.connect(DB_FILE)
    try:
        # Check if column already exists
        cursor = conn.execute("PRAGMA table_info(contacts)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'profile_image' not in columns:
            print("Adding profile_image column...")
            conn.execute("ALTER TABLE contacts ADD COLUMN profile_image TEXT;")
            conn.commit()
            print("Migration for profile_image successful.")
        
        if 'short_url' not in columns:
            print("Adding short_url column...")
            conn.execute("ALTER TABLE contacts ADD COLUMN short_url TEXT;")
            conn.commit()
            print("Migration for short_url successful.")
        else:
            print("Column short_url already exists.")
            
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
