"""Independent performer registration and durable stage workflow.

The legacy 0001 reads live metadata. Check individual objects on fresh installs,
while using frozen definitions here for upgrades from 0007.
"""
from alembic import op
import sqlalchemy as sa
revision = '0008'
down_revision = '0007'
branch_labels = depends_on = None


def upgrade():
    meta = sa.MetaData()
    sa.Table('events', meta, sa.Column('id', sa.Integer, primary_key=True))
    configs = sa.Table('performance_events', meta,
        sa.Column('event_id', sa.Integer, sa.ForeignKey('events.id'), primary_key=True),
        sa.Column('channel_id', sa.Integer, nullable=False, unique=True),
        sa.Column('board_message_id', sa.Integer),
        sa.Column('registration_open', sa.Boolean, nullable=False),
        sa.Column('lifecycle', sa.String(20), nullable=False),
        sa.Column('starts_at', sa.DateTime, nullable=False), sa.Column('ends_at', sa.DateTime, nullable=False),
        sa.Column('set_minutes', sa.Integer, nullable=False),
        sa.Column('transition_seconds', sa.Integer, nullable=False),
        sa.Column('minimum_seconds', sa.Integer, nullable=False),
        sa.Column('capacity', sa.Integer, nullable=False), sa.Column('revision', sa.Integer, nullable=False),
        sa.Column('last_ended_at', sa.DateTime),
        sa.Column('next_notice_minutes', sa.Integer, nullable=False),
        sa.Column('deck_notice_minutes', sa.Integer, nullable=False),
        sa.CheckConstraint('set_minutes > 0 AND transition_seconds >= minimum_seconds AND minimum_seconds >= 0'),
        sa.CheckConstraint('capacity > 0 AND revision >= 0'))
    slots = sa.Table('performance_slots', meta,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('event_id', sa.Integer, sa.ForeignKey('performance_events.event_id'), nullable=False),
        sa.Column('position', sa.Integer, nullable=False),
        sa.Column('original_start', sa.DateTime, nullable=False), sa.Column('original_end', sa.DateTime, nullable=False),
        sa.UniqueConstraint('event_id', 'position'))
    registrations = sa.Table('performer_registrations', meta,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('event_id', sa.Integer, sa.ForeignKey('performance_events.event_id'), nullable=False),
        sa.Column('slot_id', sa.Integer, sa.ForeignKey('performance_slots.id'), nullable=False),
        sa.Column('discord_id', sa.Integer, nullable=False),
        sa.Column('registered_at', sa.DateTime, nullable=False), sa.Column('status', sa.String(20), nullable=False),
        *[sa.Column(name, sa.DateTime) for name in ('cancelled_at','arrived_at','ready_at','actual_start','actual_end')])
    for name, columns, condition in [
        ('uq_active_performer', ['event_id','discord_id'], "status IN ('registered', 'playing')"),
        ('uq_occupied_performance_slot', ['slot_id'], "status != 'cancelled'"),
        ('uq_current_performance', ['event_id'], "status = 'playing'")]:
        sa.Index(name, *[registrations.c[c] for c in columns], unique=True,
                 sqlite_where=sa.text(condition), postgresql_where=sa.text(condition))
    actions = sa.Table('performance_actions', meta,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('event_id', sa.Integer, sa.ForeignKey('performance_events.event_id'), nullable=False),
        sa.Column('request_id', sa.String(160), nullable=False, unique=True),
        sa.Column('actor_id', sa.Integer, nullable=False), sa.Column('action', sa.String(40), nullable=False),
        sa.Column('target_id', sa.Integer), sa.Column('recorded_at', sa.DateTime, nullable=False),
        sa.Column('result', sa.Text, nullable=False))
    notices = sa.Table('performance_notices', meta,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('event_id', sa.Integer, sa.ForeignKey('performance_events.event_id'), nullable=False),
        sa.Column('delivery_key', sa.String(160), nullable=False, unique=True),
        sa.Column('content', sa.Text, nullable=False), sa.Column('recipient_id', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False), sa.Column('sent_at', sa.DateTime),
        sa.Column('message_id', sa.Integer), sa.Column('obsolete', sa.Boolean, nullable=False))
    bind = op.get_bind()
    for table in (configs, slots, registrations, actions, notices):
        table.create(bind, checkfirst=True)
        for index in table.indexes:
            index.create(bind, checkfirst=True)


def downgrade():
    raise RuntimeError('Restore a verified backup instead of deleting performance history.')
