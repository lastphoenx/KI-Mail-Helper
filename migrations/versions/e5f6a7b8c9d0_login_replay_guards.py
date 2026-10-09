"""TOTP-Schritt und Session-Epoche gegen Replay und alte Logins.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-09

"""
from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("last_totp_step", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "session_epoch",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade():
    op.drop_column("users", "session_epoch")
    op.drop_column("users", "last_totp_step")
