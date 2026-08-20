"""013_add_recipe_ssh_access

Revision ID: 013_add_recipe_ssh_access
Revises: 012_add_recipe_board
Create Date: 2026-08-20 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '013_add_recipe_ssh_access'
down_revision: Union[str, None] = '012_add_recipe_board'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Password login is allowed by default: an image with no keys would
    # otherwise be unreachable. Root password login is closed, as is customary
    # on Debian and Ubuntu.
    op.add_column(
        'recipes',
        sa.Column('ssh_password_auth', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'recipes',
        sa.Column('ssh_permit_root_login', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('recipes', 'ssh_permit_root_login')
    op.drop_column('recipes', 'ssh_password_auth')
