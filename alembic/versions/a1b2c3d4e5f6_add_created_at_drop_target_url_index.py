"""Add created_at, drop target_url index

Revision ID: a1b2c3d4e5f6
Revises: 738c9066211c
Create Date: 2026-03-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '738c9066211c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('urls', sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False))
    op.drop_index('ix_urls_target_url', table_name='urls')


def downgrade() -> None:
    op.create_index('ix_urls_target_url', 'urls', ['target_url'], unique=False)
    op.drop_column('urls', 'created_at')
