import sqlite3
import os
db_path = os.path.join(os.path.dirname(__file__), 'emails.db')
c = sqlite3.connect(db_path)
cur = c.cursor()
cur.execute('SELECT COUNT(*) FROM users')
print(f'Users: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM mail_accounts')
print(f'Mail Accounts: {cur.fetchone()[0]}')
cur.execute('SELECT * FROM users')
for user in cur.fetchall():
    print(f'User: {user}')
cur.execute('SELECT * FROM mail_accounts')
for acc in cur.fetchall():
    print(f'Account: {acc}')
c.close()
