"""
Thread & Conversation Service (Phase 12)
=========================================
Hilfs-Methoden für Thread-basierte Email-Queries.

Verwendet: thread_id, parent_uid, message_id, received_at
"""

from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, case
import importlib

models = importlib.import_module(".02_models", "src")


class ThreadService:
    """Service für Thread- und Conversation-Queries"""

    @staticmethod
    def get_conversation(
        session: Session, user_id: int, thread_id: str
    ) -> List[models.RawEmail]:
        """Holt alle Emails in einem Thread, sortiert nach Datum
        
        Args:
            session: SQLAlchemy Session
            user_id: User ID
            thread_id: UUID des Threads
            
        Returns:
            Liste von RawEmails in Conversation (zeitlich sortiert)
        """
        return (
            session.query(models.RawEmail)
            .filter_by(user_id=user_id, thread_id=thread_id)
            .order_by(models.RawEmail.received_at.asc())
            .all()
        )

    @staticmethod
    def get_reply_chain(
        session: Session, user_id: int, thread_id: str
    ) -> Dict[str, Dict[str, Any]]:
        """Erstellt Parent-Child Mapping für Thread-Visualisierung
        
        Args:
            session: SQLAlchemy Session
            user_id: User ID
            thread_id: UUID des Threads
            
        Returns:
            Dict mapping uid → {email, parent_uid, children_uids}
            
        Example:
            {
                '205': {
                    'email': RawEmail(id=1, ...),
                    'parent_uid': None,
                    'children': ['206', '207']
                },
                '206': {
                    'email': RawEmail(id=2, ...),
                    'parent_uid': '205',
                    'children': []
                }
            }
        """
        emails = ThreadService.get_conversation(session, user_id, thread_id)
        
        result = {}
        for email in emails:
            result[email.imap_uid] = {
                'email': email,
                'parent_uid': email.parent_uid,
                'children': []
            }
        
        for uid, data in result.items():
            if data['parent_uid'] and data['parent_uid'] in result:
                result[data['parent_uid']]['children'].append(uid)
        
        return result

    @staticmethod
    def get_threads_summary(
        session: Session, user_id: int, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Holt Thread-Zusammenfassungen mit Count, neuest, älteste Email
        
        Args:
            session: SQLAlchemy Session
            user_id: User ID
            limit: Max Anzahl Threads
            offset: Pagination offset
            
        Returns:
            Liste von {
                thread_id, 
                count (Anzahl Emails), 
                latest_uid, 
                latest_date, 
                latest_subject,
                oldest_date,
                has_unread
            }
        """
        subquery = (
            session.query(
                models.RawEmail.thread_id,
                func.count(models.RawEmail.id).label('count'),
                func.max(models.RawEmail.received_at).label('latest_date'),
                func.min(models.RawEmail.received_at).label('oldest_date'),
                func.sum(
                    case((models.RawEmail.imap_is_seen == False, 1), else_=0)
                ).label('unread_count'),
            )
            .filter(models.RawEmail.user_id == user_id)
            .filter(models.RawEmail.thread_id.isnot(None))
            .group_by(models.RawEmail.thread_id)
            .order_by(func.max(models.RawEmail.received_at).desc())
            .limit(limit)
            .offset(offset)
            .subquery()
        )
        
        results = session.query(subquery).all()
        
        summary = []
        for row in results:
            thread_id, count, latest_date, oldest_date, unread = row
            
            latest_email = (
                session.query(models.RawEmail)
                .filter_by(user_id=user_id, thread_id=thread_id)
                .order_by(models.RawEmail.received_at.desc())
                .first()
            )
            
            root_email = (
                session.query(models.RawEmail)
                .filter_by(user_id=user_id, thread_id=thread_id)
                .order_by(models.RawEmail.received_at.asc())
                .first()
            )
            
            summary.append({
                'thread_id': thread_id,
                'count': count,
                'latest_uid': latest_email.imap_uid if latest_email else None,
                'latest_date': latest_date,
                'oldest_date': oldest_date,
                'has_unread': (unread or 0) > 0,
                'latest_sender': (
                    latest_email.encrypted_sender if latest_email else None
                ),
                'root_subject': root_email.encrypted_subject if root_email else None,
            })
        
        return summary

    @staticmethod
    def get_thread_subject(
        session: Session, user_id: int, thread_id: str
    ) -> Optional[str]:
        """Holt Subject des Thread-Roots (erste Email)
        
        Args:
            session: SQLAlchemy Session
            user_id: User ID
            thread_id: UUID des Threads
            
        Returns:
            Encrypted subject (wird im Frontend entschlüsselt)
        """
        root = (
            session.query(models.RawEmail)
            .filter_by(user_id=user_id, thread_id=thread_id)
            .order_by(models.RawEmail.received_at.asc())
            .first()
        )
        
        return root.encrypted_subject if root else None

    @staticmethod
    def search_conversations(
        session: Session,
        user_id: int,
        query: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Sucht in Conversations (Subject + Sender)
        
        Args:
            session: SQLAlchemy Session
            user_id: User ID
            query: Suchstring
            limit: Max Results
            
        Returns:
            Ähnlich get_threads_summary()
        """
        subquery = (
            session.query(models.RawEmail.thread_id)
            .filter_by(user_id=user_id)
            .filter(
                (models.RawEmail.encrypted_subject.ilike(f"%{query}%"))
                | (models.RawEmail.encrypted_sender.ilike(f"%{query}%"))
            )
            .distinct()
            .limit(limit)
            .subquery()
        )
        
        thread_ids = session.query(subquery).all()
        
        result = []
        for (thread_id,) in thread_ids:
            summary = ThreadService.get_threads_summary(
                session, user_id, limit=1, offset=0
            )
            for item in summary:
                if item['thread_id'] == thread_id:
                    result.append(item)
        
        return result

    @staticmethod
    def get_thread_stats(
        session: Session, user_id: int, thread_id: str
    ) -> Dict[str, Any]:
        """Detaillierte Thread-Statistik
        
        Args:
            session: SQLAlchemy Session
            user_id: User ID
            thread_id: UUID des Threads
            
        Returns:
            {
                count, 
                unread_count,
                has_attachments_count,
                senders_set,
                span_days
            }
        """
        emails = ThreadService.get_conversation(session, user_id, thread_id)
        
        if not emails:
            return {}
        
        unread = sum(1 for e in emails if not e.imap_is_seen)
        with_attachments = sum(1 for e in emails if e.has_attachments)
        
        span_days = (emails[-1].received_at - emails[0].received_at).days if emails else 0
        
        return {
            'count': len(emails),
            'unread_count': unread,
            'with_attachments_count': with_attachments,
            'span_days': span_days,
            'latest_date': emails[-1].received_at if emails else None,
            'oldest_date': emails[0].received_at if emails else None,
        }
