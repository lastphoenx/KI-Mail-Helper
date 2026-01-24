"""add_processing_timestamps

Revision ID: 003181942ae3
Revises: de3d584b6293
Create Date: 2026-01-24 13:03:57.740439

Phase 27.1: Granular Processing Timestamps
Ersetzt das lineare processing_status-System durch individuelle Timestamps
für jeden Verarbeitungsschritt. Ermöglicht präzises Nachverarbeiten einzelner
Steps ohne Datenverlust oder redundante Wiederholungen.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003181942ae3'
down_revision: Union[str, Sequence[str], None] = 'de3d584b6293'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add granular processing timestamps for each pipeline step."""
    
    # Translation Step (Phase 26)
    # embedding_generated_at existiert bereits (Phase 17)
    op.add_column('raw_emails', sa.Column('translation_completed_at', sa.DateTime(), nullable=True))
    
    # AI Classification Step (Phase 8/9)
    op.add_column('raw_emails', sa.Column('ai_classification_completed_at', sa.DateTime(), nullable=True))
    
    # Auto-Rules Step (Phase G.2)
    op.add_column('raw_emails', sa.Column('auto_rules_completed_at', sa.DateTime(), nullable=True))
    
    # Migration: Konvertiere bestehende processing_status in Timestamps
    # Nutze processing_last_attempt_at als Basis-Timestamp
    op.execute("""
        UPDATE raw_emails SET
            -- Embedding: Status >= 10
            -- (embedding_generated_at existiert bereits, nicht überschreiben)
            
            -- Translation: Status >= 20
            translation_completed_at = CASE 
                WHEN processing_status >= 20 THEN processing_last_attempt_at 
                ELSE NULL 
            END,
            
            -- AI Classification: Status >= 40
            ai_classification_completed_at = CASE 
                WHEN processing_status >= 40 THEN processing_last_attempt_at 
                ELSE NULL 
            END,
            
            -- Auto-Rules: Status >= 50
            auto_rules_completed_at = CASE 
                WHEN processing_status >= 50 THEN processing_last_attempt_at 
                ELSE NULL 
            END
        WHERE processing_last_attempt_at IS NOT NULL;
    """)
    
    # Hinweis: processing_status bleibt erhalten für Monitoring (100 = alles fertig)
    # Die Pipeline nutzt ab jetzt die Timestamps für Steuerung


def downgrade() -> None:
    """Remove granular timestamps, fallback to processing_status."""
    op.drop_column('raw_emails', 'auto_rules_completed_at')
    op.drop_column('raw_emails', 'ai_classification_completed_at')
    op.drop_column('raw_emails', 'translation_completed_at')
