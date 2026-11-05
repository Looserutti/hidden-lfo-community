"""Separate externally sourced calendar listings.
Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    # Legacy 0001 creates current metadata for fresh installs.
    if not sa.inspect(op.get_bind()).has_table('imported_events'):
        op.create_table('imported_events',
            sa.Column('source_id', sa.String(80), primary_key=True),
            sa.Column('external_id', sa.String(160), primary_key=True),
            sa.Column('title', sa.String(250), nullable=False),
            sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('location', sa.String(250), nullable=False),
            sa.Column('source_url', sa.Text(), nullable=False),
            sa.Column('cancelled', sa.Boolean(), nullable=False),
            sa.Column('suppressed', sa.Boolean(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    raise RuntimeError('Restore a backup instead of destructive downgrade.')
