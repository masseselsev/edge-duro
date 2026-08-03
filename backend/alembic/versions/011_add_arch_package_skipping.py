"""011_add_arch_package_skipping

Revision ID: 011_add_arch_package_skipping
Revises: 010_add_recipe_locale
Create Date: 2026-08-03 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '011_add_arch_package_skipping'
down_revision: Union[str, None] = '010_add_recipe_locale'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'recipes',
        sa.Column('ignore_missing_arch_packages', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'builds',
        sa.Column('missing_packages', sa.JSON(), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('builds', 'missing_packages')
    op.drop_column('recipes', 'ignore_missing_arch_packages')
