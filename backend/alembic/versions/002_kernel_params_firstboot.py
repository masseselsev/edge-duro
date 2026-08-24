"""002_kernel_params_firstboot

Revision ID: 002_kernel_params_firstboot
Revises: 001_initial_schema
Create Date: 2026-07-24 12:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa

from migration_utils import (
    add_column_if_missing,
    drop_column_if_exists,
)


revision: str = '002_kernel_params_firstboot'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing('recipes', sa.Column('kernel_params', sa.String(), nullable=True))
    add_column_if_missing('recipes', sa.Column('raw_firstboot', sa.Text(), nullable=True))


def downgrade() -> None:
    drop_column_if_exists('recipes', 'raw_firstboot')
    drop_column_if_exists('recipes', 'kernel_params')
