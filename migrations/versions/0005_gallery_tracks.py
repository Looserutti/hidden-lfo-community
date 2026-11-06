"""Gallery soundtrack metadata; audio files stay in persistent storage."""
from alembic import op
from app.db import GalleryTrack
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    GalleryTrack.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Restore a backup instead of deleting gallery audio metadata.')
