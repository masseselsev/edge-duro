"""006_add_partitions_and_log_retention

Revision ID: 006_add_partitions_and_log_retention
Revises: 005_add_iso_artifact_to_builds
Create Date: 2026-07-29 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '006_add_partitions_and_log_retention'
down_revision: Union[str, None] = '005_add_iso_artifact_to_builds'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recipes', sa.Column('partitions', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.add_column('settings', sa.Column('log_retention_days', sa.Integer(), nullable=False, server_default='3'))


def downgrade() -> None:
    op.drop_column('settings', 'log_retention_days')
    op.drop_column('recipes', 'partitions')