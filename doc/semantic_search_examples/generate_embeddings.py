#!/usr/bin/env python3
"""
Phase 15: Generate Embeddings für bestehende Emails
===================================================

Dieses Script generiert Embeddings für Emails, die VOR Phase 15 
gespeichert wurden (also ohne Embedding).

WICHTIG: 
- Muss als eingeloggter User ausgeführt werden (braucht master_key!)
- Oder: User-Credentials als Parameter übergeben

Usage (als CLI):
    cd /path/to/KI-Mail-Helper
    source venv/bin/activate
    
    # Option 1: Für alle User (braucht Admin-Zugang zu Passwörtern)
    python scripts/generate_embeddings.py --all-users
    
    # Option 2: Für einen User (interaktiv, fragt nach Passwort)
    python scripts/generate_embeddings.py --user thomas@example.com
    
    # Option 3: Batch-Size anpassen
    python scripts/generate_embeddings.py --user thomas@example.com --batch-size 50
    
    # Option 4: Dry-Run (zeigt nur was gemacht würde)
    python scripts/generate_embeddings.py --user thomas@example.com --dry-run

Usage (als Flask-Endpoint für eingeloggte User):
    POST /api/generate-embeddings
    → Generiert Embeddings für aktuellen User
"""

import argparse
import sys
import os
import logging
import getpass
from datetime import datetime, UTC
from typing import Optional, Tuple
import numpy as np

# Path setup
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class EmbeddingGenerator:
    """Generiert Embeddings für bestehende Emails"""
    
    EMBEDDING_MODEL = "all-minilm:22m"
    
    def __init__(self, db_path: str = 'emails.db', batch_size: int = 50):
        self.db_path = db_path
        self.batch_size = batch_size
        self.engine = create_engine(f'sqlite:///{db_path}')
        self.Session = sessionmaker(bind=self.engine)
        
        # Lazy imports
        self.models = None
        self.encryption = None
        self.ai_client = None
    
    def _init_modules(self):
        """Lazy import der Module"""
        if self.models is None:
            import importlib
            self.models = importlib.import_module('src.02_models')
            self.encryption = importlib.import_module('src.08_encryption')
            ai_module = importlib.import_module('src.03_ai_client')
            self.ai_client = ai_module.LocalOllamaClient(model=self.EMBEDDING_MODEL)
    
    def get_master_key_for_user(self, username: str, password: str) -> Optional[str]:
        """
        Generiert Master-Key aus User-Credentials.
        
        ACHTUNG: Dies ist nur für Migration-Zwecke!
        Im normalen Betrieb kommt der Key aus der Flask-Session.
        """
        self._init_modules()
        session = self.Session()
        
        try:
            user = session.query(self.models.User).filter_by(
                username=username
            ).first()
            
            if not user:
                logger.error(f"User '{username}' nicht gefunden")
                return None
            
            if not user.check_password(password):
                logger.error(f"Falsches Passwort für '{username}'")
                return None
            
            # Master-Key aus Passwort ableiten
            # PBKDF2 wie in 07_auth.py
            from src.auth_helpers import derive_master_key
            master_key = derive_master_key(password, user.salt)
            
            return master_key
            
        except Exception as e:
            logger.error(f"Master-Key Generierung fehlgeschlagen: {e}")
            return None
        finally:
            session.close()
    
    def generate_for_user(
        self, 
        user_id: int, 
        master_key: str,
        dry_run: bool = False
    ) -> Tuple[int, int, int]:
        """
        Generiert Embeddings für alle Emails eines Users ohne Embedding.
        
        Args:
            user_id: User ID
            master_key: Master-Key für Entschlüsselung
            dry_run: Wenn True, keine Änderungen speichern
            
        Returns:
            (processed, success, failed)
        """
        self._init_modules()
        session = self.Session()
        
        try:
            # Emails ohne Embedding finden
            emails_without_embedding = session.query(self.models.RawEmail).filter(
                self.models.RawEmail.user_id == user_id,
                self.models.RawEmail.email_embedding.is_(None),
                self.models.RawEmail.deleted_at.is_(None)
            ).all()
            
            total = len(emails_without_embedding)
            
            if total == 0:
                logger.info(f"✅ Alle Emails haben bereits Embeddings!")
                return 0, 0, 0
            
            logger.info(f"📊 {total} Emails ohne Embedding gefunden")
            
            if dry_run:
                logger.info(f"🔍 DRY-RUN: Würde {total} Emails verarbeiten")
                return total, 0, 0
            
            success = 0
            failed = 0
            
            for i, email in enumerate(emails_without_embedding, 1):
                try:
                    # Entschlüsseln
                    subject = self.encryption.EmailDataManager.decrypt_email_subject(
                        email.encrypted_subject or "", master_key
                    )
                    body = self.encryption.EmailDataManager.decrypt_email_body(
                        email.encrypted_body or "", master_key
                    )
                    
                    # Embedding generieren
                    text = f"{subject}\n{body[:500]}"
                    embedding_list = self.ai_client._get_embedding(text)
                    
                    if embedding_list:
                        embedding_bytes = np.array(
                            embedding_list, dtype=np.float32
                        ).tobytes()
                        
                        email.email_embedding = embedding_bytes
                        email.embedding_model = self.EMBEDDING_MODEL
                        email.embedding_generated_at = datetime.now(UTC)
                        
                        success += 1
                    else:
                        logger.warning(f"  ⚠️ Email {email.id}: Kein Embedding erhalten")
                        failed += 1
                    
                    # Batch-Commit
                    if i % self.batch_size == 0:
                        session.commit()
                        pct = (i / total) * 100
                        logger.info(f"  ✅ {i}/{total} ({pct:.0f}%) - {success} OK, {failed} Failed")
                
                except Exception as e:
                    logger.warning(f"  ❌ Email {email.id}: {e}")
                    failed += 1
            
            # Final commit
            session.commit()
            
            logger.info(f"\n✅ Fertig!")
            logger.info(f"   Verarbeitet: {total}")
            logger.info(f"   Erfolgreich: {success}")
            logger.info(f"   Fehlgeschlagen: {failed}")
            
            return total, success, failed
            
        except Exception as e:
            logger.error(f"❌ Fehler: {e}")
            session.rollback()
            raise
        finally:
            session.close()
    
    def get_stats(self, user_id: int) -> dict:
        """Statistiken über Embedding-Coverage"""
        self._init_modules()
        session = self.Session()
        
        try:
            total = session.query(self.models.RawEmail).filter(
                self.models.RawEmail.user_id == user_id,
                self.models.RawEmail.deleted_at.is_(None)
            ).count()
            
            with_embedding = session.query(self.models.RawEmail).filter(
                self.models.RawEmail.user_id == user_id,
                self.models.RawEmail.email_embedding.isnot(None),
                self.models.RawEmail.deleted_at.is_(None)
            ).count()
            
            return {
                'total': total,
                'with_embedding': with_embedding,
                'without_embedding': total - with_embedding,
                'coverage_percent': round((with_embedding / total * 100) if total > 0 else 0, 1)
            }
        finally:
            session.close()


