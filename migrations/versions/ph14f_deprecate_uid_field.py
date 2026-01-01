"""Phase 14f: Deprecate uid field (RFC-konform Key verwendet)

Revision ID: ph14f_deprecate_uid_field
Revises: ph14a_rfc_unique_key_uidvalidity
Create Date: 2026-01-01

===== PHASE 14F: CLEANUP (uid Feld deprecated) =====

Das alte uid Feld (selbst-generierter String/UUID) wird nicht mehr verwendet.
Der RFC-konforme Key (folder, uidvalidity, imap_uid) ersetzt es vollständig.

ÄNDERUNGEN:
1. RawEmail.uid: NOT NULL → nullable=True (Backward-Compatibility)
2. Neue Emails bekommen uid=NULL
3. Alte Emails behalten uid (kann später gelöscht werden)

Migration setzt bestehende NULL-Werte auf Dummy-String um NOT NULL Constraint zu erfüllen.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = 'ph14f_deprecate_uid_field'
down_revision = 'ph14a_rfc_unique_key_uidvalidity'
branch_labels = None
depends_on = None


def upgrade():
    """uid Feld auf nullable setzen"""
    
    print("\n" + "=" * 70)
    print("PHASE 14F: DEPRECATE UID FIELD")
    print("=" * 70)
    print()
    print("Das alte uid Feld ist deprecated und wird auf nullable gesetzt.")
    print("Neue Emails bekommen uid=NULL.")
    print("Der RFC-konforme Key (folder, uidvalidity, imap_uid) wird verwendet.")
    print()
    
    conn = op.get_bind()
    
    # SQLite: ALTER COLUMN ist kompliziert, aber uid ist schon nullable in der
    # Table Recreation von ph14a_rfc_unique_key_uidvalidity.py
    
    # Check if any uid fields are NULL and set dummy value
    result = conn.execute(text("SELECT COUNT(*) FROM raw_emails WHERE uid IS NULL"))
    null_count = result.scalar()
    
    if null_count > 0:
        print(f"ℹ️  {null_count} Emails mit uid=NULL gefunden")
        # Set dummy value for backward compatibility with old code
        conn.execute(text("""
            UPDATE raw_emails 
            SET uid = 'deprecated_' || id
            WHERE uid IS NULL
        """))
        print(f"✅ uid-Werte gesetzt (deprecated_<id>)")
    
    print()
    print("=" * 70)
    print("PHASE 14F MIGRATION ERFOLGREICH")
    print("=" * 70)
    print()


def downgrade():
    """Downgrade nicht möglich ohne Daten zu verlieren"""
    print("⚠️  Downgrade von Phase 14f nicht implementiert")
    print("   (uid Werte können nicht rekonstruiert werden)")
