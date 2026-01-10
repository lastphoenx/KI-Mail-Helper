#!/usr/bin/env python3
"""
Test: Race Condition Protection für Account Lockout

Simuliert 10 parallele Login-Versuche um zu testen ob:
1. Alle Failed Attempts korrekt gezählt werden (keine Race Condition)
2. Account Lockout nach 5 Versuchen funktioniert
3. Atomic SQL UPDATE verhindert Read-Modify-Write Race

Phase 9f: HIGH-Priority Security Fix Testing
"""

import sys
import os
import threading
import time
from datetime import datetime, UTC

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Import 02_models.py direkt (module mit Zahl im Namen)
import importlib
models = importlib.import_module('src.02_models')
User = models.User
init_db = models.init_db

def test_race_condition_lockout():
    """Test parallel login attempts"""
    
    # Test-DB (TEMP FILE statt :memory: für Thread-Safety!)
    import tempfile
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()
    
    try:
        # init_db() mit echter Datei
        engine, SessionFactory = init_db(temp_db.name)
        
        # scoped_session für Thread-Safety
        from sqlalchemy.orm import scoped_session
        Session = scoped_session(SessionFactory)
        
        # Test-User erstellen
        session = Session()
        test_user = User()
        test_user.set_username('testuser')
        test_user.set_email('test@example.com')
        test_user.set_password('testpassword123')
        test_user.failed_login_attempts = 0
        session.add(test_user)
        session.commit()
        user_id = test_user.id
        session.close()
        
        print("🧪 Race Condition Lockout Test")
        print(f"   User ID: {user_id}")
        print(f"   Initial failed_login_attempts: 0")
        print()
        
        # Parallele Failed-Login Versuche
        NUM_THREADS = 10
        results = {'count': 0, 'locked': False}
        lock = threading.Lock()
        
        def simulate_failed_login(thread_id):
            """Simuliert fehlgeschlagenen Login"""
            session = Session()
            try:
                user = session.query(User).filter_by(id=user_id).first()
                
                # Phase 9f: Atomic SQL-Update (sollte Race-Safe sein)
                user.record_failed_login(session)
                session.commit()
                
                # Read back für Verification
                session.refresh(user)
                
                with lock:
                    results['count'] = max(results['count'], user.failed_login_attempts)
                    if user.locked_until:
                        results['locked'] = True
                
                print(f"   Thread {thread_id:2d}: attempts={user.failed_login_attempts}, locked={user.locked_until is not None}")
                
            finally:
                session.close()
        
        # Start threads
        print(f"🚀 Starte {NUM_THREADS} parallele Login-Versuche...\n")
        threads = []
        start = time.time()
        
        for i in range(NUM_THREADS):
            t = threading.Thread(target=simulate_failed_login, args=(i+1,))
            threads.append(t)
            t.start()
        
        # Wait für alle Threads
        for t in threads:
            t.join()
        
        duration = time.time() - start
        
        # Final Verification
        session = Session()
        final_user = session.query(User).filter_by(id=user_id).first()
        final_count = final_user.failed_login_attempts
        is_locked = final_user.locked_until is not None
        session.close()
        
        print()
        print("📊 Test Results:")
        print(f"   Duration: {duration:.2f}s")
        print(f"   Expected count: {NUM_THREADS}")
        print(f"   Actual count: {final_count}")
        print(f"   Account locked: {is_locked}")
        print()
        
        # Assertions
        success = True
        
        if final_count != NUM_THREADS:
            print(f"❌ FAIL: Race Condition detected!")
            print(f"   {NUM_THREADS - final_count} attempts wurden NICHT gezählt")
            success = False
        else:
            print(f"✅ PASS: Alle {NUM_THREADS} Attempts korrekt gezählt (Race-Safe)")
        
        if not is_locked:
            print(f"❌ FAIL: Account sollte nach {final_count} Versuchen gesperrt sein!")
            success = False
        else:
            print(f"✅ PASS: Account korrekt gesperrt nach {final_count} Versuchen")
        
        print()
        
        if success:
            print("🎉 Alle Tests bestanden - Race Condition Protection funktioniert!")
            return 0
        else:
            print("⚠️  Tests fehlgeschlagen - Race Condition noch vorhanden!")
            return 1
    
    finally:
        # Cleanup temp DB
        import os
        if os.path.exists(temp_db.name):
            os.unlink(temp_db.name)


if __name__ == '__main__':
    sys.exit(test_race_condition_lockout())
