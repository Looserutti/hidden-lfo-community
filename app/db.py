from datetime import datetime, timezone
from sqlalchemy import create_engine, ForeignKey, String, Integer, DateTime, Boolean, UniqueConstraint, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from app.config import DATABASE_URL

class Base(DeclarativeBase):
    pass

def now():
    return datetime.now(timezone.utc)

class Member(Base):
    __tablename__ = 'members'
    discord_id: Mapped[int] = mapped_column(primary_key=True)
    discord_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    server_display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_server_activity: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_observed_online: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exempt: Mapped[bool] = mapped_column(Boolean, default=False)

class Event(Base):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str] = mapped_column(String(250), default='Discord')
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    discord_message_id: Mapped[int | None] = mapped_column(nullable=True)
    discord_channel_id: Mapped[int | None] = mapped_column(nullable=True)

class Registration(Base):
    __tablename__ = 'registrations'
    __table_args__ = (UniqueConstraint('event_id', 'discord_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id'))
    discord_id: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default='going')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Setting(Base):
    __tablename__ = 'settings'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)

engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False, 'timeout': 30} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
if DATABASE_URL.startswith('sqlite'):
    from sqlalchemy import event as sa_event
    @sa_event.listens_for(engine, 'connect')
    def pragmas(connection, record):
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA busy_timeout=30000')
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()
Session = sessionmaker(engine, expire_on_commit=False)

def init_db():
    Base.metadata.create_all(engine)


class ImportedEvent(Base):
    """Source listings stay separate from community events and their RSVPs."""
    __tablename__ = 'imported_events'
    source_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    title: Mapped[str] = mapped_column(String(250))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str] = mapped_column(String(250), default='')
    source_url: Mapped[str] = mapped_column(Text)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EventSubmission(Base):
    """Member proposals remain separate from public events until approval."""
    __tablename__ = 'event_submissions'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    interaction_id: Mapped[str] = mapped_column(String(32), unique=True)
    submitted_by: Mapped[int] = mapped_column()
    submitted_name: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str] = mapped_column(String(250))
    status: Mapped[str] = mapped_column(String(20), default='pending')
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reviewed_by: Mapped[int | None] = mapped_column(nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey('events.id'), nullable=True)


class GalleryTrack(Base):
    """Audio metadata; actual uploads live outside source control."""
    __tablename__ = 'gallery_tracks'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    artist: Mapped[str] = mapped_column(String(160), default='')
    filename: Mapped[str] = mapped_column(String(80), unique=True)
    byte_size: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=0)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
