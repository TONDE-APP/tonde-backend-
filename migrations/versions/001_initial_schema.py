"""Initial schema - Create all TONDE tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-06-22 14:00:00.000000

NOTE: Cette migration crée le schéma complet de TONDE.
Ordre de création : organizations → users → agencies → services → counters → employees → tickets
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

# revision identifiers
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Définir les ENUM types
userrole_enum = PGEnum(
    'CLIENT', 'AGENT', 'SUPERVISOR', 'ADMIN_AGENCY', 'ADMIN_ORG', 'SUPER_ADMIN',
    name='userrole', create_type=False
)
employeestatus_enum = PGEnum(
    'active', 'on_leave', 'suspended', 'inactive',
    name='employeestatus', create_type=False
)
ticketstatus_enum = PGEnum(
    'waiting', 'called', 'serving', 'done', 'absent', 'transferred', 'cancelled', 'incomplete',
    name='ticketstatus', create_type=False
)
ticketpriority_enum = PGEnum(
    'standard', 'priority', 'vip', 'emergency',
    name='ticketpriority', create_type=False
)


def upgrade() -> None:
    # Créer les ENUM types d'abord
    userrole_enum.create(op.get_bind(), checkfirst=True)
    employeestatus_enum.create(op.get_bind(), checkfirst=True)
    ticketstatus_enum.create(op.get_bind(), checkfirst=True)
    ticketpriority_enum.create(op.get_bind(), checkfirst=True)

    # ── Organizations ─────────────────────────────────────────────
    op.create_table(
        'organizations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('slug', sa.String(200), unique=True, nullable=False, index=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('sector', sa.String(50), nullable=False),
        sa.Column('country', sa.String(50), nullable=False, server_default='Burundi'),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('website', sa.String(500), nullable=True),
        sa.Column('logo_url', sa.String(500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # ── Users ─────────────────────────────────────────────────────
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('name', sa.String(100), nullable=True),
        sa.Column('email', sa.String(255), unique=True, nullable=True),
        sa.Column('phone', sa.String(20), unique=True, nullable=True),
        sa.Column('photo_url', sa.String(500), nullable=True),
        sa.Column('hashed_password', sa.String(255), nullable=True),
        sa.Column('role', userrole_enum, nullable=False, server_default='CLIENT'),
        sa.Column('language', sa.String(5), nullable=False, server_default='fr'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('fcm_token', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
    )

    # ── Agencies (Branches) ──────────────────────────────────────
    op.create_table(
        'agencies',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('slug', sa.String(200), unique=True, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('sector', sa.String(50), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('address', sa.String(500), nullable=True),
        sa.Column('city', sa.String(100), nullable=False, server_default='Bujumbura'),
        sa.Column('country', sa.String(50), nullable=False, server_default='Burundi'),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('opens_at', sa.String(5), nullable=False, server_default='08:00'),
        sa.Column('closes_at', sa.String(5), nullable=False, server_default='17:00'),
        sa.Column('logo_url', sa.String(500), nullable=True),
        sa.Column('max_daily_tickets', sa.Integer(), nullable=False, server_default='500'),
        sa.Column('avg_service_minutes', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_open', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # ── Services ──────────────────────────────────────────────────
    op.create_table(
        'services',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('agency_id', sa.String(36), sa.ForeignKey('agencies.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('ticket_prefix', sa.String(5), nullable=False, server_default='A'),
        sa.Column('avg_duration_minutes', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # ── Counters ─────────────────────────────────────────────────
    op.create_table(
        'counters',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('agency_id', sa.String(36), sa.ForeignKey('agencies.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('current_ticket_id', sa.String(36), nullable=True),
        sa.Column('is_open', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # ── Employees ────────────────────────────────────────────────
    op.create_table(
        'employees',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('agency_id', sa.String(36), sa.ForeignKey('agencies.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('counter_id', sa.String(36), sa.ForeignKey('counters.id', ondelete='SET NULL'), nullable=True),
        sa.Column('role', userrole_enum, nullable=False),
        sa.Column('status', employeestatus_enum, nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # ── Tickets ──────────────────────────────────────────────────
    op.create_table(
        'tickets',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('number', sa.String(20), nullable=False),
        sa.Column('prefix', sa.String(5), nullable=False, server_default='A'),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('agency_id', sa.String(36), sa.ForeignKey('agencies.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('service_id', sa.String(36), sa.ForeignKey('services.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('status', ticketstatus_enum, nullable=False, server_default='waiting'),
        sa.Column('priority', ticketpriority_enum, nullable=False, server_default='standard'),
        sa.Column('counter_id', sa.String(36), nullable=True),
        sa.Column('counter_name', sa.String(50), nullable=True),
        sa.Column('qr_token', sa.String(100), unique=True, nullable=False),
        sa.Column('estimated_wait_minutes', sa.Integer(), nullable=True),
        sa.Column('actual_wait_minutes', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('called_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('served_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notified_5min', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('notified_turn', sa.Boolean(), nullable=False, server_default='false'),
    )

    # ── Refresh Tokens (pour la persistance des sessions) ────────
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('token_hash', sa.String(255), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('is_revoked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('device_info', sa.String(500), nullable=True),
        sa.Column('ip_address', sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('refresh_tokens')
    op.drop_table('tickets')
    op.drop_table('employees')
    op.drop_table('counters')
    op.drop_table('services')
    op.drop_table('agencies')
    op.drop_table('users')
    op.drop_table('organizations')
    # Supprimer les ENUM types
    ticketpriority_enum.drop(op.get_bind(), checkfirst=True)
    ticketstatus_enum.drop(op.get_bind(), checkfirst=True)
    employeestatus_enum.drop(op.get_bind(), checkfirst=True)
    userrole_enum.drop(op.get_bind(), checkfirst=True)
