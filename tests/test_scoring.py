"""
Tests für Scoring & Prioritäts-Logik
"""

import sys
from pathlib import Path
import importlib

sys.path.insert(0, str(Path(__file__).parent.parent))

scoring = importlib.import_module('src.05_scoring')
calculate_score = scoring.calculate_score
get_matrix_position = scoring.get_matrix_position
get_color = scoring.get_color
analyze_priority = scoring.analyze_priority
get_priority_label = scoring.get_priority_label


def test_score_calculation():
    """Test Score-Berechnung: dringlichkeit * 2 + wichtigkeit"""
    assert calculate_score(1, 1) == 3   # Min
    assert calculate_score(3, 3) == 9   # Max
    assert calculate_score(2, 2) == 6   # Mittel
    assert calculate_score(3, 1) == 7   # Dringend, aber unwichtig
    assert calculate_score(1, 3) == 5   # Wichtig, aber nicht dringend


def test_matrix_position():
    """Test Matrix-Position (x=Wichtigkeit, y=Dringlichkeit)"""
    assert get_matrix_position(1, 1) == (1, 1)  # Links unten
    assert get_matrix_position(3, 3) == (3, 3)  # Rechts oben
    assert get_matrix_position(2, 2) == (2, 2)  # Mitte


def test_color_assignment():
    """Test Ampelfarben"""
    assert get_color(9) == "rot"    # Score 8-9
    assert get_color(8) == "rot"
    assert get_color(7) == "gelb"   # Score 5-7
    assert get_color(5) == "gelb"
    assert get_color(4) == "grün"   # Score 3-4
    assert get_color(3) == "grün"


def test_priority_label():
    """Test Priority Labels"""
    assert get_priority_label(9) == "Sehr hoch"
    assert get_priority_label(6) == "Hoch"
    assert get_priority_label(5) == "Mittel"
    assert get_priority_label(3) == "Niedrig"


def test_analyze_priority_integration():
    """Test vollständige Analyse"""
    result = analyze_priority(3, 3)  # Max Priorität
    
    assert result['score'] == 9
    assert result['matrix_x'] == 3
    assert result['matrix_y'] == 3
    assert result['farbe'] == "rot"
    assert result['quadrant'] == "33"
    assert '#' in result['farbe_hex']


def test_all_matrix_combinations():
    """Test alle 9 Felder der Matrix"""
    expected_scores = {
        (1, 1): 3,   # Grün
        (1, 2): 5,   # Gelb
        (1, 3): 7,   # Gelb
        (2, 1): 4,   # Grün
        (2, 2): 6,   # Gelb
        (2, 3): 8,   # Rot
        (3, 1): 5,   # Gelb
        (3, 2): 7,   # Gelb
        (3, 3): 9    # Rot
    }
    
    for (wichtigkeit, dringlichkeit), expected_score in expected_scores.items():
        score = calculate_score(dringlichkeit, wichtigkeit)
        assert score == expected_score, \
            f"Fehler bei ({wichtigkeit}, {dringlichkeit}): {score} != {expected_score}"


if __name__ == "__main__":
    print("🧪 Führe Scoring-Tests aus...\n")
    
    tests = [
        test_score_calculation,
        test_matrix_position,
        test_color_assignment,
        test_priority_label,
        test_analyze_priority_integration,
        test_all_matrix_combinations
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            print(f"✅ {test_func.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {test_func.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"⚠️  {test_func.__name__}: {e}")
            failed += 1
    
    print(f"\n📊 Ergebnis: {passed} bestanden, {failed} fehlgeschlagen")