# =============================================================================
# FLASK ENDPOINT (für eingeloggte User)
# =============================================================================

def register_embedding_endpoints(app, db):
    """
    Registriert Flask-Endpoints für Embedding-Generierung.
    
    Füge dies in 01_web_app.py ein:
    
        from scripts.generate_embeddings import register_embedding_endpoints
        register_embedding_endpoints(app, db)
    """
    from flask import jsonify, session
    from flask_login import login_required, current_user
    
    @app.route("/api/embeddings/generate", methods=["POST"])
    @login_required
    def generate_embeddings_for_current_user():
        """Generiert fehlende Embeddings für eingeloggten User"""
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Nicht eingeloggt"}), 401
        
        generator = EmbeddingGenerator()
        total, success, failed = generator.generate_for_user(
            user_id=current_user.id,
            master_key=master_key
        )
        
        return jsonify({
            "processed": total,
            "success": success,
            "failed": failed,
            "message": f"{success} Embeddings generiert"
        })
    
    @app.route("/api/embeddings/stats", methods=["GET"])
    @login_required
    def get_embedding_stats():
        """Statistiken über Embedding-Coverage"""
        generator = EmbeddingGenerator()
        stats = generator.get_stats(user_id=current_user.id)
        return jsonify(stats)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Generate Embeddings für bestehende Emails (Phase 15)'
    )
    parser.add_argument(
        '--db',
        default='emails.db',
        help='Path to database (default: emails.db)'
    )
    parser.add_argument(
        '--user',
        help='Username für den Embeddings generiert werden sollen'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Batch size für Commits (default: 50)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Zeigt nur was gemacht würde, ohne Änderungen'
    )
    parser.add_argument(
        '--stats-only',
        action='store_true',
        help='Zeigt nur Statistiken, generiert keine Embeddings'
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.db):
        logger.error(f"❌ Database nicht gefunden: {args.db}")
        sys.exit(1)
    
    generator = EmbeddingGenerator(args.db, args.batch_size)
    
    if not args.user:
        logger.error("❌ --user Parameter erforderlich")
        logger.info("   Beispiel: python generate_embeddings.py --user thomas@example.com")
        sys.exit(1)
    
    # Passwort abfragen
    password = getpass.getpass(f"Passwort für {args.user}: ")
    
    # Master-Key generieren
    logger.info(f"🔑 Generiere Master-Key für {args.user}...")
    master_key = generator.get_master_key_for_user(args.user, password)
    
    if not master_key:
        logger.error("❌ Login fehlgeschlagen")
        sys.exit(1)
    
    # User-ID holen
    generator._init_modules()
    session = generator.Session()
    user = session.query(generator.models.User).filter_by(username=args.user).first()
    session.close()
    
    if not user:
        logger.error(f"❌ User '{args.user}' nicht gefunden")
        sys.exit(1)
    
    # Stats anzeigen
    stats = generator.get_stats(user.id)
    logger.info(f"\n📊 Aktuelle Statistiken für {args.user}:")
    logger.info(f"   Emails gesamt: {stats['total']}")
    logger.info(f"   Mit Embedding: {stats['with_embedding']}")
    logger.info(f"   Ohne Embedding: {stats['without_embedding']}")
    logger.info(f"   Coverage: {stats['coverage_percent']}%")
    
    if args.stats_only:
        sys.exit(0)
    
    if stats['without_embedding'] == 0:
        logger.info("\n✅ Alle Emails haben bereits Embeddings!")
        sys.exit(0)
    
    # Embeddings generieren
    logger.info(f"\n🚀 Starte Embedding-Generierung...")
    
    try:
        total, success, failed = generator.generate_for_user(
            user_id=user.id,
            master_key=master_key,
            dry_run=args.dry_run
        )
        
        if failed > 0:
            logger.warning(f"\n⚠️ {failed} Emails konnten nicht verarbeitet werden")
            sys.exit(1)
        else:
            logger.info(f"\n✅ Erfolgreich abgeschlossen!")
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
