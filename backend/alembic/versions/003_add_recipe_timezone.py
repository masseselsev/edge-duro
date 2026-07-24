"""003_add_recipe_timezone

Revision ID: 003_add_recipe_timezone
Revises: 002_add_kernel_params_and_firstboot
Create Date: 2026-07-24 13:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '003_add_recipe_timezone'
down_revision: Union[str, None] = '002_add_kernel_params_and_firstboot'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recipes', sa.Column('timezone', sa.String(), nullable=False, server_default='UTC'))


def downgrade() -> None:
    op.drop_column('recipes', 'timezone')
