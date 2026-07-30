"""007_add_recipe_credentials

Revision ID: 007_add_recipe_credentials
Revises: 006_add_partitions_and_log_retention
Create Date: 2026-07-30 18:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '007_add_recipe_credentials'
down_revision: Union[str, None] = '006_add_partitions_and_log_retention'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recipes', sa.Column('root_password', sa.String(), nullable=True))
    op.add_column('recipes', sa.Column('users', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))


def downgrade() -> None:
    op.drop_column('recipes', 'users')
    op.drop_column('recipes', 'root_password')
