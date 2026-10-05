"""Audit: bekannte Kontakte + BFS-Vornamen."""

from alembic import op
import sqlalchemy as sa


revision = "e6f7a8b9c0d1"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_firstnames",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name_key", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name_key"),
    )
    op.create_index("ix_audit_firstnames_name_key", "audit_firstnames", ["name_key"])

    op.create_table(
        "audit_known_contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("mail_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["mail_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "account_id", "email_normalized",
            name="uq_audit_known_contact_email",
        ),
    )
    op.create_index(
        "idx_audit_known_contact_account",
        "audit_known_contacts",
        ["user_id", "account_id"],
    )

    op.add_column(
        "mail_accounts",
        sa.Column(
            "audit_contacts_import_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "mail_accounts",
        sa.Column("audit_contacts_import_state", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mail_accounts", "audit_contacts_import_state")
    op.drop_column("mail_accounts", "audit_contacts_import_enabled")
    op.drop_index("idx_audit_known_contact_account", table_name="audit_known_contacts")
    op.drop_table("audit_known_contacts")
    op.drop_index("ix_audit_firstnames_name_key", table_name="audit_firstnames")
    op.drop_table("audit_firstnames")
