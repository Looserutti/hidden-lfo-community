"""Remove events from active listings while retaining their records."""
from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = depends_on = None


def upgrade():
    if 'deleted_at' not in {column['name'] for column in sa.inspect(op.get_bind()).get_columns('events')}:
        op.add_column('events', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('events', 'deleted_at')
