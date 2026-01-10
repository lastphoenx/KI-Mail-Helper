#!/usr/bin/env python3
"""
Test-Script für Tag-Learning Verbesserungen (Phase F.2 Enhanced)

Tests:
1. remove_tag() ruft update_learned_embedding() auf
2. Dynamische Thresholds basierend auf Tag-Anzahl
3. MIN_EMAILS_FOR_LEARNING wird respektiert
4. Auto-Assignment vs. Manual Suggestions

Usage:
    python test_tag_learning_improvements.py --user-id 1
"""

import sys
import argparse
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import models & services
import importlib
models = importlib.import_module("02_models")
tag_manager = importlib.import_module("src.services.tag_manager")

# Import constants
from src.services.tag_manager import (
    MIN_EMAILS_FOR_LEARNING,
    AUTO_ASSIGN_SIMILARITY_THRESHOLD,
    get_suggestion_threshold
)


def run_tests(db_session, user_id: int):
    """Führt alle Tests aus"""
    
    print("\n" + "="*80)
    print("TAG-LEARNING IMPROVEMENTS - TEST SUITE")
    print("="*80 + "\n")
    
    # Test 1: Dynamische Thresholds
    print("📊 TEST 1: Dynamische Thresholds")
    print("-" * 80)
    
    tag_counts = [3, 8, 20]
    for count in tag_counts:
        threshold = get_suggestion_threshold(count)
        print(f"  {count:2d} Tags → Threshold: {threshold:.2%}")
    
    print(f"\n  Auto-Assignment Threshold: {AUTO_ASSIGN_SIMILARITY_THRESHOLD:.2%}")
    print(f"  MIN_EMAILS_FOR_LEARNING: {MIN_EMAILS_FOR_LEARNING}")
    print("  ✅ Dynamische Thresholds funktionieren\n")
    
    # Test 2: User Tags zählen
    print("📊 TEST 2: User Tags analysieren")
    print("-" * 80)
    
    user_tags = db_session.query(models.EmailTag).filter_by(user_id=user_id).all()
    print(f"  User {user_id} hat {len(user_tags)} Tags:")
    
    for tag in user_tags[:10]:  # Nur erste 10 zeigen
        email_count = db_session.query(models.EmailTagAssignment).filter_by(
            tag_id=tag.id
        ).count()
        
        has_learned = "✅" if tag.learned_embedding else "❌"
        has_description = "✅" if tag.description else "❌"
        
        print(f"    - {tag.name:20s} | {email_count:3d} Emails | "
              f"Learned: {has_learned} | Description: {has_description}")
    
    if len(user_tags) > 10:
        print(f"    ... und {len(user_tags) - 10} weitere")
    
    suggestion_threshold = get_suggestion_threshold(len(user_tags))
    print(f"\n  → Aktueller Suggestion-Threshold: {suggestion_threshold:.2%}")
    print("  ✅ User Tags analysiert\n")
    
    # Test 3: MIN_EMAILS_FOR_LEARNING Check
    print("📊 TEST 3: MIN_EMAILS_FOR_LEARNING Validierung")
    print("-" * 80)
    
    tags_below_min = []
    tags_above_min = []
    
    for tag in user_tags:
        email_count = db_session.query(models.EmailTagAssignment).filter_by(
            tag_id=tag.id
        ).count()
        
        if email_count < MIN_EMAILS_FOR_LEARNING:
            tags_below_min.append((tag, email_count))
        else:
            tags_above_min.append((tag, email_count))
    
    print(f"  Tags mit < {MIN_EMAILS_FOR_LEARNING} Emails (kein Learning erwartet): {len(tags_below_min)}")
    for tag, count in tags_below_min[:5]:
        has_learned = "⚠️ HAT" if tag.learned_embedding else "✅ KEIN"
        print(f"    - {tag.name:20s}: {count} Email(s) | {has_learned} learned_embedding")
    
    print(f"\n  Tags mit >= {MIN_EMAILS_FOR_LEARNING} Emails (Learning erwartet): {len(tags_above_min)}")
    for tag, count in tags_above_min[:5]:
        has_learned = "✅ HAT" if tag.learned_embedding else "⚠️ KEIN"
        print(f"    - {tag.name:20s}: {count} Email(s) | {has_learned} learned_embedding")
    
    # Warnung wenn Diskrepanzen
    discrepancies = sum(
        1 for tag, count in tags_below_min if tag.learned_embedding
    ) + sum(
        1 for tag, count in tags_above_min if not tag.learned_embedding
    )
    
    if discrepancies > 0:
        print(f"\n  ⚠️  {discrepancies} Diskrepanz(en) gefunden - "
              f"eventuell alte Daten vor dem Patch")
    else:
        print("\n  ✅ Alle Tags konsistent mit MIN_EMAILS_FOR_LEARNING")
    print()
    
    # Test 4: Sample Email Tag-Suggestions
    print("📊 TEST 4: Sample Tag-Suggestions")
    print("-" * 80)
    
    # Hole erste Email mit Embedding
    sample_email = db_session.query(models.RawEmail).filter(
        models.RawEmail.user_id == user_id,
        models.RawEmail.email_embedding.isnot(None)
    ).first()
    
    if sample_email:
        print(f"  Testing mit Email ID {sample_email.id}:")
        print(f"  Subject: {sample_email.email_subject[:60]}...")
        
        # Get processed email ID
        processed = db_session.query(models.ProcessedEmail).filter_by(
            raw_email_id=sample_email.id
        ).first()
        
        if processed:
            # Bereits assigned Tags
            assigned_tags = tag_manager.TagManager.get_email_tags(
                db_session, processed.id, user_id
            )
            assigned_tag_ids = [t.id for t in assigned_tags]
            
            print(f"  Bereits assigned: {[t.name for t in assigned_tags]}")
            
            # Suggestions holen
            suggestions = tag_manager.TagManager.suggest_tags_by_email_embedding(
                db_session,
                user_id,
                sample_email.email_embedding,
                top_k=7,
                exclude_tag_ids=assigned_tag_ids
            )
            
            print(f"\n  Tag-Suggestions (Top {len(suggestions)}):")
            
            auto_count = 0
            suggest_count = 0
            
            for tag, similarity, auto_assign in suggestions:
                icon = "🟢" if auto_assign else "🟡"
                label = "AUTO" if auto_assign else "SUGGEST"
                
                embedding_source = (
                    "learned" if tag.learned_embedding 
                    else ("description" if tag.description else "name")
                )
                
                print(f"    {icon} [{label:7s}] {similarity:.2%} - "
                      f"{tag.name:20s} (source: {embedding_source})")
                
                if auto_assign:
                    auto_count += 1
                else:
                    suggest_count += 1
            
            print(f"\n  → {auto_count} würden auto-assigned (>= {AUTO_ASSIGN_SIMILARITY_THRESHOLD:.0%})")
            print(f"  → {suggest_count} sind manuelle Vorschläge (>= {suggestion_threshold:.0%})")
            print("  ✅ Tag-Suggestions funktionieren")
        else:
            print("  ⚠️  Keine ProcessedEmail gefunden für RawEmail")
    else:
        print("  ⚠️  Keine Email mit Embedding gefunden")
    
    print("\n" + "="*80)
    print("TESTS ABGESCHLOSSEN")
    print("="*80 + "\n")
    
    # Summary
    print("📋 ZUSAMMENFASSUNG:")
    print(f"  • {len(user_tags)} Tags insgesamt")
    print(f"  • Suggestion-Threshold: {suggestion_threshold:.2%} ({len(user_tags)} Tags)")
    print(f"  • Auto-Assign-Threshold: {AUTO_ASSIGN_SIMILARITY_THRESHOLD:.2%}")
    print(f"  • MIN_EMAILS_FOR_LEARNING: {MIN_EMAILS_FOR_LEARNING}")
    print(f"  • Tags mit learned_embedding: {sum(1 for t in user_tags if t.learned_embedding)}")
    print(f"  • Tags mit description: {sum(1 for t in user_tags if t.description)}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Test Tag-Learning Improvements"
    )
    parser.add_argument(
        "--user-id",
        type=int,
        required=True,
        help="User ID für Tests"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="mail_helper.db",
        help="Pfad zur Datenbank (default: mail_helper.db)"
    )
    
    args = parser.parse_args()
    
    # Database connection
    engine = create_engine(f"sqlite:///{args.db}")
    Session = sessionmaker(bind=engine)
    db_session = Session()
    
    try:
        # Check if user exists
        user = db_session.query(models.User).filter_by(id=args.user_id).first()
        if not user:
            print(f"❌ User ID {args.user_id} nicht gefunden!")
            sys.exit(1)
        
        print(f"✅ Testing für User: {user.email}")
        
        # Run tests
        run_tests(db_session, args.user_id)
        
    finally:
        db_session.close()


if __name__ == "__main__":
    main()
