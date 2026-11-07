"""Additive live-performance records; attendance RSVPs remain independent."""
from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, CheckConstraint, Index, text, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base, now


class PerformanceEvent(Base):
    __tablename__ = 'performance_events'
    __table_args__ = (CheckConstraint('set_minutes > 0 AND transition_seconds >= minimum_seconds AND minimum_seconds >= 0'),
                      CheckConstraint('capacity > 0 AND revision >= 0'),)
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id'), primary_key=True)
    channel_id: Mapped[int] = mapped_column(unique=True)
    board_message_id: Mapped[int | None] = mapped_column(nullable=True)
    registration_open: Mapped[bool] = mapped_column(default=True)
    lifecycle: Mapped[str] = mapped_column(String(20), default='scheduled')
    starts_at: Mapped[datetime] = mapped_column()
    ends_at: Mapped[datetime] = mapped_column()
    set_minutes: Mapped[int] = mapped_column(default=15)
    transition_seconds: Mapped[int] = mapped_column(default=0)
    minimum_seconds: Mapped[int] = mapped_column(default=0)
    capacity: Mapped[int] = mapped_column(default=25)
    revision: Mapped[int] = mapped_column(default=0)
    last_ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    next_notice_minutes: Mapped[int] = mapped_column(default=10)
    deck_notice_minutes: Mapped[int] = mapped_column(default=25)


class PerformanceSlot(Base):
    __tablename__ = 'performance_slots'
    __table_args__ = (UniqueConstraint('event_id', 'position'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('performance_events.event_id'))
    position: Mapped[int] = mapped_column()
    original_start: Mapped[datetime] = mapped_column()
    original_end: Mapped[datetime] = mapped_column()


class PerformerRegistration(Base):
    __tablename__ = 'performer_registrations'
    __table_args__ = (
        Index('uq_active_performer', 'event_id', 'discord_id', unique=True,
              sqlite_where=text("status IN ('registered', 'playing')"),
              postgresql_where=text("status IN ('registered', 'playing')")),
        Index('uq_occupied_performance_slot', 'slot_id', unique=True,
              sqlite_where=text("status != 'cancelled'"), postgresql_where=text("status != 'cancelled'")),
        Index('uq_current_performance', 'event_id', unique=True,
              sqlite_where=text("status = 'playing'"), postgresql_where=text("status = 'playing'")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('performance_events.event_id'))
    slot_id: Mapped[int] = mapped_column(ForeignKey('performance_slots.id'))
    discord_id: Mapped[int] = mapped_column()
    registered_at: Mapped[datetime] = mapped_column(default=now)
    status: Mapped[str] = mapped_column(String(20), default='registered')
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    arrived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(nullable=True)
    actual_start: Mapped[datetime | None] = mapped_column(nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(nullable=True)
    paused_seconds: Mapped[float] = mapped_column(Float, default=0.0)


class PerformanceAction(Base):
    __tablename__ = 'performance_actions'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('performance_events.event_id'))
    request_id: Mapped[str] = mapped_column(String(160), unique=True)
    actor_id: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[int | None] = mapped_column(nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(default=now)
    result: Mapped[str] = mapped_column(Text)


class PerformanceNotice(Base):
    __tablename__ = 'performance_notices'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('performance_events.event_id'))
    delivery_key: Mapped[str] = mapped_column(String(160), unique=True)
    content: Mapped[str] = mapped_column(Text)
    recipient_id: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=now)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    message_id: Mapped[int | None] = mapped_column(nullable=True)
    obsolete: Mapped[bool] = mapped_column(default=False)
