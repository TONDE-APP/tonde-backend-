"""Rename agencies table to branches — S2-01

Revision ID: 003_rename_agencies_to_branches
Revises: 70c723d5ac75
Create Date: 2026-06-26 00:00:00.000000

Applique la DÉCISION 8 : Agency → Branch.

Opérations :
  1. Renommer la table agencies → branches
  2. Renommer la table services : colonne agency_id → branch_id
  3. Mettre à jour les FK dans counters et employees
  4. Renommer les index et contraintes FK impactés

Les données existantes sont conservées intégralement.
Les URLs /agencies sont maintenues via alias dans le router (rétro-compat mobile).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = '003_rename_agencies_to_branches'
down_revision: Union[str, None] = '70c723d5ac75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Renommer la table agencies → branches ──────────────────────────────
    op.rename_table('agencies', 'branches')

    # ── 2. Table services : renommer agency_id → branch_id ───────────────────
    # Supprimer l'ancienne FK vers agencies
    op.drop_constraint('services_agency_id_fkey', 'services', type_='foreignkey')

    # Renommer la colonne
    op.alter_column('services', 'agency_id', new_column_name='branch_id')

    # Recréer la FK vers la table renommée branches
    op.create_foreign_key(
        'services_branch_id_fkey',
        'services', 'branches',
        ['branch_id'], ['id'],
        ondelete='CASCADE',
    )

    # ── 3. Table counters : mettre à jour FK agency_id → branches ─────────────
    op.drop_constraint('counters_agency_id_fkey', 'counters', type_='foreignkey')
    op.create_foreign_key(
        'counters_agency_id_fkey',
        'counters', 'branches',
        ['agency_id'], ['id'],
        ondelete='CASCADE',
    )

    # ── 4. Table employees : mettre à jour FK agency_id → branches ────────────
    op.drop_constraint('employees_agency_id_fkey', 'employees', type_='foreignkey')
    op.create_foreign_key(
        'employees_agency_id_fkey',
        'employees', 'branches',
        ['agency_id'], ['id'],
        ondelete='SET NULL',
    )

    # ── 5. Table tickets : mettre à jour FK agency_id → branches ─────────────
    op.drop_constraint('tickets_agency_id_fkey', 'tickets', type_='foreignkey')
    op.create_foreign_key(
        'tickets_agency_id_fkey',
        'tickets', 'branches',
        ['agency_id'], ['id'],
        ondelete='CASCADE',
    )

    # ── 6. Table organizations : la relation est gérée au niveau ORM ──────────
    # Pas de FK directe organizations → agencies/branches dans le schéma initial
    # La relation est via Branch.org_id → organizations.id (déjà correct)


def downgrade() -> None:
    # Inverse : branches → agencies

    # Tickets
    op.drop_constraint('tickets_agency_id_fkey', 'tickets', type_='foreignkey')
    op.create_foreign_key(
        'tickets_agency_id_fkey',
        'tickets', 'agencies',
        ['agency_id'], ['id'],
        ondelete='CASCADE',
    )

    # Employees
    op.drop_constraint('employees_agency_id_fkey', 'employees', type_='foreignkey')
    op.create_foreign_key(
        'employees_agency_id_fkey',
        'employees', 'agencies',
        ['agency_id'], ['id'],
        ondelete='SET NULL',
    )

    # Counters
    op.drop_constraint('counters_agency_id_fkey', 'counters', type_='foreignkey')
    op.create_foreign_key(
        'counters_agency_id_fkey',
        'counters', 'agencies',
        ['agency_id'], ['id'],
        ondelete='CASCADE',
    )

    # Services : branch_id → agency_id
    op.drop_constraint('services_branch_id_fkey', 'services', type_='foreignkey')
    op.alter_column('services', 'branch_id', new_column_name='agency_id')
    op.create_foreign_key(
        'services_agency_id_fkey',
        'services', 'agencies',
        ['agency_id'], ['id'],
        ondelete='CASCADE',
    )

    # Renommer branches → agencies
    op.rename_table('branches', 'agencies')
