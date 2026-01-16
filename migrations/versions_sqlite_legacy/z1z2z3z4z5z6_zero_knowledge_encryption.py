"""zero_knowledge_encryption

Revision ID: z1z2z3z4z5z6
Revises: f1a2b3c4d5e6
Create Date: 2025-12-26 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'z1z2z3z4z5z6'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    """
    Migration für Zero-Knowledge-Verschlüsselung:
    
    1. MailAccount: imap_server/imap_username → encrypted + hash
    2. RawEmail: sender/subject/body → encrypted
    """
    
    # MailAccount: Neue verschlüsselte Felder hinzufügen
    op.add_column('mail_accounts', sa.Column('encrypted_imap_server', sa.Text(), nullable=True))
    op.add_column('mail_accounts', sa.Column('imap_server_hash', sa.String(length=64), nullable=True))
    op.add_column('mail_accounts', sa.Column('encrypted_imap_username', sa.Text(), nullable=True))
    op.add_column('mail_accounts', sa.Column('imap_username_hash', sa.String(length=64), nullable=True))
    op.add_column('mail_accounts', sa.Column('encrypted_smtp_server', sa.Text(), nullable=True))
    op.add_column('mail_accounts', sa.Column('encrypted_smtp_username', sa.Text(), nullable=True))
    op.add_column('mail_accounts', sa.Column('encrypted_pop3_server', sa.Text(), nullable=True))
    op.add_column('mail_accounts', sa.Column('encrypted_pop3_username', sa.Text(), nullable=True))
    
    # Index für Hash-Felder
    op.create_index('ix_mail_accounts_imap_server_hash', 'mail_accounts', ['imap_server_hash'])
    op.create_index('ix_mail_accounts_imap_username_hash', 'mail_accounts', ['imap_username_hash'])
    
    # RawEmail: Neue verschlüsselte Felder hinzufügen
    op.add_column('raw_emails', sa.Column('encrypted_sender', sa.Text(), nullable=True))
    op.add_column('raw_emails', sa.Column('encrypted_subject', sa.Text(), nullable=True))
    op.add_column('raw_emails', sa.Column('encrypted_body', sa.Text(), nullable=True))
    
    # WARNUNG: Bestehende Daten können nicht automatisch verschlüsselt werden
    # da der Master-Key des Users benötigt wird (Zero-Knowledge)
    # 
    # Optionen:
    # 1. Alle Mail-Accounts & RawEmails löschen (Neustart)
    # 2. Manuelle Migration via Script mit User-Login
    # 3. User muss sich neu einloggen und Accounts neu anlegen
    
    # Alte unverschlüsselte Felder entfernen (nach Migration der Daten)
    # ACHTUNG: Nur aktivieren wenn Daten migriert sind!
    # op.drop_column('mail_accounts', 'imap_server')
    # op.drop_column('mail_accounts', 'imap_username')
    # op.drop_column('mail_accounts', 'smtp_server')
    # op.drop_column('mail_accounts', 'smtp_username')
    # op.drop_column('mail_accounts', 'pop3_server')
    # op.drop_column('mail_accounts', 'pop3_username')
    # op.drop_column('raw_emails', 'sender')
    # op.drop_column('raw_emails', 'subject')
    # op.drop_column('raw_emails', 'body')


def downgrade():
    """
    Rollback: Verschlüsselte Felder entfernen
    
    ACHTUNG: Datenverlust! Verschlüsselte Daten können nicht
    zurück in Klartext konvertiert werden ohne Master-Key.
    """
    
    # RawEmail: Verschlüsselte Felder entfernen
    op.drop_column('raw_emails', 'encrypted_body')
    op.drop_column('raw_emails', 'encrypted_subject')
    op.drop_column('raw_emails', 'encrypted_sender')
    
    # MailAccount: Verschlüsselte Felder und Indizes entfernen
    op.drop_index('ix_mail_accounts_imap_username_hash', table_name='mail_accounts')
    op.drop_index('ix_mail_accounts_imap_server_hash', table_name='mail_accounts')
    
    op.drop_column('mail_accounts', 'encrypted_pop3_username')
    op.drop_column('mail_accounts', 'encrypted_pop3_server')
    op.drop_column('mail_accounts', 'encrypted_smtp_username')
    op.drop_column('mail_accounts', 'encrypted_smtp_server')
    op.drop_column('mail_accounts', 'imap_username_hash')
    op.drop_column('mail_accounts', 'encrypted_imap_username')
    op.drop_column('mail_accounts', 'imap_server_hash')
    op.drop_column('mail_accounts', 'encrypted_imap_server')
