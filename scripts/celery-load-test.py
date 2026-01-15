#!/usr/bin/python3
"""Load-Test für Celery Worker

Testet Performance bei vielen parallelen Tasks:
- 10 Tasks gleichzeitig queuen
- Worker-Auslastung beobachten
- Success-Rate messen
- Durchschnittliche Execution-Time

⚠️  WICHTIG: Nutzt Mock-Tasks (debug_task) um echte Mail-Accounts nicht zu überlasten!
"""

import sys
import time
import statistics
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("🧪 Celery Load-Test: 10 parallele Tasks")
print("=" * 70)
print("")

# ════════════════════════════════════════════════════════════════════════
# SETUP
# ════════════════════════════════════════════════════════════════════════
print("📋 Setup...")

from src.celery_app import celery_app, debug_task

# Check Worker
inspect = celery_app.control.inspect()
active_workers = inspect.active()

if not active_workers:
    print("   ❌ Keine aktiven Worker!")
    sys.exit(1)

worker_count = len(active_workers)
print(f"   ✅ {worker_count} Worker aktiv")

# Check concurrency
stats = inspect.stats()
if stats:
    for worker_name, worker_stats in stats.items():
        pool = worker_stats.get('pool', {})
        concurrency = pool.get('max-concurrency', 'unknown')
        print(f"   ✅ {worker_name}: {concurrency} concurrent tasks")

print("")

# ════════════════════════════════════════════════════════════════════════
# LOAD TEST CONFIGURATION
# ════════════════════════════════════════════════════════════════════════
NUM_TASKS = 10
MAX_WORKERS = 10
TIMEOUT = 60  # seconds per task

print(f"⚙️  Load-Test Config:")
print(f"   Tasks: {NUM_TASKS}")
print(f"   Max Workers: {MAX_WORKERS}")
print(f"   Timeout per Task: {TIMEOUT}s")
print("")

response = input("Starten? (y/n): ")
if response.lower() != 'y':
    print("Test abgebrochen.")
    sys.exit(0)

print("")
print("=" * 70)
print("")

# ════════════════════════════════════════════════════════════════════════
# TEST 1: Queue Tasks
# ════════════════════════════════════════════════════════════════════════
print("1️⃣  Queuing Tasks...")

start_queue_time = time.time()
tasks = []

for i in range(NUM_TASKS):
    # Use debug_task instead of real sync_user_emails
    # This prevents overloading real mail servers
    task = debug_task.delay()
    tasks.append((i+1, task))
    print(f"   [{i+1}/{NUM_TASKS}] Task {task.id[:8]}... queued")
    
queue_time = time.time() - start_queue_time
print(f"   ✅ Alle {NUM_TASKS} Tasks gequeued in {queue_time:.2f}s")
print("")

# ════════════════════════════════════════════════════════════════════════
# TEST 2: Execute & Monitor
# ════════════════════════════════════════════════════════════════════════
print("2️⃣  Task Execution...")
print(f"   ⏳ Warte auf Completion (max {TIMEOUT}s pro Task)...")
print("")

results = []
start_exec_time = time.time()

def wait_for_task(task_info):
    """Wait for single task and measure time"""
    task_num, task = task_info
    task_start = time.time()
    
    try:
        # Wait for result
        result = task.get(timeout=TIMEOUT)
        task_time = time.time() - task_start
        
        return {
            'num': task_num,
            'task_id': task.id,
            'status': 'success',
            'time': task_time,
            'state': task.state
        }
    except Exception as e:
        task_time = time.time() - task_start
        
        return {
            'num': task_num,
            'task_id': task.id,
            'status': 'failed',
            'time': task_time,
            'state': task.state,
            'error': str(e)
        }

# Execute with ThreadPool
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {executor.submit(wait_for_task, task_info): task_info for task_info in tasks}
    
    for future in as_completed(futures):
        result = future.result()
        results.append(result)
        
        status_icon = "✅" if result['status'] == 'success' else "❌"
        print(f"   {status_icon} Task {result['num']}: {result['status']} ({result['time']:.2f}s)")

total_exec_time = time.time() - start_exec_time
print("")
print(f"   ⏱️  Total Execution Time: {total_exec_time:.2f}s")
print("")

# ════════════════════════════════════════════════════════════════════════
# TEST 3: Statistics
# ════════════════════════════════════════════════════════════════════════
print("3️⃣  Statistics...")

successful = [r for r in results if r['status'] == 'success']
failed = [r for r in results if r['status'] == 'failed']
times = [r['time'] for r in results]

success_rate = (len(successful) / NUM_TASKS) * 100
avg_time = statistics.mean(times)
min_time = min(times)
max_time = max(times)
median_time = statistics.median(times)

print(f"   📊 Success Rate: {len(successful)}/{NUM_TASKS} ({success_rate:.1f}%)")
print(f"   ⏱️  Avg Execution Time: {avg_time:.2f}s")
print(f"   ⏱️  Min/Max Time: {min_time:.2f}s / {max_time:.2f}s")
print(f"   ⏱️  Median Time: {median_time:.2f}s")
print("")

# Calculate throughput
throughput = NUM_TASKS / total_exec_time
print(f"   🚀 Throughput: {throughput:.2f} tasks/second")
print("")

# ════════════════════════════════════════════════════════════════════════
# TEST 4: Worker Health Check
# ════════════════════════════════════════════════════════════════════════
print("4️⃣  Worker Health Check...")

# Check if worker still responsive
active_after = inspect.active()
if active_after:
    print(f"   ✅ Worker noch aktiv: {len(active_after)} worker(s)")
else:
    print(f"   ⚠️  Worker nicht mehr erreichbar!")

print("")

# ════════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════════
print("=" * 70)

if success_rate == 100:
    print("✅ Load-Test PASSED!")
elif success_rate >= 90:
    print("⚠️  Load-Test PASSED mit Warnings")
else:
    print("❌ Load-Test FAILED!")

print("")
print("📋 Zusammenfassung:")
print(f"   ✅ Tasks: {len(successful)}/{NUM_TASKS} erfolgreich")
print(f"   ⏱️  Avg Time: {avg_time:.2f}s")
print(f"   🚀 Throughput: {throughput:.2f} tasks/s")

if failed:
    print("")
    print("❌ Failed Tasks:")
    for fail in failed:
        print(f"   - Task {fail['num']}: {fail.get('error', 'Unknown error')}")

print("")
print("💡 Beobachtungen:")
if avg_time < 1.0:
    print("   ✅ Sehr schnelle Execution (< 1s avg)")
elif avg_time < 5.0:
    print("   ✅ Gute Performance (< 5s avg)")
else:
    print("   ⚠️  Langsame Execution (> 5s avg)")

if success_rate == 100:
    print("   ✅ Keine Task-Failures")
elif success_rate >= 90:
    print("   ⚠️  Einige Tasks fehlgeschlagen")
else:
    print("   ❌ Viele Tasks fehlgeschlagen - Worker überfordert?")

print("")
print("🚀 Nächster Schritt:")
print("   python3 scripts/celery-error-handling-test.py")
print("")
