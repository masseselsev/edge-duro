"""013_add_recipe_ssh_access

Revision ID: 013_add_recipe_ssh_access
Revises: 012_add_recipe_board
Create Date: 2026-08-20 10:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa

from migration_utils import (
    add_column_if_missing,
    drop_column_if_exists,
)


revision: str = '013_add_recipe_ssh_access'
down_revision: Union[str, None] = '012_add_recipe_board'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Password login is allowed by default: an image with no keys would
    # otherwise be unreachable. Root password login is closed, as is customary
    # on Debian and Ubuntu.
    add_column_if_missing(
        'recipes',
        sa.Column('ssh_password_auth', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    add_column_if_missing(
        'recipes',
        sa.Column('ssh_permit_root_login', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    drop_column_if_exists('recipes', 'ssh_permit_root_login')
    drop_column_if_exists('recipes', 'ssh_password_auth')
