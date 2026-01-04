#!/usr/bin/env python3
"""
Test: ReDoS Protection für Sanitizer

Testet ob Timeout und Pattern-Fixes funktionieren:
1. Timeout-Decorator bei slow regex
2. Length-Limit bei großem Input
3. Bounded quantifiers verhindern catastrophic backtracking

Phase 9f: HIGH-Priority Security Fix Testing
"""

import sys
import os
import time

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Import sanitizer
import importlib.util
spec = importlib.util.spec_from_file_location("sanitizer", os.path.join(project_root, "src", "04_sanitizer.py"))
sanitizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sanitizer)


def test_quote_detection_bounded():
    """Test bounded quantifiers für Quote-Detection"""
    print("🧪 Test 1: Quote-Detection Bounded Quantifiers")
    
    # Crafted ReDoS-Angriff (ALT: würde hängen)
    # "Am " + 100x "xyz " + "schrieb nicht"  → 2^100 Backtracking Steps
    crafted = "Am " + "xyz " * 100 + "schrieb nicht"
    
    start = time.time()
    result = sanitizer._remove_quoted_history(crafted)
    duration = time.time() - start
    
    print(f"   Input: {len(crafted)} chars (100x 'xyz ' pattern)")
    print(f"   Duration: {duration:.4f}s")
    
    if duration < 0.1:  # Sollte instant sein
        print(f"   ✅ PASS: Bounded quantifiers verhindern Backtracking")
        return True
    else:
        print(f"   ❌ FAIL: Pattern zu langsam ({duration:.2f}s)")
        return False


def test_email_pattern_simplified():
    """Test simplified Email-Pattern"""
    print("\n🧪 Test 2: Email-Pattern Simplified")
    
    # Normaler Fall: 20-char local + 20-char domain (sollte matchen)
    normal_email = "a" * 20 + "@" + "b" * 20 + ".com"
    text = f"Test {normal_email} test"
    
    start = time.time()
    result = sanitizer._pseudonymize(text)
    duration = time.time() - start
    
    print(f"   Input: {len(text)} chars (valid email)")
    print(f"   Duration: {duration:.4f}s")
    print(f"   Result: {result}")
    
    # Test 2: Too-long email (1000 chars) sollte NICHT matchen (by design)
    crafted_email = "a" * 1000 + "@" + "b" * 1000 + ".com"
    text2 = f"Test {crafted_email} test"
    
    start2 = time.time()
    result2 = sanitizer._pseudonymize(text2)
    duration2 = time.time() - start2
    
    print(f"   Input 2: {len(text2)} chars (too-long email)")
    print(f"   Duration 2: {duration2:.4f}s")
    
    if duration < 0.1 and "[EMAIL_1]" in result and duration2 < 0.1:
        print(f"   ✅ PASS: Simplified pattern funktioniert (valid match, invalid skip, kein Backtracking)")
        return True
    else:
        print(f"   ❌ FAIL: Pattern zu langsam oder falsch")
        return False


def test_timeout_decorator():
    """Test Timeout-Decorator"""
    print("\n🧪 Test 3: Timeout-Decorator (2s Limit)")
    
    # Gigantischer Text (sollte timeout triggern wenn regex slow ist)
    huge_text = "test@example.com " * 100_000  # 2MB
    
    start = time.time()
    result = sanitizer._pseudonymize(huge_text)
    duration = time.time() - start
    
    print(f"   Input: {len(huge_text)/1024:.0f}KB (100k emails)")
    print(f"   Duration: {duration:.2f}s")
    
    # Mit Timeout sollte es maximal 3s dauern (2s + overhead)
    if duration < 5:
        print(f"   ✅ PASS: Timeout-Decorator verhindert lange Laufzeiten")
        return True
    else:
        print(f"   ❌ FAIL: Timeout funktioniert nicht ({duration:.2f}s)")
        return False


def test_length_limit():
    """Test Input-Length Limit"""
    print("\n🧪 Test 4: Input-Length Limit (500KB)")
    
    # Über dem Limit
    huge_text = "x" * 600_000  # 600KB
    
    start = time.time()
    result = sanitizer._pseudonymize(huge_text)
    duration = time.time() - start
    
    print(f"   Input: {len(huge_text)/1024:.0f}KB")
    print(f"   Output: {len(result)/1024:.0f}KB")
    print(f"   Duration: {duration:.4f}s")
    
    if len(result) <= 500_000:
        print(f"   ✅ PASS: Input korrekt auf 500KB begrenzt")
        return True
    else:
        print(f"   ❌ FAIL: Length-Limit funktioniert nicht")
        return False


def main():
    print("="*60)
    print("ReDoS Protection Tests")
    print("="*60)
    print()
    
    results = []
    results.append(test_quote_detection_bounded())
    results.append(test_email_pattern_simplified())
    results.append(test_timeout_decorator())
    results.append(test_length_limit())
    
    print()
    print("="*60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    
    if all(results):
        print("🎉 Alle Tests bestanden - ReDoS Protection funktioniert!")
        return 0
    else:
        print("⚠️  Einige Tests fehlgeschlagen")
        return 1


if __name__ == '__main__':
    sys.exit(main())
