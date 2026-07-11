"""merge heads

Revision ID: c0d78e94182b
Revises: 002_add_refresh_tokens, 005_add_branch_config_fields
Create Date: 2026-07-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'c0d78e94182b'
down_revision = ('002_add_refresh_tokens', '005_add_branch_config_fields')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
