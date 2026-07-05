"""Add user_organizations table — S2-02

Revision ID: 004_add_user_organizations
Revises: 003_rename_agencies_to_branches
Create Date: 2026-06-26 00:00:00.000000

Implémente la DÉCISION 7 : table pivot Many-to-Many User ↔ Organization.

Un utilisateur peut appartenir à plusieurs organisations (BANCOBU, CHUK…)
depuis une seule application TONDE, via un code d'invitation (S2-08).

Champs :
  - id              : UUID PK
  - user_id         : FK → users.id CASCADE DELETE
  - organization_id : FK → organizations.id CASCADE DELETE
  - member_number   : numéro de membre optionnel (compte bancaire, dossier patient…)
  - status          : active | inactive
  - created_at      : date d'adhésion

Contrainte d'unicité : (user_id, organization_id) — un user ne peut pas
rejoindre la même organisation deux fois.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = '004_add_user_organizations'
down_revision: Union[str, None] = '003_rename_agencies_to_branches'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_organizations',

        # ── Identifiant ──────────────────────────────────────────
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),

        # ── Clés étrangères ───────────────────────────────────────
        sa.Column(
            'user_id', sa.String(36),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'organization_id', sa.String(36),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),

        # ── Numéro de membre (optionnel) ──────────────────────────
        sa.Column('member_number', sa.String(100), nullable=True),

        # ── Statut ────────────────────────────────────────────────
        sa.Column(
            'status', sa.String(20),
            nullable=False,
            server_default='active',
        ),

        # ── Date d'adhésion ───────────────────────────────────────
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('NOW()'),
        ),
    )

    # Index sur user_id — requêtes "mes organisations"
    op.create_index(
        'ix_user_organizations_user_id',
        'user_organizations',
        ['user_id'],
    )

    # Index sur organization_id — requêtes "membres d'une org"
    op.create_index(
        'ix_user_organizations_organization_id',
        'user_organizations',
        ['organization_id'],
    )

    # Contrainte d'unicité (user_id, organization_id)
    op.create_unique_constraint(
        'uq_user_organization',
        'user_organizations',
        ['user_id', 'organization_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_user_organization', 'user_organizations', type_='unique')
    op.drop_index('ix_user_organizations_organization_id', table_name='user_organizations')
    op.drop_index('ix_user_organizations_user_id', table_name='user_organizations')
    op.drop_table('user_organizations')
