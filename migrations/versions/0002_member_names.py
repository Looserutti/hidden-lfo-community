"""Store latest observed Discord username and server display name.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    # The legacy initial migration creates from current ORM metadata on fresh installs.
    # Add only missing columns so both fresh and existing installations upgrade safely.
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('members')}
    for name in ('discord_username', 'server_display_name'):
        if name not in existing:
            op.add_column('members', sa.Column(name, sa.String(128), nullable=True))


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a backup instead.')
