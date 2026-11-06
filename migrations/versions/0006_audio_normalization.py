"""Optional normalized playback copies; original audio is preserved."""
from alembic import op
import sqlalchemy as sa
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('gallery_tracks')}
    columns = [sa.Column('normalized_filename',sa.String(80),nullable=True),
        sa.Column('normalized_byte_size',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('normalization_enabled',sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column('normalization_status',sa.String(20),nullable=False,server_default='original'),
        sa.Column('normalization_error',sa.String(240),nullable=False,server_default=''),
        sa.Column('target_lufs',sa.Float(),nullable=False,server_default='-14'),
        sa.Column('output_lufs',sa.Float(),nullable=True)]
    for column in columns:
        if column.name not in existing:op.add_column('gallery_tracks',column)


def downgrade():
    raise RuntimeError('Restore matching database and audio backups instead.')
