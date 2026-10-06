"""Audit: Klartext-Spalten aus audit_known_contacts entfernen.

Nur ausführen nach:
  - alembic f7a8b9c0d1e2
  - scripts/backfill_audit_known_contacts_encrypt.py (alle Zeilen verschlüsselt)
  - Verifikation (keine Zeile mit encrypted_email IS NULL)

Rollback stellt Klartext-Spalten wieder her (ohne Daten-Rehydration).
"""

from alembic import op
import sqlalchemy as sa


revision = "f8a9b0c1d2e3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        pending = bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM audit_known_contacts "
                "WHERE encrypted_email IS NULL OR email_lookup_hmac IS NULL"
            )
        ).scalar()
        if pending and int(pending) > 0:
            raise RuntimeError(
                f"audit_known_contacts: {pending} Zeile(n) ohne Verschlüsselung — "
                "Backfill zuerst ausführen."
            )

    op.drop_constraint(
        "uq_audit_known_contact_email",
        "audit_known_contacts",
        type_="unique",
    )
    op.drop_column("audit_known_contacts", "display_name")
    op.drop_column("audit_known_contacts", "email_normalized")

    with op.batch_alter_table("audit_known_contacts") as batch_op:
        batch_op.alter_column(
            "email_lookup_hmac",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch_op.alter_column(
            "encrypted_email",
            existing_type=sa.Text(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_known_contacts") as batch_op:
        batch_op.alter_column(
            "encrypted_email",
            existing_type=sa.Text(),
            nullable=True,
        )
        batch_op.alter_column(
            "email_lookup_hmac",
            existing_type=sa.String(length=64),
            nullable=True,
        )

    op.add_column(
        "audit_known_contacts",
        sa.Column("email_normalized", sa.String(length=320), nullable=True),
    )
    op.add_column(
        "audit_known_contacts",
        sa.Column("display_name", sa.String(length=512), nullable=True),
    )
    op.create_unique_constraint(
        "uq_audit_known_contact_email",
        "audit_known_contacts",
        ["user_id", "account_id", "email_normalized"],
    )
