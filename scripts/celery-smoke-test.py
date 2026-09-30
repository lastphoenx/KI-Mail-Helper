#!/usr/bin/python3
"""Smoke Test für Celery Worker - Testet debug_task()"""

import sys
import time
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("🧪 Celery Smoke Test - debug_task()")
print("=" * 50)
print("")

try:
    from src.celery_app import celery_app, debug_task
    
    # 1. Task absenden
    print("1️⃣  Sende debug_task...")
    task = debug_task.delay()
    print(f"   ✅ Task ID: {task.id}")
    print(f"   ✅ Status: {task.state}")
    print("")
    
    # 2. Warte auf Ergebnis (max 10s)
    print("2️⃣  Warte auf Task-Completion (max 10s)...")
    try:
        result = task.get(timeout=10)
        print(f"   ✅ Task completed!")
        print(f"   ✅ Result: {result}")
    except Exception as e:
        print(f"   ❌ Task failed: {e}")
        sys.exit(1)
    
    print("")
    
    # 3. Celery Inspect
    print("3️⃣  Celery Worker Info:")
    inspect = celery_app.control.inspect()
    
    # Active workers
    active_workers = inspect.active()
    if active_workers:
        print(f"   ✅ Active Workers: {len(active_workers)}")
        for worker_name in active_workers.keys():
            print(f"      - {worker_name}")
    else:
        print("   ❌ No active workers!")
        sys.exit(1)
    
    # Registered tasks
    registered = inspect.registered()
    if registered:
        print(f"   ✅ Registered Tasks:")
        for worker_name, tasks in registered.items():
            print(f"      Worker: {worker_name}")
            for task_name in tasks:
                if 'tasks.' in task_name or 'debug_task' in task_name:
                    print(f"         - {task_name}")
    
    print("")
    print("=" * 50)
    print("✅ Smoke Test PASSED!")
    print("🎉 Celery Worker ist operational!")
    print("")
    print("🌸 Flower Web UI: http://localhost:5555")
    
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("")
    print("Stelle sicher, dass:")
    print("  - venv aktiviert ist")
    print("  - celery installiert ist")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
