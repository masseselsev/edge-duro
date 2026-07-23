"""001_initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-07-23 20:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. settings
    op.create_table(
        'settings',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('server_name', sa.String(), nullable=False, server_default='Edge-D.U.R.O.'),
        sa.Column('timezone', sa.String(), nullable=False, server_default='Browser Local'),
        sa.Column('language', sa.String(), nullable=False, server_default='en'),
        sa.Column('duro_workspace_path', sa.String(), nullable=False, server_default='/opt/data/duro_workspace')
    )

    # 2. users
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('username', sa.String(), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('telegram_id', sa.String(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('is_superadmin', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_admin_plus', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )
    op.create_index('ix_users_username', 'users', ['username'], unique=True)

    # 3. recipes
    op.create_table(
        'recipes',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('distribution', sa.String(), nullable=False, server_default='debian'),
        sa.Column('release', sa.String(), nullable=False, server_default='bookworm'),
        sa.Column('architecture', sa.String(), nullable=False, server_default='amd64'),
        sa.Column('output_formats', sa.JSON(), nullable=False),
        sa.Column('packages', sa.JSON(), nullable=False),
        sa.Column('repositories', sa.JSON(), nullable=False),
        sa.Column('hostname', sa.String(), nullable=False, server_default='edge-node'),
        sa.Column('network_config', sa.JSON(), nullable=True),
        sa.Column('ssh_keys', sa.JSON(), nullable=False),
        sa.Column('raw_mkosi_conf', sa.Text(), nullable=True),
        sa.Column('raw_preseed_cfg', sa.Text(), nullable=True),
        sa.Column('raw_postinst', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('last_build_at', sa.DateTime(), nullable=True),
        sa.Column('last_build_status', sa.String(), nullable=True)
    )
    op.create_index('ix_recipes_name', 'recipes', ['name'], unique=True)

    # 4. builds
    op.create_table(
        'builds',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('recipe_id', sa.Integer(), sa.ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='PENDING'),
        sa.Column('triggered_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('log_output', sa.Text(), nullable=False, server_default=''),
        sa.Column('artifact_path', sa.String(), nullable=True),
        sa.Column('artifact_size', sa.BigInteger(), nullable=True),
        sa.Column('output_format', sa.String(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True)
    )

    # 5. recipe_assets
    op.create_table(
        'recipe_assets',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('recipe_id', sa.Integer(), sa.ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('file_type', sa.String(), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('install_target', sa.String(), nullable=True),
        sa.Column('is_postinst', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
    )

    # 6. system_logs
    op.create_table(
        'system_logs',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('level', sa.String(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
    )

    # 7. audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
    )
    op.create_index('ix_audit_logs_username', 'audit_logs', ['username'])


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('system_logs')
    op.drop_table('recipe_assets')
    op.drop_table('builds')
    op.drop_table('recipes')
    op.drop_table('users')
    op.drop_table('settings')
