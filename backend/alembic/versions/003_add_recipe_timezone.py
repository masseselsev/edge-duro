"""003_add_recipe_timezone

Revision ID: 003_add_recipe_timezone
Revises: 002_kernel_params_firstboot
Create Date: 2026-07-24 13:20:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa

from migration_utils import (
    add_column_if_missing,
    drop_column_if_exists,
)


revision: str = '003_add_recipe_timezone'
down_revision: Union[str, None] = '002_kernel_params_firstboot'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing('recipes', sa.Column('timezone', sa.String(), nullable=False, server_default='UTC'))


def downgrade() -> None:
    drop_column_if_exists('recipes', 'timezone')
