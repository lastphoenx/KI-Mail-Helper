#!/usr/bin/env python3
"""Phase Y2: Test effective_ai_mode Property"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import importlib

def test_effective_ai_mode():
    """Test the effective_ai_mode property with different toggle combinations"""
    
    models_mod = importlib.import_module(".02_models", "src")
    
    # Create DB session
    engine = create_engine("sqlite:///emails.db")
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # Get first account
        account = db.query(models_mod.MailAccount).first()
        
        if not account:
            print("❌ Kein Account gefunden")
            return
        
        print(f"📧 Testing Account: {account.name} (ID: {account.id})")
        print("=" * 60)
        
        # Test 1: Alle aus (none)
        print("\n1️⃣ Test: Alle Toggles aus")
        account.urgency_booster_enabled = False
        account.ai_analysis_anon_enabled = False
        account.ai_analysis_original_enabled = False
        account.anonymize_with_spacy = False
        mode = account.effective_ai_mode
        print(f"   effective_ai_mode = '{mode}'")
        assert mode == "none", f"Expected 'none', got '{mode}'"
        print("   ✅ PASS")
        
        # Test 2: Urgency Booster überschreibt alles
        print("\n2️⃣ Test: Urgency Booster überschreibt AI-Original")
        account.urgency_booster_enabled = True
        account.ai_analysis_original_enabled = True  # Wird ignoriert!
        mode = account.effective_ai_mode
        print(f"   effective_ai_mode = '{mode}'")
        assert mode == "spacy_booster", f"Expected 'spacy_booster', got '{mode}'"
        print("   ✅ PASS (Urgency Booster hat Priorität)")
        
        # Test 3: LLM Original
        print("\n3️⃣ Test: LLM auf Original-Daten")
        account.urgency_booster_enabled = False
        account.ai_analysis_original_enabled = True
        mode = account.effective_ai_mode
        print(f"   effective_ai_mode = '{mode}'")
        assert mode == "llm_original", f"Expected 'llm_original', got '{mode}'"
        print("   ✅ PASS")
        
        # Test 4: LLM Anon (benötigt Anonymisierung)
        print("\n4️⃣ Test: LLM Anon ohne Anonymisierung")
        account.urgency_booster_enabled = False
        account.ai_analysis_original_enabled = False
        account.ai_analysis_anon_enabled = True  # Alleine nicht genug!
        account.anonymize_with_spacy = False
        mode = account.effective_ai_mode
        print(f"   effective_ai_mode = '{mode}'")
        assert mode != "llm_anon", f"Expected NOT 'llm_anon' (missing anonymization), got '{mode}'"
        print(f"   ✅ PASS (Fällt zurück auf '{mode}')")
        
        # Test 5: LLM Anon mit Anonymisierung
        print("\n5️⃣ Test: LLM Anon MIT Anonymisierung")
        account.anonymize_with_spacy = True
        account.ai_analysis_anon_enabled = True
        mode = account.effective_ai_mode
        print(f"   effective_ai_mode = '{mode}'")
        assert mode == "llm_anon", f"Expected 'llm_anon', got '{mode}'"
        print("   ✅ PASS")
        
        # Test 6: Legacy enable_ai_analysis_on_fetch
        print("\n6️⃣ Test: Legacy enable_ai_analysis_on_fetch")
        account.urgency_booster_enabled = False
        account.ai_analysis_anon_enabled = False
        account.ai_analysis_original_enabled = False
        account.enable_ai_analysis_on_fetch = True  # Legacy
        mode = account.effective_ai_mode
        print(f"   effective_ai_mode = '{mode}'")
        assert mode == "llm_original", f"Expected 'llm_original' (legacy support), got '{mode}'"
        print("   ✅ PASS (Legacy-Support funktioniert)")
        
        print("\n" + "=" * 60)
        print("✅ Alle Tests bestanden!")
        print("\nPhase Y2 Implementation erfolgreich:")
        print("  • effective_ai_mode Property funktioniert")
        print("  • Hierarchie: Urgency > Anon > Original > None")
        print("  • Anonymisierungs-Abhängigkeit erzwungen")
        print("  • Legacy-Support für enable_ai_analysis_on_fetch")
        
    finally:
        db.rollback()  # Änderungen nicht speichern
        db.close()

if __name__ == "__main__":
    test_effective_ai_mode()
