"""
PATCH: 01_web_app.py - Semantic Search API Endpoints
=====================================================

Füge diese Endpoints zu src/01_web_app.py hinzu.
"""

# =============================================================================
# IMPORTS (am Anfang der Datei hinzufügen)
# =============================================================================

from src.semantic_search import SemanticSearchService


# =============================================================================
# API ENDPOINTS (irgendwo bei den anderen API-Routes)
# =============================================================================

# -----------------------------------------------------------------------------
# Semantic Search
# -----------------------------------------------------------------------------

@app.route("/api/search/semantic", methods=["GET"])
@login_required
def semantic_search_endpoint():
    """
    Semantische Suche über Emails.
    
    Query Parameters:
        q: Suchbegriff (required)
        limit: Maximale Ergebnisse (default: 20, max: 100)
        threshold: Minimale Similarity 0.0-1.0 (default: 0.25)
        folder: Optional - nur in bestimmtem Ordner
        account_id: Optional - nur in bestimmtem Account
        
    Returns:
        {
            "results": [
                {
                    "email_id": 123,
                    "similarity": 0.87,
                    "subject": "Projektbudget Q1",
                    "sender": "alice@example.com",
                    "received_at": "2026-01-02T10:30:00",
                    "folder": "INBOX"
                },
                ...
            ],
            "query": "Budget",
            "total_results": 15,
            "threshold": 0.25
        }
    """
    query = request.args.get("q", "").strip()
    
    if not query:
        return jsonify({"error": "Parameter 'q' erforderlich"}), 400
    
    limit = min(int(request.args.get("limit", 20)), 100)
    threshold = float(request.args.get("threshold", 0.25))
    folder = request.args.get("folder")
    account_id = request.args.get("account_id", type=int)
    
    master_key = session.get("master_key")
    if not master_key:
        return jsonify({"error": "Nicht eingeloggt"}), 401
    
    # AI-Client für Query-Embedding
    try:
        ai_client = ai_client_mod.LocalOllamaClient(model="all-minilm:22m")
    except Exception as e:
        logger.error(f"AI-Client nicht verfügbar: {e}")
        return jsonify({"error": "AI-Service nicht verfügbar"}), 503
    
    # Suche durchführen
    service = SemanticSearchService(db_session=db.session, ai_client=ai_client)
    results = service.search(
        query=query,
        user_id=current_user.id,
        limit=limit,
        threshold=threshold,
        folder=folder,
        account_id=account_id
    )
    
    # Details für Ergebnisse entschlüsseln (nur Top-Ergebnisse!)
    enriched_results = []
    for r in results:
        try:
            email = db.session.get(models.RawEmail, r['email_id'])
            if not email:
                continue
            
            subject = encryption.EmailDataManager.decrypt_email_subject(
                email.encrypted_subject or "", master_key
            )
            sender = encryption.EmailDataManager.decrypt_email_sender(
                email.encrypted_sender or "", master_key
            )
            
            enriched_results.append({
                "email_id": r['email_id'],
                "similarity": round(r['similarity'], 3),
                "similarity_percent": round(r['similarity'] * 100),
                "subject": subject,
                "sender": sender,
                "received_at": r['received_at'],
                "folder": r['imap_folder'],
                "thread_id": r['thread_id'],
                "account_id": r['mail_account_id']
            })
        except Exception as e:
            logger.warning(f"Ergebnis {r['email_id']} Entschlüsselung fehlgeschlagen: {e}")
    
    return jsonify({
        "results": enriched_results,
        "query": query,
        "total_results": len(enriched_results),
        "threshold": threshold
    })


@app.route("/api/emails/<int:email_id>/similar", methods=["GET"])
@login_required
def find_similar_emails(email_id):
    """
    Findet ähnliche Emails zu einer gegebenen Email.
    
    Path Parameters:
        email_id: ID der Referenz-Email
        
    Query Parameters:
        limit: Maximale Ergebnisse (default: 10, max: 50)
        threshold: Minimale Similarity (default: 0.5)
        
    Returns:
        {
            "reference_email": { ... },
            "similar_emails": [ ... ],
            "total_found": 8
        }
    """
    limit = min(int(request.args.get("limit", 10)), 50)
    threshold = float(request.args.get("threshold", 0.5))
    
    master_key = session.get("master_key")
    if not master_key:
        return jsonify({"error": "Nicht eingeloggt"}), 401
    
    # Prüfen ob Email existiert und User gehört
    ref_email = db.session.query(models.RawEmail).filter_by(
        id=email_id,
        user_id=current_user.id
    ).first()
    
    if not ref_email:
        return jsonify({"error": "Email nicht gefunden"}), 404
    
    if not ref_email.email_embedding:
        return jsonify({
            "error": "Diese Email hat kein Embedding. Bitte erst Embeddings generieren.",
            "hint": "POST /api/embeddings/generate"
        }), 400
    
    # Ähnliche Emails finden
    service = SemanticSearchService(db_session=db.session)
    # Wir brauchen keinen AI-Client, da wir das vorhandene Embedding nutzen
    results = service.search_similar_to_email(
        email_id=email_id,
        user_id=current_user.id,
        limit=limit,
        threshold=threshold
    )
    
    # Referenz-Email Details
    ref_subject = encryption.EmailDataManager.decrypt_email_subject(
        ref_email.encrypted_subject or "", master_key
    )
    ref_sender = encryption.EmailDataManager.decrypt_email_sender(
        ref_email.encrypted_sender or "", master_key
    )
    
    # Ähnliche Emails entschlüsseln
    similar_emails = []
    for r in results:
        try:
            email = db.session.get(models.RawEmail, r['email_id'])
            if not email:
                continue
            
            subject = encryption.EmailDataManager.decrypt_email_subject(
                email.encrypted_subject or "", master_key
            )
            sender = encryption.EmailDataManager.decrypt_email_sender(
                email.encrypted_sender or "", master_key
            )
            
            similar_emails.append({
                "email_id": r['email_id'],
                "similarity": round(r['similarity'], 3),
                "similarity_percent": round(r['similarity'] * 100),
                "subject": subject,
                "sender": sender,
                "received_at": r['received_at'],
                "thread_id": r['thread_id']
            })
        except Exception as e:
            logger.warning(f"Similar Email {r['email_id']} Fehler: {e}")
    
    return jsonify({
        "reference_email": {
            "id": email_id,
            "subject": ref_subject,
            "sender": ref_sender
        },
        "similar_emails": similar_emails,
        "total_found": len(similar_emails)
    })


