"""Preserve remaining set time through interruptions and accidental-end recovery."""
from alembic import op
import sqlalchemy as sa
revision = '0009'
down_revision = '0008'
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {c['name'] for c in sa.inspect(bind).get_columns('performer_registrations')}
    if 'paused_at' not in columns:
        op.add_column('performer_registrations', sa.Column('paused_at', sa.DateTime(), nullable=True))
    if 'paused_seconds' not in columns:
        op.add_column('performer_registrations', sa.Column('paused_seconds', sa.Float(), nullable=False, server_default='0'))


def downgrade():
    raise RuntimeError('Restore a verified backup instead of deleting interruption history.')
