"""012_add_recipe_board

Revision ID: 012_add_recipe_board
Revises: 011_add_arch_package_skipping
Create Date: 2026-08-06 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '012_add_recipe_board'
down_revision: Union[str, None] = '011_add_arch_package_skipping'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'recipes',
        sa.Column('board', sa.String(), nullable=False, server_default='generic'),
    )


def downgrade() -> None:
    op.drop_column('recipes', 'board')
