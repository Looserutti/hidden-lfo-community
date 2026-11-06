"""Optional per-track artist social links, hidden by default."""
from alembic import op
import sqlalchemy as sa
revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('gallery_tracks', sa.Column('artist_social_url', sa.String(2048), nullable=False, server_default=''))
    op.add_column('gallery_tracks', sa.Column('artist_social_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))

def downgrade():
    raise RuntimeError('Restore a matching database backup instead.')
