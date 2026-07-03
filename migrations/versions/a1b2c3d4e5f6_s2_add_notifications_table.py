"""s2_add_notifications_table

Revision ID: a1b2c3d4e5f6
Revises: 35b6d638fb50
Create Date: 2026-06-26 00:00:00.000000

Sprint 2 — Module Notifications (S2-05)
Crée la table 'notifications' pour l'audit trail des SMS, FCM et in-app.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '35b6d638fb50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('ticket_id', sa.String(36), sa.ForeignKey('tickets.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('channel', sa.Enum('sms', 'fcm', 'in_app', name='notificationchannel'), nullable=False),
        sa.Column('title', sa.String(200), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('pending', 'sent', 'failed', name='notificationstatus'), nullable=False, default='pending', index=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, default=False),
        sa.Column('error_message', sa.String(500), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('notifications')
    op.execute("DROP TYPE IF EXISTS notificationchannel")
    op.execute("DROP TYPE IF EXISTS notificationstatus")
