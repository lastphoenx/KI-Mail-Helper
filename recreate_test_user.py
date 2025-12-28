#!/usr/bin/env python3
"""Recreates test user after DB cleanup"""

from src.02_models import init_db, User
import os

# Backup alte DB
if os.path.exists("emails.db"):
    os.rename("emails.db", "emails.db.before-usercleanup")
    print("✅ Old DB backed up to emails.db.before-usercleanup")

# Neue DB
engine, Session = init_db()
session = Session()

user = User(username="thomas")
user.set_email("thomas@example.com")
user.set_password("TestPassword123!")
session.add(user)
session.commit()

print(f"✅ Test-User erstellt: thomas")
print(f"✅ Passwort: TestPassword123!")

# Verify
count = session.query(User).count()
print(f"✅ User in DB: {count}")

session.close()
