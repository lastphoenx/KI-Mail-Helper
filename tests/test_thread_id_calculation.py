"""
Test Thread-ID Berechnung (Phase 12, fehlende Tests)

Testet die komplexe Logik für:
- Nested Thread-Strukturen (aus IMAP THREAD)
- Message-ID basierte Threading (In-Reply-To Chain)
- Fallback-Strategien
- Edge Cases
"""

import uuid
import sys
import os
import importlib
from typing import Dict, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

mail_fetcher = importlib.import_module('src.06_mail_fetcher')
ThreadCalculator = mail_fetcher.ThreadCalculator


ThreadIDCalculator = ThreadCalculator


class TestThreadIDCalculation:
    """Tests für Thread-ID Berechnung"""

    def test_flat_structure(self):
        """Test: Einfache flache Thread-Struktur"""
        print("\n📊 Test 1: Flache Structure (Top-Level Items)")
        
        # (1, 2, 3, 4, 5) = 5 top-level items = 5 separate Threads
        structure = (1, 2, 3, 4, 5)
        result = ThreadIDCalculator.from_imap_thread_structure(structure)
        
        # Alle sollten unterschiedliche Thread-IDs haben
        unique_threads = len(set(result.values()))
        print(f"   Input: {structure}")
        print(f"   Result: {result}")
        print(f"   Unique Threads: {unique_threads}")
        assert unique_threads == 5, f"Expected 5 separate threads, got {unique_threads}"
        print("   ✅ PASS")

    def test_nested_structure(self):
        """Test: Nested Thread-Struktur (Top-Level mit nested Group)"""
        print("\n📊 Test 2: Nested Structure")
        
        # (1, (2, 3, 4)) 
        # Thread 1: UID 1
        # Thread 2: UIDs 2, 3, 4 (nested group)
        structure = (1, (2, 3, 4))
        result = ThreadIDCalculator.from_imap_thread_structure(structure)
        
        print(f"   Input: {structure}")
        print(f"   Mapping: {result}")
        
        unique_threads = len(set(result.values()))
        assert unique_threads == 2, f"Expected 2 threads, got {unique_threads}"
        
        # UIDs 2, 3, 4 sollten gleiche Thread-ID haben
        assert result[2] == result[3] == result[4], "Nested UIDs sollten gleiche thread_id haben"
        
        # UID 1 sollte unterschiedlich sein
        assert result[1] != result[2], "UIDs 1 und 2,3,4 sollten unterschiedlich sein"
        
        print("   ✅ PASS")

    def test_deep_nesting(self):
        """Test: Tiefe Verschachtelung (lange Conversation Chain)"""
        print("\n📊 Test 3: Deep Nesting")
        
        # (1, (2, (3, (4, (5)))))
        # Eine lange Reply-Chain
        structure = (1, (2, (3, (4, (5)))))
        result = ThreadIDCalculator.from_imap_thread_structure(structure)
        
        print(f"   Input: {structure}")
        print(f"   Mapping: {result}")
        
        unique_threads = len(set(result.values()))
        assert unique_threads == 1, f"Expected 1 thread, got {unique_threads}"
        
        # Alle sollten die gleiche thread_id haben
        unique_ids = set(result.values())
        assert len(unique_ids) == 1, "Alle UIDs sollten gleiche thread_id haben"
        
        print("   ✅ PASS")

    def test_complex_structure(self):
        """Test: Komplexe mixed Struktur"""
        print("\n📊 Test 4: Complex Mixed Structure")
        
        # Mehrere Root-Threads mit Replies
        # (1, (2, 3, (4)), 5, (6, (7, 8)))
        structure = (1, (2, 3, (4)), 5, (6, (7, 8)))
        result = ThreadIDCalculator.from_imap_thread_structure(structure)
        
        print(f"   Input: {structure}")
        print(f"   Mapping: {result}")
        
        unique_threads = len(set(result.values()))
        print(f"   Unique Threads: {unique_threads}")
        
        # Sollten mehrere verschiedene Threads sein
        assert unique_threads >= 2, f"Expected at least 2 threads, got {unique_threads}"
        
        print("   ✅ PASS")

    def test_message_id_chain_simple(self):
        """Test: Simple Message-ID Chain"""
        print("\n📊 Test 5: Message-ID Chain (Simple)")
        
        emails = {
            1: {'message_id': 'msg1@server.com', 'in_reply_to': None},
            2: {'message_id': 'msg2@server.com', 'in_reply_to': 'msg1@server.com'},
            3: {'message_id': 'msg3@server.com', 'in_reply_to': 'msg2@server.com'},
        }
        
        thread_ids, parent_uids = ThreadIDCalculator.from_message_id_chain(emails)
        
        print(f"   Thread IDs: {thread_ids}")
        print(f"   Parent UIDs: {parent_uids}")
        
        # Alle sollten gleiche thread_id haben (sind in gleicher Conversation)
        assert thread_ids[1] == thread_ids[2] == thread_ids[3], \
            "Alle sollten gleiche thread_id haben"
        
        # Parent-UIDs sollten richtig sein
        assert parent_uids[1] is None, "UID 1 hat keinen Parent"
        assert parent_uids[2] == 1, "UID 2 parent ist 1"
        assert parent_uids[3] == 2, "UID 3 parent ist 2"
        
        print("   ✅ PASS")

    def test_message_id_chain_multiple_threads(self):
        """Test: Multiple separaten Message-ID Chains"""
        print("\n📊 Test 6: Message-ID Chain (Multiple Threads)")
        
        emails = {
            # Thread 1
            1: {'message_id': 'a1@server.com', 'in_reply_to': None},
            2: {'message_id': 'a2@server.com', 'in_reply_to': 'a1@server.com'},
            # Thread 2
            3: {'message_id': 'b1@server.com', 'in_reply_to': None},
            4: {'message_id': 'b2@server.com', 'in_reply_to': 'b1@server.com'},
        }
        
        thread_ids, parent_uids = ThreadIDCalculator.from_message_id_chain(emails)
        
        print(f"   Thread IDs: {thread_ids}")
        print(f"   Parent UIDs: {parent_uids}")
        
        # UIDs 1, 2 sollten gleiche thread_id haben
        assert thread_ids[1] == thread_ids[2], "UIDs 1, 2 sollten gleiche thread_id haben"
        
        # UIDs 3, 4 sollten gleiche thread_id haben
        assert thread_ids[3] == thread_ids[4], "UIDs 3, 4 sollten gleiche thread_id haben"
        
        # Aber unterschiedlich von 1, 2
        assert thread_ids[1] != thread_ids[3], "Unterschiedliche Threads sollten unterschiedliche IDs haben"
        
        print("   ✅ PASS")

    def test_broken_chain(self):
        """Test: Unterbrochene Message-ID Chain (parent nicht vorhanden)"""
        print("\n📊 Test 7: Broken Chain")
        
        emails = {
            1: {'message_id': 'msg1@server.com', 'in_reply_to': None},
            # msg2 ist NICHT in unserer DB
            2: {'message_id': 'msg3@server.com', 'in_reply_to': 'missing_msg@server.com'},
            3: {'message_id': 'msg4@server.com', 'in_reply_to': 'msg3@server.com'},
        }
        
        thread_ids, parent_uids = ThreadIDCalculator.from_message_id_chain(emails)
        
        print(f"   Thread IDs: {thread_ids}")
        print(f"   Parent UIDs: {parent_uids}")
        
        # msg3 und msg4 sollten eigene Thread sein (parent fehlt)
        assert thread_ids[2] == thread_ids[3], "msg3 & msg4 sollten gleiche thread_id haben"
        
        # msg1 ist separate thread
        assert thread_ids[1] != thread_ids[2], "Unterschiedliche Threads"
        
        print("   ✅ PASS")


def main():
    print("\n" + "="*70)
    print("🧵 Phase 12: Thread-ID Calculation Tests")
    print("="*70)
    
    test = TestThreadIDCalculation()
    
    try:
        test.test_flat_structure()
        test.test_nested_structure()
        test.test_deep_nesting()
        test.test_complex_structure()
        test.test_message_id_chain_simple()
        test.test_message_id_chain_multiple_threads()
        test.test_broken_chain()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED!")
        print("="*70)
        return 0
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
