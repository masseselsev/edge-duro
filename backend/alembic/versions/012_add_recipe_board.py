"""012_add_recipe_board

Revision ID: 012_add_recipe_board
Revises: 011_add_arch_package_skipping
Create Date: 2026-08-06 12:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa

from migration_utils import (
    add_column_if_missing,
    drop_column_if_exists,
)


revision: str = '012_add_recipe_board'
down_revision: Union[str, None] = '011_add_arch_package_skipping'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        'recipes',
        sa.Column('board', sa.String(), nullable=False, server_default='generic'),
    )


def downgrade() -> None:
    drop_column_if_exists('recipes', 'board')
