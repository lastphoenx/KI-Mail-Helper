#!/usr/bin/env python3
"""
Manage Learning – Tag-Learning (pro User) und Score-Classifier (global)

Das System hat ZWEI Learning-Mechanismen:

1. Tag-Learning (PRO USER)
   - Speicherung: DB (email_tags.learned_embedding, negative_embedding)
   - Embedding-Aggregation aus Tag-Zuweisungen
   
2. Score-Learning (GLOBAL)
   - Speicherung: src/classifiers/*.pkl
   - SGD-Classifier für Dringlichkeit/Wichtigkeit/Spam/Kategorie
   - ⚠️ ACHTUNG: User-Korrekturen beeinflussen ALLE User!

Verwendung:
  Tag-Learning:
    python scripts/manage_learning.py --list                    # Status aller User
    python scripts/manage_learning.py --user=1                  # Status für User 1
    python scripts/manage_learning.py --user=1 --reset          # Reset für User 1
    python scripts/manage_learning.py --tag=5 --reset           # Reset für Tag 5
    python scripts/manage_learning.py --user=1 --reset-negative # Nur Negative resetten

  Score-Classifier:
    python scripts/manage_learning.py --classifiers             # Classifier-Status
    python scripts/manage_learning.py --reset-classifiers       # Alle Classifier löschen
"""

import sys
import os
import argparse

# Projekt-Root zu sys.path hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# .env laden
from dotenv import load_dotenv
from pathlib import Path
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env.local", override=True)
load_dotenv(project_root / ".env", override=False)

# Database Setup
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
import importlib

models = importlib.import_module('.02_models', 'src')

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{project_root / 'emails.db'}")
USE_POSTGRESQL = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")

