"""002_add_kernel_params_and_firstboot

Revision ID: 002_add_kernel_params_and_firstboot
Revises: 001_initial_schema
Create Date: 2026-07-24 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '002_add_kernel_params_and_firstboot'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recipes', sa.Column('kernel_params', sa.String(), nullable=True))
    op.add_column('recipes', sa.Column('raw_firstboot', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('recipes', 'raw_firstboot')
    op.drop_column('recipes', 'kernel_params')
