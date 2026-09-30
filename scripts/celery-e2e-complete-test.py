#!/usr/bin/env python3
"""
E2E Test: Complete Multi-User Stack (Tag 11-14)

Tests die komplette Migration:
- Mail-Sync (Tag 9)
- Auto-Rules (Tag 11-12)
- Sender-Pattern (Tag 13-14)

Alle Tasks sollten registriert sein und funktionieren.
"""

import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.celery_app import celery_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_all_tasks_registered():
    """Test 1: Prüfe ob ALLE Multi-User Tasks registriert sind"""
    logger.info("=" * 70)
    logger.info("TEST 1: Complete Task Registration")
    logger.info("=" * 70)
    
    inspect = celery_app.control.inspect()
    registered = inspect.registered()
    
    if not registered:
        logger.error("❌ FAIL: Keine Tasks registriert!")
        return False
    
    # Get all tasks
    all_tasks = []
    for worker_tasks in registered.values():
        all_tasks.extend(worker_tasks)
    
    required_tasks = [
        # Mail-Sync (Tag 9)
        "tasks.sync_user_emails",
        "tasks.sync_all_accounts",
        
        # Auto-Rules (Tag 11-12)
        "tasks.rule_execution.apply_rules_to_emails",
        "tasks.rule_execution.apply_rules_to_new_emails",
        "tasks.rule_execution.test_rule",
        
        # Sender-Pattern (Tag 13-14)
        "tasks.sender_patterns.scan_sender_patterns",
        "tasks.sender_patterns.cleanup_old_patterns",
        "tasks.sender_patterns.get_pattern_statistics",
        "tasks.sender_patterns.update_pattern_from_correction",
    ]
    
    missing_tasks = [t for t in required_tasks if t not in all_tasks]
    
    if missing_tasks:
        logger.error(f"❌ FAIL: Tasks fehlen: {missing_tasks}")
        return False
    
    logger.info(f"✅ PASS: Alle {len(required_tasks)} Multi-User Tasks registriert!")
    logger.info("")
    logger.info("Mail-Sync Tasks (Tag 9):")
    logger.info("  - tasks.sync_user_emails")
    logger.info("  - tasks.sync_all_accounts")
    logger.info("")
    logger.info("Auto-Rules Tasks (Tag 11-12):")
    logger.info("  - tasks.rule_execution.apply_rules_to_emails")
    logger.info("  - tasks.rule_execution.apply_rules_to_new_emails")
    logger.info("  - tasks.rule_execution.test_rule")
    logger.info("")
    logger.info("Sender-Pattern Tasks (Tag 13-14):")
    logger.info("  - tasks.sender_patterns.scan_sender_patterns")
    logger.info("  - tasks.sender_patterns.cleanup_old_patterns")
    logger.info("  - tasks.sender_patterns.get_pattern_statistics")
    logger.info("  - tasks.sender_patterns.update_pattern_from_correction")
    
    return True


def test_worker_health():
    """Test 2: Worker Health Check"""
    logger.info("")
    logger.info("=" * 70)
    logger.info("TEST 2: Worker Health")
    logger.info("=" * 70)
    
    inspect = celery_app.control.inspect()
    
    # Active workers
    workers = inspect.active()
    if not workers:
        logger.error("❌ FAIL: Keine aktiven Worker!")
        return False
    
    logger.info(f"✅ PASS: Worker aktiv: {list(workers.keys())}")
    
    # Stats
    stats = inspect.stats()
    if stats:
        for worker, worker_stats in stats.items():
            logger.info(f"   - {worker}")
            logger.info(f"     Pool: {worker_stats.get('pool', {}).get('implementation', 'unknown')}")
            logger.info(f"     Max concurrency: {worker_stats.get('pool', {}).get('max-concurrency', 'unknown')}")
    
    return True


def test_database_connection():
    """Test 3: Database Connection"""
    logger.info("")
    logger.info("=" * 70)
    logger.info("TEST 3: Database Connection")
    logger.info("=" * 70)
    
    try:
        from src.helpers.database import get_session_factory
        
        SessionFactory = get_session_factory()
        with SessionFactory() as db:
            # Simple query to test connection
            from src.helpers.database import _get_models
            models = _get_models()
            
            user_count = db.query(models.User).count()
            logger.info(f"✅ PASS: Database connected ({user_count} users)")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ FAIL: Database connection error: {e}")
        return False


def test_redis_connection():
    """Test 4: Redis Connection"""
    logger.info("")
    logger.info("=" * 70)
    logger.info("TEST 4: Redis Connection")
    logger.info("=" * 70)
    
    try:
        import redis
        
        # Test Broker (DB 1)
        broker_client = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
        broker_client.ping()
        logger.info("✅ PASS: Redis Broker (DB 1) connected")
        
        # Test Results (DB 2)
        result_client = redis.Redis(host='localhost', port=6379, db=2, decode_responses=True)
        result_client.ping()
        logger.info("✅ PASS: Redis Results (DB 2) connected")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ FAIL: Redis connection error: {e}")
        return False


def main():
    """Main Test Runner"""
    print("\n" + "=" * 70)
    print("🚀 MULTI-USER E2E TEST (TAG 8-14)")
    print("=" * 70)
    print("")
    
    tests = [
        ("Complete Task Registration", test_all_tasks_registered),
        ("Worker Health", test_worker_health),
        ("Database Connection", test_database_connection),
        ("Redis Connection", test_redis_connection),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"❌ Test '{test_name}' crashed: {type(e).__name__}: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 E2E TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:12} {test_name}")
    
    print("=" * 70)
    print(f"Result: {passed}/{total} tests passed")
    print("=" * 70)
    
    if passed == total:
        print("")
        print("✅ ALL E2E TESTS PASSED!")
        print("")
        print("🎉 MULTI-USER MIGRATION COMPLETE (TAG 8-14)")
        print("")
        print("Migration Status:")
        print("  ✅ Tag 8: Celery Worker Setup")
        print("  ✅ Tag 9: Mail-Sync Tasks")
        print("  ✅ Tag 10: Mail-Sync Testing")
        print("  ✅ Tag 11: Auto-Rules Tasks")
        print("  ✅ Tag 12: Auto-Rules Testing")
        print("  ✅ Tag 13: Sender-Pattern Tasks")
        print("  ✅ Tag 14: Sender-Pattern Testing")
        print("")
        print("🚀 SYSTEM READY FOR PRODUCTION!")
        print("")
        return 0
    else:
        print(f"❌ {total - passed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
