"""007_add_recipe_credentials

Revision ID: 007_add_recipe_credentials
Revises: 006_partitions_log_retention
Create Date: 2026-07-30 18:30:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa

from migration_utils import (
    add_column_if_missing,
    drop_column_if_exists,
)


revision: str = '007_add_recipe_credentials'
down_revision: Union[str, None] = '006_partitions_log_retention'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing('recipes', sa.Column('root_password', sa.String(), nullable=True))
    add_column_if_missing('recipes', sa.Column('users', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))


def downgrade() -> None:
    drop_column_if_exists('recipes', 'users')
    drop_column_if_exists('recipes', 'root_password')
