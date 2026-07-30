"""009_add_recipe_is_dev

Revision ID: 009_add_recipe_is_dev
Revises: 008_add_recipe_ssh_port
Create Date: 2026-07-31 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '009_add_recipe_is_dev'
down_revision: Union[str, None] = '008_add_recipe_ssh_port'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recipes', sa.Column('is_dev', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('recipes', 'is_dev')
