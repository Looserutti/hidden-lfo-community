import asyncio
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Member


def test_verification_timestamp_is_preserved(tmp_path):
    # Create a temporary test database.
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    original_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with Session() as db:
        member = Member(discord_id=123456789, verified_at=original_time)
        db.add(member)
        db.commit()

    # Simulate the timestamp-preserving database logic.
    with Session() as db:
        member = db.query(Member).filter_by(discord_id=123456789).one()

        if member.verified_at is None:
            member.verified_at = datetime.now(timezone.utc)

        db.commit()
        assert member.verified_at == original_time.replace(tzinfo=None)

    import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from bot.main import RulesView


def test_agree_button_preserves_timestamp_on_second_click(tmp_path):
    # Create an isolated test database.
    engine = create_engine(f"sqlite:///{tmp_path / 'button_test.db'}")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    member_id = 123456789
    original_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with TestSession() as db:
        db.add(Member(discord_id=member_id, verified_at=original_time))
        db.commit()

    role = MagicMock(spec=discord.Role)

    user = MagicMock(spec=discord.Member)
    user.id = member_id
    user.roles = [role]
    user.add_roles = AsyncMock()

    guild = MagicMock(spec=discord.Guild)
    guild.get_role.return_value = role

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = user
    interaction.response.send_message = AsyncMock()

    view = RulesView()
    button = view.children[0]

    async def click_twice():
        await button.callback(interaction)
        await button.callback(interaction)

    with (
        patch("bot.main.GUILD_ID", guild.id),
        patch("bot.main.Session", TestSession),
    ):
        asyncio.run(click_twice())

    # An already-verified member should not receive the role again.
    user.add_roles.assert_not_awaited()

    # Both clicks should receive a successful response.
    assert interaction.response.send_message.await_count == 2

    # The original verification timestamp must remain unchanged.
    with TestSession() as db:
        saved = db.query(Member).filter_by(discord_id=member_id).one()
        assert saved.verified_at == original_time.replace(tzinfo=None) 

def test_agree_button_handles_discord_permission_error(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'permission_test.db'}")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    member_id = 987654321
    role = MagicMock(spec=discord.Role)

    user = MagicMock(spec=discord.Member)
    user.id = member_id
    user.roles = []
    user.add_roles = AsyncMock(
        side_effect=discord.Forbidden(
            MagicMock(status=403, reason="Forbidden"),
            "Missing Permissions",
        )
    )

    guild = MagicMock(spec=discord.Guild)
    guild.get_role.return_value = role

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = user
    interaction.response.send_message = AsyncMock()

    view = RulesView()
    button = view.children[0]

    with (
        patch("bot.main.GUILD_ID", guild.id),
        patch("bot.main.Session", TestSession),
    ):
        asyncio.run(button.callback(interaction))

    user.add_roles.assert_awaited_once()
    interaction.response.send_message.assert_awaited_once_with(
        "I cannot assign that role. Please contact an administrator.",
        ephemeral=True,
    )

    with TestSession() as db:
        saved = db.query(Member).filter_by(discord_id=member_id).one_or_none()
        assert saved is None or saved.verified_at is None