"""004_add_hostname_from_netif

Revision ID: 004_add_hostname_from_netif
Revises: 003_add_recipe_timezone
Create Date: 2026-07-24 13:50:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa

from migration_utils import (
    add_column_if_missing,
    drop_column_if_exists,
)


revision: str = '004_add_hostname_from_netif'
down_revision: Union[str, None] = '003_add_recipe_timezone'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing('recipes', sa.Column('hostname_from_netif', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    drop_column_if_exists('recipes', 'hostname_from_netif')
