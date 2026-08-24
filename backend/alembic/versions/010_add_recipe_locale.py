"""010_add_recipe_locale

Revision ID: 010_add_recipe_locale
Revises: 009_add_recipe_is_dev
Create Date: 2026-07-31 11:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa

from migration_utils import (
    add_column_if_missing,
    drop_column_if_exists,
)


revision: str = '010_add_recipe_locale'
down_revision: Union[str, None] = '009_add_recipe_is_dev'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing('recipes', sa.Column('locale', sa.String(), nullable=False, server_default='C.UTF-8'))


def downgrade() -> None:
    drop_column_if_exists('recipes', 'locale')
