"""Phase 13C Part 6: Move Fetch Filters to Mail Accounts

Revision ID: ph13c_p6_move_filters
Revises: ph13c_p5_fetch_filters
Create Date: 2026-01-04 09:30:00.000000

Verschiebt Fetch-Filter von User → MailAccount (account-spezifische Filter)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ph13c_p6_move_filters'
down_revision: Union[str, None] = 'ph13c_p5_fetch_filters'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Neue Spalten in mail_accounts Tabelle hinzufügen
    with op.batch_alter_table('mail_accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fetch_since_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('fetch_unseen_only', sa.Boolean(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('fetch_include_folders', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('fetch_exclude_folders', sa.Text(), nullable=True))
    
    # 2. Daten von users → mail_accounts migrieren (falls User Filter gesetzt hat)
    # Hinweis: Wenn ein User Filter hatte, werden sie auf ALLE seine Accounts kopiert
    # Das ist ein pragmatischer Ansatz - User kann danach individuell anpassen
    conn = op.get_bind()
    
    # Hole alle Users mit Filter-Settings
    users_with_filters = conn.execute(sa.text("""
        SELECT id, fetch_since_date, fetch_unseen_only, fetch_include_folders, fetch_exclude_folders
        FROM users
        WHERE fetch_since_date IS NOT NULL 
           OR fetch_unseen_only = 1
           OR fetch_include_folders IS NOT NULL
           OR fetch_exclude_folders IS NOT NULL
    """)).fetchall()
    
    # Kopiere Filter auf alle Accounts des jeweiligen Users
    for user_row in users_with_filters:
        user_id = user_row[0]
        since_date = user_row[1]
        unseen_only = user_row[2]
        include_folders = user_row[3]
        exclude_folders = user_row[4]
        
        conn.execute(sa.text("""
            UPDATE mail_accounts
            SET fetch_since_date = :since_date,
                fetch_unseen_only = :unseen_only,
                fetch_include_folders = :include_folders,
                fetch_exclude_folders = :exclude_folders
            WHERE user_id = :user_id
        """), {
            'user_id': user_id,
            'since_date': since_date,
            'unseen_only': 1 if unseen_only else 0,
            'include_folders': include_folders,
            'exclude_folders': exclude_folders
        })
    
    # 3. Alte Spalten aus users Tabelle entfernen
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('fetch_exclude_folders')
        batch_op.drop_column('fetch_include_folders')
        batch_op.drop_column('fetch_unseen_only')
        batch_op.drop_column('fetch_since_date')


def downgrade() -> None:
    # 1. Spalten in users wieder hinzufügen
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fetch_since_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('fetch_unseen_only', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('fetch_include_folders', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('fetch_exclude_folders', sa.Text(), nullable=True))
    
    # 2. Daten von mail_accounts → users zurückmigrieren
    # Nimm die Filter vom ERSTEN Account des Users (pragmatisch)
    conn = op.get_bind()
    
    accounts_with_filters = conn.execute(sa.text("""
        SELECT user_id, fetch_since_date, fetch_unseen_only, fetch_include_folders, fetch_exclude_folders
        FROM mail_accounts
        WHERE fetch_since_date IS NOT NULL 
           OR fetch_unseen_only = 1
           OR fetch_include_folders IS NOT NULL
           OR fetch_exclude_folders IS NOT NULL
        GROUP BY user_id
    """)).fetchall()
    
    for account_row in accounts_with_filters:
        user_id = account_row[0]
        since_date = account_row[1]
        unseen_only = account_row[2]
        include_folders = account_row[3]
        exclude_folders = account_row[4]
        
        conn.execute(sa.text("""
            UPDATE users
            SET fetch_since_date = :since_date,
                fetch_unseen_only = :unseen_only,
                fetch_include_folders = :include_folders,
                fetch_exclude_folders = :exclude_folders
            WHERE id = :user_id
        """), {
            'user_id': user_id,
            'since_date': since_date,
            'unseen_only': 1 if unseen_only else 0,
            'include_folders': include_folders,
            'exclude_folders': exclude_folders
        })
    
    # 3. Spalten aus mail_accounts entfernen
    with op.batch_alter_table('mail_accounts', schema=None) as batch_op:
        batch_op.drop_column('fetch_exclude_folders')
        batch_op.drop_column('fetch_include_folders')
        batch_op.drop_column('fetch_unseen_only')
        batch_op.drop_column('fetch_since_date')
