"""Add notifications and queue_logs tables — S2-04/S2-05

Revision ID: 006_add_notifications_and_queue_logs
Revises: 161835c00fba
Create Date: 2026-06-26 00:00:00.000000

Ajoute deux tables d'audit trail et notifications :

  1. queue_logs  — Audit trail immuable de chaque transition ticket
     Source de données pour le pipeline Analytics (DÉCISION 9).
     Champs : org_id, ticket_id, agency_id, service_id, action,
              from_status, to_status, actor_id, actor_role,
              counter_id, counter_name, elapsed_seconds, extra_data

  2. notifications — Historique de chaque notification envoyée
     SMS (Africa's Talking), FCM (Firebase), In-App.
     Champs : org_id, user_id, ticket_id, channel, title, body,
              status, is_read, error_message, sent_at
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = '006_add_notifications_and_queue_logs'
down_revision: Union[str, None] = '161835c00fba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enums ─────────────────────────────────────────────────────────────────
    queuelogaction_enum = sa.Enum(
        'ticket_created', 'ticket_called', 'ticket_serving', 'ticket_done',
        'ticket_absent', 'ticket_returned', 'ticket_transferred',
        'ticket_cancelled', 'ticket_incomplete',
        name='queuelogaction',
    )
    notificationchannel_enum = sa.Enum(
        'sms', 'fcm', 'in_app',
        name='notificationchannel',
    )
    notificationstatus_enum = sa.Enum(
        'pending', 'sent', 'failed',
        name='notificationstatus',
    )

    # ── Table queue_logs ──────────────────────────────────────────────────────
    op.create_table(
        'queue_logs',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            'org_id', sa.String(36),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
        ),
        sa.Column(
            'ticket_id', sa.String(36),
            sa.ForeignKey('tickets.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
        ),
        sa.Column(
            'agency_id', sa.String(36),
            sa.ForeignKey('branches.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
        ),
        sa.Column(
            'service_id', sa.String(36),
            sa.ForeignKey('services.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
        ),
        sa.Column('action', queuelogaction_enum, nullable=False, index=True),
        sa.Column('from_status', sa.String(20), nullable=True),
        sa.Column('to_status', sa.String(20), nullable=False),
        sa.Column('actor_id', sa.String(36), nullable=True),
        sa.Column('actor_role', sa.String(30), nullable=True),
        sa.Column('counter_id', sa.String(36), nullable=True),
        sa.Column('counter_name', sa.String(50), nullable=True),
        sa.Column('elapsed_seconds', sa.Integer(), nullable=True),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('NOW()'),
            index=True,
        ),
    )

    # ── Table notifications ───────────────────────────────────────────────────
    op.create_table(
        'notifications',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            'org_id', sa.String(36),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
        ),
        sa.Column(
            'user_id', sa.String(36),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
        ),
        sa.Column(
            'ticket_id', sa.String(36),
            sa.ForeignKey('tickets.id', ondelete='SET NULL'),
            nullable=True,
            index=True,
        ),
        sa.Column('channel', notificationchannel_enum, nullable=False),
        sa.Column('title', sa.String(200), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column(
            'status',
            notificationstatus_enum,
            nullable=False,
            server_default='pending',
            index=True,
        ),
        sa.Column(
            'is_read',
            sa.Boolean(),
            nullable=False,
            server_default='false',
        ),
        sa.Column('error_message', sa.String(500), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('NOW()'),
        ),
    )


def downgrade() -> None:
    op.drop_table('notifications')
    op.drop_table('queue_logs')
    op.execute('DROP TYPE IF EXISTS notificationstatus')
    op.execute('DROP TYPE IF EXISTS notificationchannel')
    op.execute('DROP TYPE IF EXISTS queuelogaction')
