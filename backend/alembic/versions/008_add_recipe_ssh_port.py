"""008_add_recipe_ssh_port

Revision ID: 008_add_recipe_ssh_port
Revises: 007_add_recipe_credentials
Create Date: 2026-07-30 23:58:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa

from migration_utils import (
    add_column_if_missing,
    drop_column_if_exists,
)


revision: str = '008_add_recipe_ssh_port'
down_revision: Union[str, None] = '007_add_recipe_credentials'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing('recipes', sa.Column('ssh_port', sa.Integer(), nullable=False, server_default='2222'))


def downgrade() -> None:
    drop_column_if_exists('recipes', 'ssh_port')
