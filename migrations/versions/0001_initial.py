"""Initial schema corresponding to the Version 4 models.

Revision ID: 0001
Revises:
"""
from alembic import op
from app.db import Base
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # For a fresh database. Existing V4 databases must be backed up, schema-reviewed,
    # and stamped instead; running this on existing tables will fail safely.
    Base.metadata.create_all(bind=op.get_bind())

def downgrade():
    raise RuntimeError('Destructive downgrade intentionally disabled; restore a backup instead.')
