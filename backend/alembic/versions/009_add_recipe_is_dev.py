"""009_add_recipe_is_dev

Revision ID: 009_add_recipe_is_dev
Revises: 008_add_recipe_ssh_port
Create Date: 2026-07-31 10:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa

from migration_utils import (
    add_column_if_missing,
    drop_column_if_exists,
)


revision: str = '009_add_recipe_is_dev'
down_revision: Union[str, None] = '008_add_recipe_ssh_port'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing('recipes', sa.Column('is_dev', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    drop_column_if_exists('recipes', 'is_dev')
