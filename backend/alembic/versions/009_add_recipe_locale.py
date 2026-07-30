"""009_add_recipe_locale

Revision ID: 009_add_recipe_locale
Revises: 008_add_recipe_is_dev
Create Date: 2026-07-31 11:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '009_add_recipe_locale'
down_revision: Union[str, None] = '008_add_recipe_is_dev'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recipes', sa.Column('locale', sa.String(), nullable=False, server_default='C.UTF-8'))


def downgrade() -> None:
    op.drop_column('recipes', 'locale')
