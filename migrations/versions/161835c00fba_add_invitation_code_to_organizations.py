"""add_invitation_code_to_organizations — S2-08 Join by Code

Révision ID: 161835c00fba
Révision précédente: c0d78e94182b
Date: 2026-07-11

Ajoute 3 colonnes à la table organizations :
  - invitation_code       : code alphanumérique 8 chars, UNIQUE, nullable
  - invitation_expires_at : expiration du code, nullable
  - invitation_code_active: booléen, défaut False
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '161835c00fba'
down_revision: Union[str, None] = 'c0d78e94182b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column(
        'invitation_code', sa.String(length=12), nullable=True
    ))
    op.add_column('organizations', sa.Column(
        'invitation_expires_at', sa.DateTime(timezone=True), nullable=True
    ))
    op.add_column('organizations', sa.Column(
        'invitation_code_active', sa.Boolean(), nullable=False,
        server_default=sa.text('false')
    ))
    op.create_index(
        'ix_organizations_invitation_code',
        'organizations',
        ['invitation_code'],
        unique=True
    )


def downgrade() -> None:
    op.drop_index('ix_organizations_invitation_code', table_name='organizations')
    op.drop_column('organizations', 'invitation_code_active')
    op.drop_column('organizations', 'invitation_expires_at')
    op.drop_column('organizations', 'invitation_code')
