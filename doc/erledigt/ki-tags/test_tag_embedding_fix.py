#!/usr/bin/env python3
"""
Test-Script: Verifiziert, dass Tag-Embeddings korrekt generiert werden

Usage:
    python3 test_tag_embedding_fix.py --user-id 1 --tag-name "AGB Richtlinien"
"""

import sys
import argparse
from pathlib import Path
import numpy as np

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import models & services
import importlib
models = importlib.import_module("02_models")
tag_manager = importlib.import_module("src.services.tag_manager")


def cosine_similarity(vec1, vec2):
    """Berechnet Cosine Similarity zwischen zwei Vektoren"""
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


def main():
    parser = argparse.ArgumentParser(
        description="Test Tag-Embedding Fix"
    )
    parser.add_argument(
        "--user-id",
        type=int,
        required=True,
        help="User ID"
    )
    parser.add_argument(
        "--tag-name",
        type=str,
        required=True,
        help="Tag Name zum Testen (z.B. 'AGB Richtlinien')"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="mail_helper.db",
        help="Pfad zur Datenbank"
    )
    
    args = parser.parse_args()
    
    # Database connection
    engine = create_engine(f"sqlite:///{args.db}")
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        print("\n" + "="*80)
        print("TAG-EMBEDDING BUG VERIFICATION TEST")
        print("="*80 + "\n")
        
        # 1. Check User
        user = db.query(models.User).filter_by(id=args.user_id).first()
        if not user:
            print(f"❌ User ID {args.user_id} nicht gefunden!")
            sys.exit(1)
        
        print(f"✅ User: {user.email}")
        
        # 2. Check Tag
        tag = db.query(models.EmailTag).filter_by(
            user_id=args.user_id,
            name=args.tag_name
        ).first()
        
        if not tag:
            print(f"❌ Tag '{args.tag_name}' nicht gefunden!")
            sys.exit(1)
        
        print(f"✅ Tag: {tag.name}")
        if tag.description:
            print(f"   Description: {tag.description[:100]}...")
        else:
            print("   ⚠️  Keine Description!")
        
        # 3. Test Tag-Embedding Generation
        print("\n📊 Teste Tag-Embedding Generierung...")
        print("-" * 80)
        
        # Get AI Client
        client = tag_manager.TagEmbeddingCache._get_ai_client_for_user(
            args.user_id, db
        )
        
        if not client:
            print("❌ AI-Client konnte nicht erstellt werden!")
            sys.exit(1)
        
        # Check Client Type
        client_class = client.__class__.__name__
        print(f"   Client Type: {client_class}")
        
        if client_class == "LocalOllamaClient":
            print("   ❌ FEHLER: Nutzt LocalOllamaClient (Chat-Model)!")
            print("   → Dies ist der BUG! Sollte OllamaEmbeddingClient sein.")
            print("\n   FIX benötigt: Siehe FIX_TAG_EMBEDDING_BUG.md")
            sys.exit(1)
        elif client_class == "OllamaEmbeddingClient":
            print("   ✅ Nutzt OllamaEmbeddingClient (Embedding-Model) - KORREKT!")
        else:
            print(f"   ⚠️  Unbekannter Client-Type: {client_class}")
        
        # 4. Generate Tag-Embedding
        text_for_embedding = tag.description if tag.description else tag.name
        print(f"\n   Generiere Embedding für: '{text_for_embedding[:80]}...'")
        
        # Use correct method based on client type
        if hasattr(client, 'get_embedding'):
            tag_embedding = client.get_embedding(text_for_embedding)
        elif hasattr(client, '_get_embedding'):
            tag_embedding = client._get_embedding(text_for_embedding)
        else:
            print("   ❌ Client hat keine Embedding-Methode!")
            sys.exit(1)
        
        if not tag_embedding:
            print("   ❌ Embedding-Generierung fehlgeschlagen!")
            sys.exit(1)
        
        tag_emb_array = np.array(tag_embedding, dtype=np.float32)
        print(f"   ✅ Tag-Embedding generiert: {len(tag_emb_array)} Dimensionen")
        
        # 5. Compare with Email-Embedding
        print("\n📧 Teste Vergleich mit Email-Embeddings...")
        print("-" * 80)
        
        # Find email with embedding
        email_with_embedding = db.query(models.RawEmail).filter(
            models.RawEmail.user_id == args.user_id,
            models.RawEmail.email_embedding.isnot(None)
        ).first()
        
        if not email_with_embedding:
            print("   ⚠️  Keine Email mit Embedding gefunden")
            print("   (Test kann Similarity nicht prüfen)")
        else:
            email_emb_array = np.frombuffer(
                email_with_embedding.email_embedding,
                dtype=np.float32
            )
            
            print(f"   Email-Embedding: {len(email_emb_array)} Dimensionen")
            print(f"   Model: {email_with_embedding.embedding_model}")
            
            # Dimension Check
            if len(tag_emb_array) != len(email_emb_array):
                print(f"\n   ❌ DIMENSION MISMATCH!")
                print(f"      Tag: {len(tag_emb_array)} dims")
                print(f"      Email: {len(email_emb_array)} dims")
                print("\n   → Tag-Embeddings nutzen anderes Model als Email-Embeddings!")
                sys.exit(1)
            else:
                print(f"   ✅ Dimensionen stimmen überein: {len(tag_emb_array)}")
            
            # Similarity Check
            similarity = cosine_similarity(tag_emb_array, email_emb_array)
            print(f"\n   Similarity: {similarity:.4f} ({similarity*100:.2f}%)")
            
            if similarity < 0.20:
                print("   ❌ Sehr niedrige Similarity!")
                print("   → Tag-Embeddings scheinen falsch zu sein")
                print("   → Vermutlich wird Chat-API statt Embeddings-API genutzt")
            elif similarity >= 0.70:
                print("   ✅ Hohe Similarity - Tag-Embeddings scheinen korrekt!")
            else:
                print("   ⚠️  Moderate Similarity - könnte OK sein oder nicht")
        
        # 6. Test with real emails if exists
        print("\n🔍 Teste mit relevanten Emails...")
        print("-" * 80)
        
        # Find relevant emails matching tag description
        relevant_emails = db.query(models.RawEmail).filter(
            models.RawEmail.user_id == args.user_id,
            models.RawEmail.email_embedding.isnot(None)
        ).limit(5).all()
        
        if not relevant_emails:
            print("   ⚠️  Keine relevanten Emails gefunden")
        else:
            print(f"   Teste mit {len(relevant_emails)} Emails:")
            
            for email in relevant_emails:
                email_emb = np.frombuffer(email.email_embedding, dtype=np.float32)
                similarity = cosine_similarity(tag_emb_array, email_emb)
                
                # Status Icon
                if similarity >= 0.80:
                    icon = "🟢"
                    status = "AUTO-ASSIGN"
                elif similarity >= 0.70:
                    icon = "🟡"
                    status = "SUGGEST"
                else:
                    icon = "🔴"
                    status = "SKIP"
                
                print(f"   {icon} [{status:12s}] {similarity:.4f} ({similarity*100:.2f}%) - "
                      f"{email.email_subject[:60]}...")
            
            # Average Similarity
            avg_similarity = np.mean([
                cosine_similarity(tag_emb_array, np.frombuffer(e.email_embedding, dtype=np.float32))
                for e in relevant_emails
            ])
            
            print(f"\n   Durchschnitt: {avg_similarity:.4f} ({avg_similarity*100:.2f}%)")
            
            if avg_similarity >= 0.75:
                print("   ✅ EXCELLENT! Tag-Embeddings funktionieren perfekt!")
            elif avg_similarity >= 0.50:
                print("   ⚠️  Tag-Embeddings scheinen zu funktionieren, aber nicht optimal")
            else:
                print("   ❌ Tag-Embeddings funktionieren NICHT korrekt!")
                print("   → Siehe FIX_TAG_EMBEDDING_BUG.md für Lösung")
        
        print("\n" + "="*80)
        print("TEST ABGESCHLOSSEN")
        print("="*80 + "\n")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()
