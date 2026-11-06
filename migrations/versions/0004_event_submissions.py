"""Member event proposals and staff review history."""
from alembic import op
from app.db import EventSubmission
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    # Also handles fresh installs whose legacy initial migration creates metadata.
    EventSubmission.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Restore a backup instead of deleting submission history.')
