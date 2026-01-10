#!/usr/bin/env python3
"""
Test-Script für Source-Specific Thresholds

Demonstriert wie die verschiedenen Thresholds funktionieren.
"""

def _get_thresholds_for_tag(tag):
    """
    Bestimme Suggest- und Auto-Assign-Thresholds basierend auf der Embedding-Quelle.
    
    Args:
        tag: Tag-Objekt mit learned_embedding, description, name
        
    Returns:
        tuple: (suggest_threshold, auto_assign_threshold)
    """
    if tag.learned_embedding:
        return 0.75, 0.80
    elif tag.description:
        return 0.50, 0.60
    else:
        return 0.35, 0.45


class MockTag:
    """Mock Tag für Testing"""
    def __init__(self, name, learned=None, description=None):
        self.name = name
        self.learned_embedding = learned
        self.description = description


def test_threshold_logic():
    """Teste die Threshold-Logik mit verschiedenen Szenarien"""
    
    print("=" * 80)
    print("SOURCE-SPECIFIC THRESHOLD TEST")
    print("=" * 80)
    
    # Test-Szenarien
    scenarios = [
        {
            "tag": MockTag("AGB Richtlinien", learned=b"dummy_embedding"),
            "similarity": 0.91,
            "description": "Learned Embedding (3+ Emails markiert)"
        },
        {
            "tag": MockTag("Rechnung", description="Rechnungen von Shops..."),
            "similarity": 0.52,
            "description": "Description-basiert (neu erstellt)"
        },
        {
            "tag": MockTag("Bank"),
            "similarity": 0.47,
            "description": "Name-basiert (kein Description)"
        },
        {
            "tag": MockTag("Newsletter", description="Newsletter und Werbung"),
            "similarity": 0.45,
            "description": "Description mit niedriger Similarity"
        },
        {
            "tag": MockTag("Dringend"),
            "similarity": 0.30,
            "description": "Name mit sehr niedriger Similarity"
        }
    ]
    
    print("\n")
    
    for i, scenario in enumerate(scenarios, 1):
        tag = scenario["tag"]
        similarity = scenario["similarity"]
        desc = scenario["description"]
        
        # Thresholds berechnen
        suggest_thresh, auto_thresh = _get_thresholds_for_tag(tag)
        
        # Entscheidung treffen
        if similarity >= auto_thresh:
            action = "✅ AUTO-ASSIGN"
        elif similarity >= suggest_thresh:
            action = "💡 SUGGEST"
        else:
            action = "❌ SKIP"
        
        # Source bestimmen
        if tag.learned_embedding:
            source = "learned"
        elif tag.description:
            source = "description"
        else:
            source = "name"
        
        print(f"Test {i}: {tag.name}")
        print(f"  Szenario: {desc}")
        print(f"  Source: {source}")
        print(f"  Similarity: {similarity*100:.1f}%")
        print(f"  Thresholds: suggest={suggest_thresh*100:.0f}%, auto={auto_thresh*100:.0f}%")
        print(f"  → {action}")
        print()
    
    print("=" * 80)
    print("ZUSAMMENFASSUNG")
    print("=" * 80)
    print()
    print("Threshold-Konfiguration:")
    print("  • Learned:      75% suggest, 80% auto-assign")
    print("  • Description:  50% suggest, 60% auto-assign")
    print("  • Name only:    35% suggest, 45% auto-assign")
    print()
    print("Erwartetes Verhalten:")
    print("  ✅ AGB Richtlinien (91%): AUTO-ASSIGN wegen Learned Embedding")
    print("  💡 Rechnung (52%): SUGGEST wegen Description (über 50%)")
    print("  ✅ Bank (47%): AUTO-ASSIGN wegen Name (über 45%)")
    print("  💡 Newsletter (45%): SUGGEST wegen Description (unter 60%)")
    print("  ❌ Dringend (30%): SKIP wegen Name (unter 35%)")
    print()


if __name__ == "__main__":
    test_threshold_logic()
