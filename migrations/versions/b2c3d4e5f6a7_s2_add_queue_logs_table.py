"""s2_add_queue_logs_table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-03 00:00:00.000000

Sprint 2 — Queue Logs / Audit Trail (S2-04)
Crée la table 'queue_logs' — enregistrement immuable de chaque
transition d'état d'un ticket pour l'audit trail et les analytics.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'queue_logs',
        sa.Column('id',           sa.String(36),  primary_key=True),
        sa.Column('org_id',       sa.String(36),  sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('ticket_id',    sa.String(36),  sa.ForeignKey('tickets.id',       ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('agency_id',    sa.String(36),  sa.ForeignKey('agencies.id',      ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('service_id',   sa.String(36),  sa.ForeignKey('services.id',      ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('action', sa.Enum(
            'ticket_created', 'ticket_called', 'ticket_serving', 'ticket_done',
            'ticket_absent', 'ticket_returned', 'ticket_transferred',
            'ticket_cancelled', 'ticket_incomplete',
            name='queuelogaction',
        ), nullable=False, index=True),
        sa.Column('from_status',  sa.String(20),  nullable=True),
        sa.Column('to_status',    sa.String(20),  nullable=False),
        sa.Column('actor_id',     sa.String(36),  nullable=True),
        sa.Column('actor_role',   sa.String(30),  nullable=True),
        sa.Column('counter_id',   sa.String(36),  nullable=True),
        sa.Column('counter_name', sa.String(50),  nullable=True),
        sa.Column('elapsed_seconds', sa.Integer(), nullable=True),
        sa.Column('extra_data',   sa.Text(),      nullable=True),
        sa.Column('created_at',   sa.DateTime(timezone=True), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table('queue_logs')
    op.execute("DROP TYPE IF EXISTS queuelogaction")
