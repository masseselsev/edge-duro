"""add iso artifact columns to builds

Revision ID: 005_add_iso_artifact_to_builds
Revises: 004_add_hostname_from_netif
Create Date: 2026-07-24 16:35:00.000000

"""
import sqlalchemy as sa

from migration_utils import (
    add_column_if_missing,
    drop_column_if_exists,
)

revision = '005_add_iso_artifact_to_builds'
down_revision = '004_add_hostname_from_netif'
branch_labels = None
depends_on = None


def upgrade():
    add_column_if_missing('builds', sa.Column('iso_artifact_path', sa.String(), nullable=True))
    add_column_if_missing('builds', sa.Column('iso_artifact_size', sa.BigInteger(), nullable=True))


def downgrade():
    drop_column_if_exists('builds', 'iso_artifact_size')
    drop_column_if_exists('builds', 'iso_artifact_path')
