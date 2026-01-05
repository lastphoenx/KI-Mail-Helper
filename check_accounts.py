#!/usr/bin/env python3
import sys
import os
import importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

models = importlib.import_module('.02_models', 'src')

engine, Session = models.init_db('emails.db')
session = Session()

print('📬 MAIL-ACCOUNTS im System:')
for ma in session.query(models.MailAccount).all():
    user = session.query(models.User).filter_by(id=ma.user_id).first()
    print(f'  Account {ma.id}: {ma.email} (User {ma.user_id}: {user.username if user else "?"})')

print()
print('📊 EMAIL-COUNT pro Account:')
for ma in session.query(models.MailAccount).all():
    count = session.query(models.RawEmail).filter_by(mail_account_id=ma.id).count()
    print(f'  Account {ma.id}: {count} RawEmails')

session.close()
