import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'emails.db')
print(f"Checking: {db_path}")
print(f"File size: {os.path.getsize(db_path)}")

try:
    c = sqlite3.connect(db_path, timeout=5)
    c.execute('PRAGMA journal_mode=WAL')
    
    cur = c.cursor()
    cur.execute('SELECT COUNT(*) FROM users')
    users = cur.fetchone()[0]
    print(f'Users: {users}')
    
    if users > 0:
        cur.execute('SELECT id, username, email FROM users')
        for row in cur.fetchall():
            print(f'  User: {row}')
    
    cur.execute('SELECT COUNT(*) FROM mail_accounts')
    accounts = cur.fetchone()[0]
    print(f'Mail Accounts: {accounts}')
    
    if accounts > 0:
        cur.execute('SELECT id, name, imap_server, imap_username FROM mail_accounts')
        for row in cur.fetchall():
            print(f'  Account: {row}')
    
    c.close()
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
