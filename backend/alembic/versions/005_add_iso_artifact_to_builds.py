"""add iso artifact columns to builds

Revision ID: 005_add_iso_artifact_to_builds
Revises: 004_add_hostname_from_netif
Create Date: 2026-07-24 16:35:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '005_add_iso_artifact_to_builds'
down_revision = '004_add_hostname_from_netif'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('builds', sa.Column('iso_artifact_path', sa.String(), nullable=True))
    op.add_column('builds', sa.Column('iso_artifact_size', sa.BigInteger(), nullable=True))


def downgrade():
    op.drop_column('builds', 'iso_artifact_size')
    op.drop_column('builds', 'iso_artifact_path')
