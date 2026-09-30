#!/usr/bin/env python3
"""
CLI-Skripts für Hybrid Score-Learning System.

Kommandos:
1. python cli_hybrid_classifier.py trigger-training <user_id> <classifier_type> [--dry-run]
2. python cli_hybrid_classifier.py delete-user <user_id> [--dry-run]
3. python cli_hybrid_classifier.py cache-stats
4. python cli_hybrid_classifier.py train-check <user_id> <classifier_type>
5. python cli_hybrid_classifier.py cleanup-orphaned

Beispiele:
  # Training triggern
  python cli_hybrid_classifier.py trigger-training 1 dringlichkeit
  
  # Dry-Run
  python cli_hybrid_classifier.py delete-user 1 --dry-run
  
  # Cache-Statistiken
  python cli_hybrid_classifier.py cache-stats
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, UTC
import shutil

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.helpers.database import get_session_factory
from src.services.personal_classifier_service import (
    get_classifier_dir,
    invalidate_classifier_cache,
    CLASSIFIER_TYPES,
    get_cache_stats,
)
from src.tasks.training_tasks import train_personal_classifier, THROTTLE_MIN_SAMPLES, THROTTLE_MIN_MINUTES

# ============================================================================
# Command 1: Trigger Training
# ============================================================================

def cmd_trigger_training(user_id: int, classifier_type: str, dry_run: bool = False):
    """Triggert Personal Classifier Training async."""
    
    print("\n" + "="*70)
    print(f"🎓 TRAINING TRIGGER: user_id={user_id}, type={classifier_type}")
    print("="*70)
    
    if classifier_type not in CLASSIFIER_TYPES:
        print(f"❌ Ungültiger classifier_type: {classifier_type}")
        print(f"   Gültige Typen: {CLASSIFIER_TYPES}")
        return 1
    
    SessionFactory = get_session_factory()
    db = SessionFactory()
    
    try:
        # 1. User prüfen
        from importlib import import_module
        models = import_module(".02_models", "src")
        
        user = db.query(models.User).filter_by(id=user_id).first()
        if not user:
            print(f"❌ User {user_id} nicht gefunden")
            return 1
        
        print(f"✅ User gefunden: {user.username}")
        
        # 2. Trainings-Daten zählen
        override_field = {
            "dringlichkeit": "user_override_dringlichkeit",
            "wichtigkeit": "user_override_wichtigkeit",
            "spam": "user_override_spam_flag",
            "kategorie": "user_override_kategorie",
        }.get(classifier_type)
        
        if not override_field:
            print(f"❌ Unbekannter classifier_type: {classifier_type}")
            return 1
        
        correction_count = db.query(models.ProcessedEmail).filter(
            models.ProcessedEmail.user_id == user_id,
            getattr(models.ProcessedEmail, override_field) != None
        ).count()
        
        print(f"📊 Trainings-Samples vorhanden: {correction_count}")
        
        if correction_count < THROTTLE_MIN_SAMPLES:
            print(f"⚠️  Throttling: Minimum {THROTTLE_MIN_SAMPLES} Samples erforderlich")
        
        # 3. Metadata prüfen
        metadata = db.query(models.ClassifierMetadata).filter_by(
            user_id=user_id,
            classifier_type=classifier_type
        ).first()
        
        if metadata:
            print(f"📈 Letztes Training: {metadata.last_trained_at}")
            print(f"   Accuracy: {metadata.accuracy_score:.2%}" if metadata.accuracy_score else "")
            print(f"   Error Count: {metadata.error_count}")
            print(f"   Model Version: {metadata.model_version}")
            
            if metadata.error_count >= 3:
                print(f"🔴 CIRCUIT-BREAKER AKTIV! Model ist deaktiviert.")
        else:
            print("📝 Noch nie trainiert (first_training)")
        
        # 4. Training triggern
        if dry_run:
            print("\n🔍 DRY-RUN: Würde Training triggern")
            print(f"   Task: train_personal_classifier.delay({user_id}, '{classifier_type}')")
        else:
            print(f"\n⏳ Training wird getriggert...")
            result = train_personal_classifier.delay(user_id, classifier_type)
            print(f"✅ Task ID: {result.id}")
            print(f"   Status: Async eingereiht")
        
        return 0
    
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")
        return 1
    
    finally:
        db.close()


# ============================================================================
# Command 2: Delete User (mit Cleanup)
# ============================================================================

def cmd_delete_user(user_id: int, dry_run: bool = False):
    """Löscht User und seine Personal Classifier."""
    
    print("\n" + "="*70)
    print(f"🗑️  USER DELETION: user_id={user_id}")
    print("="*70)
    
    SessionFactory = get_session_factory()
    db = SessionFactory()
    
    try:
        from importlib import import_module
        models = import_module(".02_models", "src")
        
        # 1. User prüfen
        user = db.query(models.User).filter_by(id=user_id).first()
        if not user:
            print(f"❌ User {user_id} nicht gefunden")
            return 1
        
        print(f"✅ User gefunden: {user.username}")
        
        # 2. Personal Classifiers prüfen
        classifier_dir = get_classifier_dir()
        user_dir = classifier_dir / "per_user" / f"user_{user_id}"
        
        files_to_delete = []
        if user_dir.exists():
            files_to_delete = list(user_dir.glob("*.joblib")) + list(user_dir.glob("*.pkl"))
            print(f"📁 Personal Classifier Dateien gefunden: {len(files_to_delete)}")
            for f in files_to_delete:
                print(f"   - {f.name}")
        else:
            print(f"📁 Keine Personal Classifier Dateien")
        
        # 3. Metadata in DB prüfen
        metadata_count = db.query(models.ClassifierMetadata).filter_by(
            user_id=user_id
        ).count()
        print(f"📊 Metadata-Einträge in DB: {metadata_count}")
        
        # 4. Löschung durchführen/simulieren
        if dry_run:
            print(f"\n🔍 DRY-RUN: Würde folgende Aktionen durchführen:")
            print(f"   1. Verzeichnis löschen: {user_dir}")
            print(f"   2. Cache invalidieren: invalidate_classifier_cache(user_id={user_id})")
            print(f"   3. User aus DB löschen: DELETE FROM users WHERE id={user_id}")
            print(f"   4. CASCADE: Alle FK-Referenzen löschen")
        else:
            print(f"\n⏳ Lösche User und Classifier-Dateien...")
            
            # Dateien löschen
            if user_dir.exists():
                shutil.rmtree(user_dir)
                print(f"✅ Verzeichnis gelöscht: {user_dir}")
            
            # Cache invalidieren
            deleted_cache = invalidate_classifier_cache(user_id=user_id)
            print(f"✅ Cache invalidiert: {deleted_cache} Einträge")
            
            # User löschen (würde in echtem Kontext über DELETE Endpoint gehen)
            print(f"⚠️  User-Löschung aus DB: Manuell durchführen oder über Admin-Panel")
            print(f"   SQL: DELETE FROM users WHERE id={user_id}")
        
        return 0
    
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")
        return 1
    
    finally:
        db.close()


# ============================================================================
# Command 3: Cache Statistics
# ============================================================================

def cmd_cache_stats():
    """Zeigt Cache-Statistiken."""
    
    print("\n" + "="*70)
    print("💾 CACHE STATISTICS")
    print("="*70)
    
    try:
        stats = get_cache_stats()
        
        print(f"\n📊 Classifier Cache:")
        print(f"   Größe: {stats['classifier_cache_size']}/{stats['classifier_cache_maxsize']}")
        print(f"   TTL: {stats['classifier_cache_ttl']} Sekunden ({stats['classifier_cache_ttl']//60} Min)")
        
        print(f"\n📊 Scaler Cache:")
        print(f"   Größe: {stats['scaler_cache_size']}/{stats['scaler_cache_maxsize']}")
        print(f"   TTL: {stats['scaler_cache_ttl']} Sekunden ({stats['scaler_cache_ttl']//60} Min)")
        
        print(f"\n🔍 Details:")
        print(f"   Total Cache Entries: {stats['classifier_cache_size'] + stats['scaler_cache_size']}")
        print(f"   Total Capacity: {stats['classifier_cache_maxsize'] + stats['scaler_cache_maxsize']}")
        
        return 0
    
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")
        return 1


# ============================================================================
# Command 4: Training Status Check
# ============================================================================

def cmd_train_check(user_id: int, classifier_type: str):
    """Prüft ob Training für Classifier möglich ist."""
    
    print("\n" + "="*70)
    print(f"📋 TRAINING CHECK: user_id={user_id}, type={classifier_type}")
    print("="*70)
    
    SessionFactory = get_session_factory()
    db = SessionFactory()
    
    try:
        from importlib import import_module
        models = import_module(".02_models", "src")
        from src.tasks.training_tasks import _should_trigger_training
        
        # 1. User prüfen
        user = db.query(models.User).filter_by(id=user_id).first()
        if not user:
            print(f"❌ User {user_id} nicht gefunden")
            return 1
        
        print(f"✅ User: {user.username}")
        print(f"   prefer_personal_classifier: {user.prefer_personal_classifier}")
        
        # 2. Throttling prüfen
        should_train, reason = _should_trigger_training(user_id, classifier_type, db, models)
        
        print(f"\n🚦 Throttling-Status:")
        if should_train:
            print(f"   ✅ KANN TRAINIEREN: {reason}")
        else:
            print(f"   ❌ KANN NICHT TRAINIEREN: {reason}")
        
        # 3. Metadata Details
        metadata = db.query(models.ClassifierMetadata).filter_by(
            user_id=user_id,
            classifier_type=classifier_type
        ).first()
        
        if metadata:
            print(f"\n📊 Metadata:")
            print(f"   Samples: {metadata.training_samples}")
            print(f"   Accuracy: {metadata.accuracy_score:.2%}" if metadata.accuracy_score else "   Accuracy: -")
            print(f"   Error Count: {metadata.error_count}/3 (Circuit-Breaker)")
            print(f"   Version: {metadata.model_version}")
            print(f"   Last Trained: {metadata.last_trained_at}")
            print(f"   Active: {metadata.is_active}")
        else:
            print(f"\n📊 Metadata: Keine Einträge (noch nie trainiert)")
        
        # 4. Datei-Status
        classifier_dir = get_classifier_dir()
        personal_path = classifier_dir / "per_user" / f"user_{user_id}" / f"{classifier_type}.joblib"
        
        print(f"\n📁 Dateien:")
        print(f"   Personal: {'✅ Existiert' if personal_path.exists() else '❌ Fehlt'}")
        
        return 0
    
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")
        return 1
    
    finally:
        db.close()


# ============================================================================
# Command 5: Cleanup Orphaned
# ============================================================================

def cmd_cleanup_orphaned():
    """Löscht orphaned Personal-Classifier-Dateien (ohne User in DB)."""
    
    print("\n" + "="*70)
    print("🧹 CLEANUP ORPHANED CLASSIFIERS")
    print("="*70)
    
    SessionFactory = get_session_factory()
    db = SessionFactory()
    
    try:
        from importlib import import_module
        models = import_module(".02_models", "src")
        
        classifier_dir = get_classifier_dir()
        per_user_dir = classifier_dir / "per_user"
        
        if not per_user_dir.exists():
            print("✅ Keine Personal-Classifier vorhanden")
            return 0
        
        # Alle User-Verzeichnisse durchsuchen
        orphaned = []
        
        for user_dir in per_user_dir.iterdir():
            if not user_dir.is_dir():
                continue
            
            # Extrahiere user_id aus "user_X"
            try:
                user_id = int(user_dir.name.split("_")[1])
            except (ValueError, IndexError):
                continue
            
            # Prüfe ob User existiert
            user = db.query(models.User).filter_by(id=user_id).first()
            if not user:
                orphaned.append(user_dir)
                print(f"❌ Orphaned: {user_dir.name} (user_id={user_id} nicht in DB)")
        
        if not orphaned:
            print("✅ Keine orphaned Classifiers gefunden")
            return 0
        
        # Löschen
        print(f"\n⏳ Lösche {len(orphaned)} orphaned Verzeichnisse...")
        for user_dir in orphaned:
            try:
                shutil.rmtree(user_dir)
                print(f"✅ Gelöscht: {user_dir.name}")
            except Exception as e:
                print(f"⚠️  Fehler beim Löschen {user_dir.name}: {e}")
        
        return 0
    
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")
        return 1
    
    finally:
        db.close()


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="CLI für Hybrid Score-Learning System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Kommando')
    
    # Trigger Training
    p1 = subparsers.add_parser('trigger-training', help='Triggert Personal Classifier Training')
    p1.add_argument('user_id', type=int, help='User ID')
    p1.add_argument('classifier_type', choices=CLASSIFIER_TYPES, help='Classifier-Typ')
    p1.add_argument('--dry-run', action='store_true', help='Nur anzeigen, nicht ausführen')
    
    # Delete User
    p2 = subparsers.add_parser('delete-user', help='Löscht User + Personal Classifiers')
    p2.add_argument('user_id', type=int, help='User ID')
    p2.add_argument('--dry-run', action='store_true', help='Nur anzeigen, nicht ausführen')
    
    # Cache Stats
    p3 = subparsers.add_parser('cache-stats', help='Zeigt Cache-Statistiken')
    
    # Training Check
    p4 = subparsers.add_parser('train-check', help='Prüft Trainings-Status')
    p4.add_argument('user_id', type=int, help='User ID')
    p4.add_argument('classifier_type', choices=CLASSIFIER_TYPES, help='Classifier-Typ')
    
    # Cleanup Orphaned
    p5 = subparsers.add_parser('cleanup-orphaned', help='Löscht orphaned Classifiers')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Execute commands
    if args.command == 'trigger-training':
        return cmd_trigger_training(args.user_id, args.classifier_type, args.dry_run)
    elif args.command == 'delete-user':
        return cmd_delete_user(args.user_id, args.dry_run)
    elif args.command == 'cache-stats':
        return cmd_cache_stats()
    elif args.command == 'train-check':
        return cmd_train_check(args.user_id, args.classifier_type)
    elif args.command == 'cleanup-orphaned':
        return cmd_cleanup_orphaned()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
