"""Audit: audit_known_contacts Verschlüsselungs-Spalten."""

from alembic import op
import sqlalchemy as sa


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_known_contacts",
        sa.Column("email_lookup_hmac", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "audit_known_contacts",
        sa.Column("encrypted_email", sa.Text(), nullable=True),
    )
    op.add_column(
        "audit_known_contacts",
        sa.Column("encrypted_display_name", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_audit_known_contacts_email_lookup_hmac",
        "audit_known_contacts",
        ["email_lookup_hmac"],
    )
    op.create_unique_constraint(
        "uq_audit_known_contact_hmac",
        "audit_known_contacts",
        ["user_id", "account_id", "email_lookup_hmac"],
    )
    with op.batch_alter_table("audit_known_contacts") as batch_op:
        batch_op.alter_column(
            "email_normalized",
            existing_type=sa.String(length=320),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_known_contacts") as batch_op:
        batch_op.alter_column(
            "email_normalized",
            existing_type=sa.String(length=320),
            nullable=False,
        )
    op.drop_constraint("uq_audit_known_contact_hmac", "audit_known_contacts", type_="unique")
    op.drop_index(
        "ix_audit_known_contacts_email_lookup_hmac",
        table_name="audit_known_contacts",
    )
    op.drop_column("audit_known_contacts", "encrypted_display_name")
    op.drop_column("audit_known_contacts", "encrypted_email")
    op.drop_column("audit_known_contacts", "email_lookup_hmac")
