import os
import sqlite3

import psycopg2

SQLITE_FILE = 'contacts.db'
DATABASE_URL = os.environ.get('DATABASE_URL')

CONTACTS_COLUMNS = (
    'id', 'first_name', 'last_name', 'phone', 'email', 'company',
    'job_title', 'address', 'website', 'contact_type', 'mobile',
    'file_path', 'profile_image', 'short_url', 'user_id', 'created_at'
)

SSQL = '''
    CREATE TABLE IF NOT EXISTS contacts (
        id TEXT PRIMARY KEY,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT,
        company TEXT,
        job_title TEXT,
        address TEXT,
        website TEXT,
        contact_type TEXT,
        mobile TEXT,
        file_path TEXT,
        profile_image TEXT,
        short_url TEXT,
        user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
'''

USQL = '''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash BYTEA NOT NULL,
        is_admin BOOLEAN DEFAULT false,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
'''


def main():
    if not DATABASE_URL:
        print("DATABASE_URL environment variable is not set.")
        return

    if not os.path.exists(SQLITE_FILE):
        print(f"{SQLITE_FILE} not found.")
        return

    src = sqlite3.connect(SQLITE_FILE)
    src.row_factory = sqlite3.Row

    # Ensure source has the user_id ownership column (backfill to first user = admin)
    try:
        src.execute('ALTER TABLE contacts ADD COLUMN user_id INTEGER')
    except sqlite3.OperationalError:
        pass
    src.execute('UPDATE contacts SET user_id = (SELECT id FROM users ORDER BY id LIMIT 1) WHERE user_id IS NULL')
    src.commit()

    pg = psycopg2.connect(DATABASE_URL)
    cur = pg.cursor()

    cur.execute(SSQL)
    cur.execute(USQL)

    contacts = src.execute('SELECT * FROM contacts').fetchall()
    for row in contacts:
        cur.execute(
            f"INSERT INTO contacts ({', '.join(CONTACTS_COLUMNS)}) "
            f"VALUES ({', '.join(['%s'] * len(CONTACTS_COLUMNS))}) "
            "ON CONFLICT (id) DO NOTHING",
            tuple(row[c] for c in CONTACTS_COLUMNS)
        )
    print(f"Copied {len(contacts)} contacts.")

    users = src.execute('SELECT * FROM users').fetchall()
    for row in users:
        cur.execute(
            "INSERT INTO users (id, username, password_hash, is_admin, created_at) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (row['id'], row['username'], row['password_hash'], bool(row['is_admin']), row['created_at'])
        )
    if users:
        cur.execute("SELECT setval(pg_get_serial_sequence('users', 'id'), (SELECT MAX(id) FROM users));")
    print(f"Copied {len(users)} users.")

    pg.commit()
    cur.close()
    pg.close()
    src.close()
    print("Migration complete.")


if __name__ == '__main__':
    main()