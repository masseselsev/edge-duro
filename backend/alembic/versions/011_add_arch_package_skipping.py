"""011_add_arch_package_skipping

Revision ID: 011_add_arch_package_skipping
Revises: 010_add_recipe_locale
Create Date: 2026-08-03 12:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa

from migration_utils import (
    add_column_if_missing,
    drop_column_if_exists,
)


revision: str = '011_add_arch_package_skipping'
down_revision: Union[str, None] = '010_add_recipe_locale'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        'recipes',
        sa.Column('ignore_missing_arch_packages', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    add_column_if_missing(
        'builds',
        sa.Column('missing_packages', sa.JSON(), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    drop_column_if_exists('builds', 'missing_packages')
    drop_column_if_exists('recipes', 'ignore_missing_arch_packages')
