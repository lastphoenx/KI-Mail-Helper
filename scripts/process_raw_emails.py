#!/usr/bin/env python3
"""Verarbeitet existierende RawEmails zu ProcessedEmails"""

import sys
import logging
import importlib

models = importlib.import_module('.02_models', 'src')
ai_client = importlib.import_module('.03_ai_client', 'src')
sanitizer = importlib.import_module('.04_sanitizer', 'src')
scoring = importlib.import_module('.05_scoring', 'src')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = create_engine('sqlite:///emails.db')
Session = sessionmaker(bind=engine)
session = Session()

try:
    # Finde alle RawEmails ohne ProcessedEmail
    pending = session.query(models.RawEmail).outerjoin(
        models.ProcessedEmail,
        models.RawEmail.id == models.ProcessedEmail.raw_email_id
    ).filter(
        models.ProcessedEmail.id.is_(None)
    ).all()
    
    logger.info(f"🧾 Found {len(pending)} RawEmails to process")
    
    if not pending:
        logger.info("✅ Keine RawEmails zum Verarbeiten")
        sys.exit(0)
    
    ai = ai_client.get_ai_client("ollama")
    processed = 0
    
    for raw in pending:
        try:
            subject_preview = (raw.subject or "")[:50]
            logger.info(f"🤖 Processing: {subject_preview}")
            
            clean_body = sanitizer.sanitize_email(raw.body, level=1)
            
            ai_result = ai.analyze_email(
                subject=raw.subject or "",
                body=clean_body
            )
            
            priority = scoring.analyze_priority(
                dringlichkeit=ai_result["dringlichkeit"],
                wichtigkeit=ai_result["wichtigkeit"]
            )
            
            processed_email = models.ProcessedEmail(
                user_id=raw.user_id,
                raw_email_id=raw.id,
                dringlichkeit=ai_result["dringlichkeit"],
                wichtigkeit=ai_result["wichtigkeit"],
                kategorie_aktion=ai_result["kategorie_aktion"],
                tags=",".join(ai_result.get("tags", [])),
                spam_flag=ai_result["spam_flag"],
                summary_de=ai_result["summary_de"],
                text_de=ai_result["text_de"],
                score=priority["score"],
                matrix_x=priority["matrix_x"],
                matrix_y=priority["matrix_y"],
                farbe=priority["farbe"],
                done=False
            )
            
            session.add(processed_email)
            session.commit()
            processed += 1
            
            logger.info(f"✅ Saved: Score={priority['score']}, Farbe={priority['farbe']}")
            
        except Exception as e:
            logger.error(f"❌ Error: {e}", exc_info=True)
            session.rollback()
            continue
    
    logger.info(f"✨ Done! {processed}/{len(pending)} processed")

finally:
    session.close()