if USE_POSTGRESQL:
    print(f"🐘 PostgreSQL Mode: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
    engine = create_engine(DATABASE_URL, connect_args={"connect_timeout": 10})
else:
    print(f"📦 SQLite Mode: {DATABASE_URL}")
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

Session = sessionmaker(bind=engine)


def list_learning_status(user_id=None):
    """Zeigt Learning-Status für alle oder einen bestimmten User"""
    session = Session()
    
    try:
        query = session.query(models.User).order_by(models.User.id)
        if user_id:
            query = query.filter(models.User.id == user_id)
        
        users = query.all()
        
        if not users:
            print(f"ℹ️  Keine User gefunden" + (f" mit ID {user_id}" if user_id else ""))
            return True
        
        print("🧠 Tag-Learning Status")
        print("=" * 100)
        
        for user in users:
            tags = session.query(models.EmailTag).filter(
                models.EmailTag.user_id == user.id
            ).order_by(models.EmailTag.id).all()
            
            if not tags:
                print(f"\n👤 User {user.id} ({user.username}): Keine Tags")
                continue
            
            # Statistiken berechnen
            total_tags = len(tags)
            tags_with_learned = sum(1 for t in tags if t.learned_embedding is not None)
            tags_with_negative = sum(1 for t in tags if t.negative_embedding is not None)
            total_negative_count = sum(t.negative_count or 0 for t in tags)
            
            # Assignments zählen
            total_assignments = session.query(models.EmailTagAssignment).join(
                models.EmailTag
            ).filter(models.EmailTag.user_id == user.id).count()
            
            # Negative Examples zählen (falls Tabelle existiert)
            total_negative_examples = 0
            if hasattr(models, 'TagNegativeExample'):
                # TagNegativeExample hat kein user_id, geht über tag_id
                tag_ids = [t.id for t in tags]
                if tag_ids:
                    total_negative_examples = session.query(models.TagNegativeExample).filter(
                        models.TagNegativeExample.tag_id.in_(tag_ids)
                    ).count()
            
            print(f"\n👤 User {user.id} ({user.username})")
            print("-" * 100)
            print(f"   📊 Gesamt: {total_tags} Tags, {total_assignments} Zuweisungen")
            print(f"   ✅ Mit Learned-Embedding: {tags_with_learned}/{total_tags} ({100*tags_with_learned//total_tags if total_tags else 0}%)")
            print(f"   ❌ Mit Negative-Embedding: {tags_with_negative}/{total_tags} ({total_negative_count} Rejects gesamt)")
            if total_negative_examples > 0:
                print(f"   📝 Negative Examples (DB): {total_negative_examples}")
            print()
            
            # Detail-Tabelle
            print(f"   {'ID':<6} {'Tag-Name':<25} {'Learned':<10} {'Negative':<10} {'Rejects':<8}")
            print(f"   {'-'*6} {'-'*25} {'-'*10} {'-'*10} {'-'*8}")
            
            for tag in tags:
                learned = "✅" if tag.learned_embedding else "—"
                negative = "✅" if tag.negative_embedding else "—"
                rejects = tag.negative_count or 0
                print(f"   {tag.id:<6} {tag.name[:25]:<25} {learned:<10} {negative:<10} {rejects:<8}")
        
        print()
        return True
        
    except Exception as e:
        print(f"❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()


def reset_learning(user_id=None, tag_id=None, reset_negative_only=False, force=False):
    """Setzt Learning zurück für User oder Tag"""
    session = Session()
    
    try:
        if tag_id:
            # Einzelnen Tag resetten
            tag = session.query(models.EmailTag).filter(models.EmailTag.id == tag_id).first()
            if not tag:
                print(f"❌ Tag mit ID {tag_id} nicht gefunden")
                return False
            
            scope_desc = f"Tag '{tag.name}' (ID {tag_id})"
            tags_to_reset = [tag]
            
        elif user_id:
            # Alle Tags eines Users
            tags_to_reset = session.query(models.EmailTag).filter(
                models.EmailTag.user_id == user_id
            ).all()
            
            if not tags_to_reset:
                print(f"ℹ️  User {user_id} hat keine Tags")
                return True
            
            user = session.query(models.User).filter(models.User.id == user_id).first()
            scope_desc = f"User '{user.username}' (ID {user_id}, {len(tags_to_reset)} Tags)"
            
        else:
            print("❌ Bitte --user=ID oder --tag=ID angeben")
            return False
        
        # Was wird gelöscht?
        if reset_negative_only:
            action = "Negative-Learning"
            print(f"🧹 {action} zurücksetzen für {scope_desc}")
            print()
            print(f"   Folgende Felder werden auf NULL gesetzt:")
            print(f"   - negative_embedding")
            print(f"   - negative_updated_at")
            print(f"   - negative_count → 0")
            if hasattr(models, 'TagNegativeExample') and user_id:
                # TagNegativeExample hat kein user_id, geht über tag_id
                tag_ids = [t.id for t in tags_to_reset]
                neg_count = session.query(models.TagNegativeExample).filter(
                    models.TagNegativeExample.tag_id.in_(tag_ids)
                ).count() if tag_ids else 0
                print(f"   - {neg_count} Negative-Example-Einträge werden gelöscht")
        else:
            action = "Komplettes Learning"
            print(f"🧹 {action} zurücksetzen für {scope_desc}")
            print()
            print(f"   Folgende Felder werden auf NULL gesetzt:")
            print(f"   - learned_embedding")
            print(f"   - embedding_updated_at")
            print(f"   - negative_embedding")
            print(f"   - negative_updated_at")
            print(f"   - negative_count → 0")
            if hasattr(models, 'TagNegativeExample') and user_id:
                # TagNegativeExample hat kein user_id, geht über tag_id
                tag_ids = [t.id for t in tags_to_reset]
                neg_count = session.query(models.TagNegativeExample).filter(
                    models.TagNegativeExample.tag_id.in_(tag_ids)
                ).count() if tag_ids else 0
                print(f"   - {neg_count} Negative-Example-Einträge werden gelöscht")
        
        print()
        print(f"   ✅ BLEIBT ERHALTEN:")
        print(f"   - Tag-Definitionen (Name, Farbe, Beschreibung)")
        print(f"   - Tag-Zuweisungen zu Emails")
        print()
        
        if not force:
            confirm = input(f"🚨 Wirklich {action} zurücksetzen? [y/N]: ").strip().lower()
            if confirm != 'y':
                print("❌ Abgebrochen")
                return False
        
        # Reset durchführen
        for tag in tags_to_reset:
            if reset_negative_only:
                tag.negative_embedding = None
                tag.negative_updated_at = None
                tag.negative_count = 0
            else:
                tag.learned_embedding = None
                tag.embedding_updated_at = None
                tag.negative_embedding = None
                tag.negative_updated_at = None
                tag.negative_count = 0
        
        # Negative Examples löschen (falls vorhanden)
        if hasattr(models, 'TagNegativeExample'):
            tag_ids = [t.id for t in tags_to_reset]
            if tag_ids:
                session.query(models.TagNegativeExample).filter(
                    models.TagNegativeExample.tag_id.in_(tag_ids)
                ).delete(synchronize_session=False)
        
        session.commit()
        
        print()
        print(f"✅ {action} zurückgesetzt für {scope_desc}")
        print(f"🔄 Tags neu zuweisen, um Learning wieder aufzubauen")
        return True
        
    except Exception as e:
        session.rollback()
        print(f"❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()


# ════════════════════════════════════════════════════════════════════════════════
# Score-Classifier Management (Global)
# ════════════════════════════════════════════════════════════════════════════════

CLASSIFIER_DIR = project_root / "src" / "classifiers"
CLASSIFIER_FILES = [
    "dringlichkeit_clf.pkl",
    "wichtigkeit_clf.pkl",
    "spam_clf.pkl",
    "kategorie_clf.pkl",
]


def list_classifiers():
    """Zeigt Status der globalen Score-Classifier"""
    print("📊 Score-Classifier Status (GLOBAL)")
    print("=" * 70)
    print()
    print(f"📁 Verzeichnis: {CLASSIFIER_DIR}")
    print()
    
    if not CLASSIFIER_DIR.exists():
        print("⚠️  Classifier-Verzeichnis existiert nicht")
        print("   → Noch kein Training durchgeführt")
        return True
    
    print(f"{'Classifier':<30} {'Status':<15} {'Größe':<15} {'Geändert':<20}")
    print("-" * 70)
    
    found_any = False
    for clf_file in CLASSIFIER_FILES:
        clf_path = CLASSIFIER_DIR / clf_file
        if clf_path.exists():
            found_any = True
            size = clf_path.stat().st_size
            mtime = datetime.fromtimestamp(clf_path.stat().st_mtime)
            size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
            print(f"{clf_file:<30} {'✅ Vorhanden':<15} {size_str:<15} {mtime.strftime('%Y-%m-%d %H:%M'):<20}")
        else:
            print(f"{clf_file:<30} {'— Nicht vorhanden':<15} {'—':<15} {'—':<20}")
    
    print()
    if found_any:
        print("ℹ️  Score-Learning ist GLOBAL – alle User teilen diese Classifier")
        print("   User-Korrekturen beeinflussen die Vorhersagen für alle anderen User")
    else:
        print("ℹ️  Noch keine Classifier trainiert")
        print("   → Training via UI: Einstellungen → 'Modelle trainieren'")
        print("   → Oder: curl -X POST http://localhost:5000/retrain")
    
    return True


def reset_classifiers(force=False):
    """Löscht alle Score-Classifier .pkl Dateien"""
    print("🗑️  Score-Classifier zurücksetzen")
    print("=" * 70)
    print()
    
    if not CLASSIFIER_DIR.exists():
        print("ℹ️  Classifier-Verzeichnis existiert nicht – nichts zu löschen")
        return True
    
    # Finde vorhandene Classifier
    existing = []
    for clf_file in CLASSIFIER_FILES:
        clf_path = CLASSIFIER_DIR / clf_file
        if clf_path.exists():
            existing.append(clf_path)
    
    if not existing:
        print("ℹ️  Keine Classifier-Dateien vorhanden – nichts zu löschen")
        return True
    
    print(f"⚠️  Folgende Dateien werden gelöscht:")
    for clf_path in existing:
        size = clf_path.stat().st_size
        size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
        print(f"   🗑️  {clf_path.name} ({size_str})")
    
    print()
    print(f"✅ BLEIBT ERHALTEN:")
    print(f"   - User-Korrekturen in der Datenbank (user_override_* Felder)")
    print(f"   - Beim nächsten Training werden Classifier neu aufgebaut")
    print()
    
    if not force:
        confirm = input("🚨 Wirklich alle Classifier löschen? [y/N]: ").strip().lower()
        if confirm != 'y':
            print("❌ Abgebrochen")
            return False
    
    # Löschen
    for clf_path in existing:
        clf_path.unlink()
        print(f"   ✅ Gelöscht: {clf_path.name}")
    
    print()
    print("✅ Alle Score-Classifier gelöscht")
    print("🔄 Neu trainieren via: curl -X POST http://localhost:5000/retrain")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Manage Learning – Tag-Learning (pro User) und Score-Classifier (global)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Tag-Learning (pro User):
  python scripts/manage_learning.py --list                    # Status aller User
  python scripts/manage_learning.py --user=1                  # Status für User 1
  python scripts/manage_learning.py --user=1 --reset          # Reset für User 1
  python scripts/manage_learning.py --tag=5 --reset           # Reset für Tag 5
  python scripts/manage_learning.py --user=1 --reset-negative # Nur Negative resetten

Score-Classifier (global):
  python scripts/manage_learning.py --classifiers             # Classifier-Status
  python scripts/manage_learning.py --reset-classifiers       # Alle Classifier löschen
        """
    )
    
    # Tag-Learning Argumente
    parser.add_argument("--list", action="store_true", help="Tag-Learning-Status aller User anzeigen")
    parser.add_argument("--user", type=int, help="User ID für Status oder Reset")
    parser.add_argument("--tag", type=int, help="Tag ID für Reset")
    parser.add_argument("--reset", action="store_true", help="Tag-Learning zurücksetzen (komplett)")
    parser.add_argument("--reset-negative", action="store_true", help="Nur Negative-Learning zurücksetzen")
    
    # Score-Classifier Argumente
    parser.add_argument("--classifiers", action="store_true", help="Score-Classifier Status anzeigen")
    parser.add_argument("--reset-classifiers", action="store_true", help="Alle Score-Classifier löschen")
    
    # Allgemein
    parser.add_argument("--force", action="store_true", help="Ohne Bestätigung")
    
    args = parser.parse_args()
    
    print("🧠 Learning Manager")
    print("=" * 70)
    print()
    
    # Score-Classifier Befehle
    if args.classifiers:
        success = list_classifiers()
    elif args.reset_classifiers:
        success = reset_classifiers(force=args.force)
    # Tag-Learning Befehle
    elif args.reset or args.reset_negative:
        success = reset_learning(
            user_id=args.user,
            tag_id=args.tag,
            reset_negative_only=args.reset_negative,
            force=args.force
        )
    elif args.list or args.user:
        success = list_learning_status(user_id=args.user)
    else:
        parser.print_help()
        success = True
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
