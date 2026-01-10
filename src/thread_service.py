"""
Thread & Conversation Service (Phase 12)
=========================================
Helper methods for thread-based email queries.

Uses: thread_id, parent_uid, message_id, received_at
"""

from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_
import importlib
import logging

models = importlib.import_module(".02_models", "src")
logger = logging.getLogger(__name__)


class ThreadService:
    """Service for thread and conversation queries"""

    @staticmethod
    def get_conversation(
        session: Session, user_id: int, thread_id: str
    ) -> List[models.RawEmail]:
        """Get all emails in a thread, sorted by date
        
        Args:
            session: SQLAlchemy session
            user_id: User ID
            thread_id: Thread UUID
            
        Returns:
            List of RawEmails in conversation (chronologically sorted)
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
        """Create parent-child mapping for thread visualization with cycle detection
        
        Args:
            session: SQLAlchemy session
            user_id: User ID
            thread_id: Thread UUID
            
        Returns:
            Dict mapping uid → {email, parent_uid, children}
            
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
        
        visited = set()
        for uid, data in result.items():
            if data['parent_uid'] and data['parent_uid'] in result:
                parent_uid = data['parent_uid']
                
                if uid in visited:
                    logger.warning(f"Circular parent reference detected for uid={uid} in thread={thread_id}")
                    continue
                
                result[parent_uid]['children'].append(uid)
                visited.add(uid)
        
        return result

    @staticmethod
    def get_threads_summary(
        session: Session, user_id: int, limit: int = 50, offset: int = 0,
        thread_ids: Optional[List[str]] = None, account_id: Optional[int] = None,
        min_count: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get thread summaries with count, latest and oldest email
        
        Args:
            session: SQLAlchemy session
            user_id: User ID
            limit: Maximum number of threads to return
            offset: Pagination offset
            thread_ids: Optional - only load these threads (for search optimization)
            account_id: Optional - filter by mail_account_id
            min_count: Optional - minimum emails in thread (e.g. 2 = only conversations)
            
        Returns:
            List of {
                thread_id, 
                count (email count), 
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
        )
        
        if thread_ids:
            subquery = subquery.filter(models.RawEmail.thread_id.in_(thread_ids))
        
        if account_id:
            subquery = subquery.filter(models.RawEmail.mail_account_id == account_id)
        
        subquery = subquery.group_by(models.RawEmail.thread_id)
        
        # HAVING für min_count (nach GROUP BY!)
        if min_count and min_count > 0:
            subquery = subquery.having(func.count(models.RawEmail.id) >= min_count)
        
        subquery = (
            subquery
            .order_by(func.max(models.RawEmail.received_at).desc())
            .limit(limit)
            .offset(offset)
            .subquery()
        )
        
        results = session.query(subquery).all()
        
        if not results:
            return []
        
        result_thread_ids = [row[0] for row in results]
        
        latest_emails = (
            session.query(models.RawEmail)
            .filter_by(user_id=user_id)
            .filter(models.RawEmail.thread_id.in_(result_thread_ids))
            .order_by(models.RawEmail.thread_id, models.RawEmail.received_at.desc())
            .all()
        )
        
        root_emails = (
            session.query(models.RawEmail)
            .filter_by(user_id=user_id)
            .filter(models.RawEmail.thread_id.in_(result_thread_ids))
            .order_by(models.RawEmail.thread_id, models.RawEmail.received_at.asc())
            .all()
        )
        
        latest_map = {}
        root_map = {}
        seen_latest = set()
        seen_root = set()
        
        for email in latest_emails:
            if email.thread_id not in seen_latest:
                latest_map[email.thread_id] = email
                seen_latest.add(email.thread_id)
        
        for email in root_emails:
            if email.thread_id not in seen_root:
                root_map[email.thread_id] = email
                seen_root.add(email.thread_id)
        
        summary = []
        for row in results:
            thread_id, count, latest_date, oldest_date, unread = row
            latest_email = latest_map.get(thread_id)
            root_email = root_map.get(thread_id)
            
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
        """Get subject of thread root email (email with parent_uid=NULL)
        
        Args:
            session: SQLAlchemy session
            user_id: User ID
            thread_id: Thread UUID
            
        Returns:
            Encrypted subject (decrypted on frontend)
        """
        root = (
            session.query(models.RawEmail)
            .filter_by(user_id=user_id, thread_id=thread_id, parent_uid=None)
            .order_by(models.RawEmail.received_at.asc())
            .first()
        )
        
        if root:
            return root.encrypted_subject
        
        fallback = (
            session.query(models.RawEmail)
            .filter_by(user_id=user_id, thread_id=thread_id)
            .order_by(models.RawEmail.received_at.asc())
            .first()
        )
        
        return fallback.encrypted_subject if fallback else None

    @staticmethod
    def get_all_user_emails(
        session: Session,
        user_id: int,
    ) -> List[models.RawEmail]:
        """Get all user emails for client-side search
        
        Required because data is encrypted and cannot be searched at the database level.
        Filtering is done in Python after decryption.
        
        Args:
            session: SQLAlchemy session
            user_id: User ID
            
        Returns:
            List of all user RawEmails
        """
        return (
            session.query(models.RawEmail)
            .filter_by(user_id=user_id)
            .order_by(models.RawEmail.thread_id, models.RawEmail.received_at.desc())
            .all()
        )

    @staticmethod
    def search_conversations(
        session: Session,
        user_id: int,
        query: str,
        decryption_key: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search conversations with client-side decryption
        
        IMPORTANT: Data is encrypted and cannot be searched at the database level with ILIKE.
        This method loads ALL emails and filters after decryption.
        
        Args:
            session: SQLAlchemy session
            user_id: User ID
            query: Search string
            decryption_key: Master key for decryption
            limit: Maximum results
            
        Returns:
            Similar to get_threads_summary()
        """
        from src.thread_api import decrypt_email
        
        all_emails = ThreadService.get_all_user_emails(session, user_id)
        
        matching_thread_ids = set()
        for email in all_emails:
            subject = decrypt_email(email.encrypted_subject, decryption_key)
            sender = decrypt_email(email.encrypted_sender, decryption_key)
            
            combined = f"{subject} {sender}".lower()
            if query.lower() in combined:
                if email.thread_id:
                    matching_thread_ids.add(email.thread_id)
        
        if not matching_thread_ids:
            return []
        
        thread_ids_list = list(matching_thread_ids)[:limit]
        
        return ThreadService.get_threads_summary(
            session, user_id, limit=len(thread_ids_list), offset=0,
            thread_ids=thread_ids_list
        )

    @staticmethod
    def get_thread_stats(
        session: Session, user_id: int, thread_id: str
    ) -> Dict[str, Any]:
        """Get detailed thread statistics
        
        Args:
            session: SQLAlchemy session
            user_id: User ID
            thread_id: Thread UUID
            
        Returns:
            {
                count, 
                unread_count,
                with_attachments_count,
                span_days,
                latest_date,
                oldest_date
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