# -----------------------------------------------------------------------------
# Embedding Management
# -----------------------------------------------------------------------------

@app.route("/api/embeddings/stats", methods=["GET"])
@login_required
def get_embedding_stats():
    """
    Statistiken über Embedding-Coverage für aktuellen User.
    
    Returns:
        {
            "total_emails": 150,
            "with_embedding": 120,
            "without_embedding": 30,
            "coverage_percent": 80.0,
            "embedding_model": "all-minilm:22m"
        }
    """
    service = SemanticSearchService(db_session=db.session)
    stats = service.get_embedding_stats(user_id=current_user.id)
    return jsonify(stats)


@app.route("/api/embeddings/generate", methods=["POST"])
@login_required
def generate_missing_embeddings():
    """
    Generiert fehlende Embeddings für alle Emails des Users.
    
    Dies kann einige Zeit dauern bei vielen Emails!
    
    Query Parameters:
        batch_size: Emails pro Batch (default: 50, max: 200)
        
    Returns:
        {
            "processed": 30,
            "success": 28,
            "failed": 2,
            "message": "28 Embeddings generiert"
        }
    """
    master_key = session.get("master_key")
    if not master_key:
        return jsonify({"error": "Nicht eingeloggt"}), 401
    
    batch_size = min(int(request.args.get("batch_size", 50)), 200)
    
    # AI-Client
    try:
        ai_client = ai_client_mod.LocalOllamaClient(model="all-minilm:22m")
    except Exception as e:
        logger.error(f"AI-Client nicht verfügbar: {e}")
        return jsonify({"error": "AI-Service nicht verfügbar"}), 503
    
    # Emails ohne Embedding finden
    emails_without = db.session.query(models.RawEmail).filter(
        models.RawEmail.user_id == current_user.id,
        models.RawEmail.email_embedding.is_(None),
        models.RawEmail.deleted_at.is_(None)
    ).limit(batch_size).all()
    
    if not emails_without:
        return jsonify({
            "processed": 0,
            "success": 0,
            "failed": 0,
            "message": "Alle Emails haben bereits Embeddings"
        })
    
    success = 0
    failed = 0
    
    for email in emails_without:
        try:
            # Entschlüsseln
            subject = encryption.EmailDataManager.decrypt_email_subject(
                email.encrypted_subject or "", master_key
            )
            body = encryption.EmailDataManager.decrypt_email_body(
                email.encrypted_body or "", master_key
            )
            
            # Embedding generieren
            text = f"{subject}\n{body[:500]}"
            embedding_list = ai_client._get_embedding(text)
            
            if embedding_list:
                import numpy as np
                email.email_embedding = np.array(
                    embedding_list, dtype=np.float32
                ).tobytes()
                email.embedding_model = "all-minilm:22m"
                email.embedding_generated_at = datetime.now(UTC)
                success += 1
            else:
                failed += 1
                
        except Exception as e:
            logger.warning(f"Embedding für Email {email.id} fehlgeschlagen: {e}")
            failed += 1
    
    db.session.commit()
    
    # Prüfen ob noch mehr Emails ohne Embedding existieren
    remaining = db.session.query(models.RawEmail).filter(
        models.RawEmail.user_id == current_user.id,
        models.RawEmail.email_embedding.is_(None),
        models.RawEmail.deleted_at.is_(None)
    ).count()
    
    return jsonify({
        "processed": len(emails_without),
        "success": success,
        "failed": failed,
        "remaining": remaining,
        "message": f"{success} Embeddings generiert" + (
            f", {remaining} verbleibend" if remaining > 0 else ""
        )
    })
