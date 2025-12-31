"""
Thread & Conversation API Blueprint (Phase 12)
===============================================
REST Endpoints für Thread-basierte Email-Views.

Endpoints:
  GET  /api/threads              - Alle Thread-Zusammenfassungen
  GET  /api/threads/{thread_id}  - Einzelner Thread mit all seinen Emails
  GET  /api/threads/search       - Thread-Suche (Subject + Sender)
"""

from flask import Blueprint, jsonify, request, session, current_app
from flask_login import login_required, current_user
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import os
import logging
import importlib

models = importlib.import_module(".02_models", "src")
encryption = importlib.import_module(".08_encryption", "src")
thread_service = importlib.import_module(".thread_service", "src")

logger = logging.getLogger(__name__)

thread_api = Blueprint("thread_api", __name__, url_prefix="/api/threads")

DATABASE_PATH = os.getenv("DATABASE_PATH", "emails.db")


def get_db_session():
    """Erstellt eine DB-Session (identisch zu 01_web_app.py)"""
    engine = create_engine(f"sqlite:///{DATABASE_PATH}")
    Session = sessionmaker(bind=engine)
    return Session()


def get_current_user_model(db):
    """Holt das aktuelle User-Model aus DB (identisch zu 01_web_app.py)"""
    if not current_user.is_authenticated:
        return None
    return db.query(models.User).filter_by(id=current_user.id).first()


def decrypt_email(encrypted_text: str, master_key: str) -> str:
    """Helper: Decrypt email data"""
    if not encrypted_text:
        return ""
    try:
        return encryption.EncryptionManager.decrypt_data(encrypted_text, master_key)
    except Exception as e:
        logger.debug(f"Decryption failed: {e}")
        return "[Decryption Error]"


@thread_api.route("", methods=["GET"])
def get_threads_endpoint():
    """GET /api/threads - Alle Threads mit Zusammenfassungen
    
    Query Params:
      limit: Max Threads (default: 50)
      offset: Pagination (default: 0)
      
    Returns:
      {
        "threads": [
          {
            "thread_id": "uuid",
            "count": 5,
            "latest_date": "2025-12-30T12:00:00",
            "oldest_date": "2025-12-20T09:00:00",
            "has_unread": true,
            "latest_sender": "[encrypted]",
            "subject": "Original Subject"  // decrypted
          },
          ...
        ],
        "total": 42
      }
    """
    if not current_user.is_authenticated:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "No decryption key"}), 401
        
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)
        
        summaries = thread_service.ThreadService.get_threads_summary(
            db, user.id, limit=limit, offset=offset
        )
        
        result = []
        for summary in summaries:
            subject = summary.get('root_subject')
            if not subject and summary['thread_id']:
                # Fallback: Only query if root_subject is missing
                subject = thread_service.ThreadService.get_thread_subject(
                    db, user.id, summary['thread_id']
                )
            
            result.append({
                'thread_id': summary['thread_id'],
                'count': summary['count'],
                'latest_date': summary['latest_date'].isoformat() if summary['latest_date'] else None,
                'oldest_date': summary['oldest_date'].isoformat() if summary['oldest_date'] else None,
                'has_unread': summary['has_unread'],
                'latest_sender': decrypt_email(summary['latest_sender'], master_key),
                'subject': decrypt_email(subject, master_key) if subject else 'No Subject',
            })
        
        return jsonify({
            'threads': result,
            'total': len(result),
            'limit': limit,
            'offset': offset,
        }), 200
            
    except Exception as e:
        db.rollback()
        logger.error(f"Error getting threads: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@thread_api.route("/<thread_id>", methods=["GET"])
def get_conversation_endpoint(thread_id: str):
    """GET /api/threads/{thread_id} - Single Thread mit all seinen Emails
    
    Returns:
      {
        "thread_id": "uuid",
        "emails": [
          {
            "id": 1,
            "imap_uid": "205",
            "message_id": "msg@server",
            "parent_uid": null,
            "received_at": "2025-12-20T09:00:00",
            "sender": "John Doe <john@example.com>",
            "subject": "Hello",
            "preview": "First 100 chars...",
            "has_attachments": false,
            "is_seen": true,
            "is_answered": false
          },
          ...
        ],
        "reply_chain": {
          "205": {
            "children": ["206", "207"],
            "parent": null
          },
          ...
        },
        "stats": {...}
      }
    """
    if not current_user.is_authenticated:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "No decryption key"}), 401
        
        emails = thread_service.ThreadService.get_conversation(
            db, user.id, thread_id
        )
        
        if not emails:
            return jsonify({"error": "Thread not found"}), 404
        
        email_list = []
        for email in emails:
            # Decrypt body before creating preview
            decrypted_body = decrypt_email(email.encrypted_body, master_key)
            preview = decrypted_body[:100] if decrypted_body else ""
            
            email_list.append({
                'id': email.id,
                'imap_uid': email.imap_uid,
                'message_id': email.message_id,
                'parent_uid': email.parent_uid,
                'received_at': email.received_at.isoformat() if email.received_at else None,
                'sender': decrypt_email(email.encrypted_sender, master_key),
                'subject': decrypt_email(email.encrypted_subject, master_key),
                'preview': preview[:100],
                'has_attachments': email.has_attachments,
                'is_seen': email.imap_is_seen,
                'is_answered': email.imap_is_answered,
            })
        
        reply_chain = thread_service.ThreadService.get_reply_chain(db, user.id, thread_id)
        
        chain_map = {}
        for uid, data in reply_chain.items():
            chain_map[uid] = {
                'parent': data['parent_uid'],
                'children': data['children']
            }
        
        stats = thread_service.ThreadService.get_thread_stats(db, user.id, thread_id)
        
        return jsonify({
            'thread_id': thread_id,
            'emails': email_list,
            'reply_chain': chain_map,
            'stats': stats,
        }), 200
            
    except Exception as e:
        db.rollback()
        logger.error(f"Error getting conversation: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@thread_api.route("/search", methods=["GET"])
def search_threads_endpoint():
    """GET /api/threads/search?q=<query> - Search Threads
    
    Query Params:
      q: Suchstring (in Subject + Sender)
      limit: Max Results (default: 20)
      
    Returns:
      Ähnlich /api/threads
    """
    if not current_user.is_authenticated:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "No decryption key"}), 401
        
        query = request.args.get("q", "", type=str)
        if not query or len(query) < 2:
            return jsonify({"error": "Query too short (min 2 chars)"}), 400
        
        limit = request.args.get("limit", 20, type=int)
        
        results = thread_service.ThreadService.search_conversations(
            db, user.id, query, limit=limit
        )
        
        result = []
        for summary in results:
            subject = summary.get('root_subject')
            if not subject and summary['thread_id']:
                # Fallback: Only query if root_subject is missing
                subject = thread_service.ThreadService.get_thread_subject(
                    db, user.id, summary['thread_id']
                )
            
            result.append({
                'thread_id': summary['thread_id'],
                'count': summary['count'],
                'latest_date': summary['latest_date'].isoformat() if summary['latest_date'] else None,
                'has_unread': summary['has_unread'],
                'latest_sender': decrypt_email(summary['latest_sender'], master_key),
                'subject': decrypt_email(subject, master_key) if subject else 'No Subject',
            })
        
        return jsonify({
            'query': query,
            'results': result,
            'total': len(result),
        }), 200
            
    except Exception as e:
        db.rollback()
        logger.error(f"Error searching threads: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()
