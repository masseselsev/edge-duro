"""006_partitions_log_retention

Revision ID: 006_partitions_log_retention
Revises: 005_add_iso_artifact_to_builds
Create Date: 2026-07-29 18:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa

from migration_utils import (
    add_column_if_missing,
    drop_column_if_exists,
)


revision: str = '006_partitions_log_retention'
down_revision: Union[str, None] = '005_add_iso_artifact_to_builds'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing('recipes', sa.Column('partitions', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    add_column_if_missing('settings', sa.Column('log_retention_days', sa.Integer(), nullable=False, server_default='3'))


def downgrade() -> None:
    drop_column_if_exists('settings', 'log_retention_days')
    drop_column_if_exists('recipes', 'partitions')