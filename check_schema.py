import sqlite3

def check_schema():
    conn = sqlite3.connect('contacts.db')
    cursor = conn.execute("PRAGMA table_info(contacts)")
    columns = cursor.fetchall()
    for col in columns:
        print(col)
    conn.close()

if __name__ == "__main__":
    check_schema()
