"""Event-channel performance commands and recoverable Discord stage boards."""
from io import BytesIO
import logging
import discord
from discord import app_commands
from discord.ext import tasks
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.branding import SITE
from app.config import GUILD_ID, VERIFIED_ROLE_ID, ADMIN_IDS, BASE_URL
from app.db import Session, now, PerformanceEvent, PerformanceNotice
from app import performances as service

log = logging.getLogger(__name__)


def stage_text(state):
    def person(row):
        if not row: return '—'
        status = 'Ready' if row['ready'] else 'Arrived, not ready' if row['arrived'] else 'Not checked in'
        stamp = row['projected_start']
        estimate = f' · estimated <t:{int(stamp.timestamp())}:t>' if stamp else ''
        return f'<@{row["discord_id"]}> · {status}{estimate}'
    config = state['config']
    title = discord.utils.escape_mentions(discord.utils.escape_markdown(state['event'].title))[:200]
    current = state['current']
    performing = f'<@{current["discord_id"]}> · started <t:{int(current["actual_start"].timestamp())}:t>' if current else 'Transition / house music — awaiting organizer start'
    if current and current['paused']:
        performing += f' · PAUSED · {int(current["remaining_seconds"] // 60)} min {int(current["remaining_seconds"] % 60)} sec remaining'
    if not current and config.lifecycle == 'ended': performing = 'Event ended — final set sheet retained'
    elif not current and config.lifecycle == 'paused': performing = 'Paused — awaiting organizer resume'
    elif not current and config.lifecycle == 'scheduled': performing = 'Awaiting event activation'
    lines = [f'**{title} — {discord.utils.escape_markdown(SITE["event_manager_name"]).upper()}**', f'State: {config.lifecycle}' + (' · unpublished / suspended' if not state['event'].published else ''),
        f'**CURRENT:** {performing}', f'**NEXT:** {person(state["next"])}', f'**ON DECK:** {person(state["deck"])}',
        f'Registration: {"open" if config.registration_open else "closed"} · {config.set_minutes}-minute sets',
        'Performers: sign up with /perform action, then tap I’ve arrived and I’m ready.\nOnly the organizer starts performances or uses pause/recovery controls. Estimates can change.']
    if state['projected_finish']:
        lines.append(f'Projected finish: <t:{int(state["projected_finish"].timestamp())}:t>' +
            (f' · {state["overrun_seconds"] // 60} min beyond event window' if state['overrun_seconds'] else ''))
    if state['event'].published and config.lifecycle != 'ended':
        lines.append(f'[Open set timer]({BASE_URL}/meetups/{config.event_id}/timer)')
    return '\n'.join(lines)


def member_access(interaction):
    return bool(interaction.guild and interaction.guild.id == GUILD_ID and isinstance(interaction.user, discord.Member))


class StageView(discord.ui.View):
    def __init__(self, event_id, revision, next_id=None, current_id=None, *,
                 ended=False, published=True, current_paused=False, recover_id=None):
        super().__init__(timeout=None)
        # Member controls keep stable IDs across stage revisions and restarts.
        for action, label in [('checkin', 'I’ve arrived'), ('ready', 'I’m ready'),
                              ('notready', 'I’m not ready')]:
            button = discord.ui.Button(label=label, row=1,
                style=discord.ButtonStyle.success if action == 'ready' else discord.ButtonStyle.secondary,
                custom_id=f'performance:member:{event_id}:{action}',
                disabled=ended or (action != 'notready' and not published))
            async def member_callback(interaction, action=action):
                await run_action(interaction, event_id, action)
            button.callback = member_callback
            self.add_item(button)
        for action, label, target in [('start', 'Organizer: start next', next_id),
                                      ('end_set', 'Organizer: end set', current_id),
                                      ('resume_set' if current_paused else 'pause_set', 'Organizer: resume set' if current_paused else 'Organizer: pause set', current_id),
                                      ('recover_set', 'Restore last set', recover_id)]:
            button = discord.ui.Button(label=label, row=2, style=discord.ButtonStyle.primary,
                custom_id=f'performance:{event_id}:{revision}:{action}:{target or 0}', disabled=target is None)
            async def callback(interaction, action=action, target=target):
                await run_action(interaction, event_id, action, revision, target)
            button.callback = callback
            self.add_item(button)

    @classmethod
    def from_state(cls, state):
        config = state['config']
        return cls(config.event_id, config.revision,
            state['next']['id'] if (
                state['next'] and state['next']['ready'] and not state['current']
                and config.lifecycle == 'live' and not state['suspended']
            ) else None,
            state['current']['id'] if state['current'] and config.lifecycle != 'ended' else None,
            ended=config.lifecycle == 'ended',
            published=state['event'].published, current_paused=bool(state['current'] and state['current']['paused']),
            recover_id=state['recoverable']['id'] if state['recoverable'] and config.lifecycle == 'live' and state['event'].published else None)



async def show_member_status(interaction, event_id):
    if not member_access(interaction):
        return await interaction.response.send_message('Use this inside the configured server.', ephemeral=True)
    with Session() as db:
        config = db.get(PerformanceEvent, event_id)
        if not config or config.channel_id != interaction.channel_id:
            return await interaction.response.send_message('Use the event’s assigned performance channel or thread.', ephemeral=True)
        state = service.snapshot(db, event_id)
        rows = [r for r in state['queue'] if r['discord_id'] == interaction.user.id]
        row = next((r for r in rows if r['status'] in ('registered','playing')), rows[-1] if rows else None)
        if row:
            def stamp(value): return f'<t:{int(value.timestamp())}:t>' if value else '—'
            text = (f'Position {row["position"]} · {row["status"]}\n'
                    f'Original performance: {stamp(row["original_start"])}\n'
                    f'Projected: {stamp(row["projected_start"])}\n'
                    f'Actual start / end: {stamp(row["actual_start"])} / {stamp(row["actual_end"])}\n'
                    f'Arrived: {"yes" if row["arrived"] else "no"} · Ready: {"yes" if row["ready"] else "no"}\n'
                    f'Set clock: {"paused" if row["paused"] else row["status"]} · {int(row["remaining_seconds"] // 60)}m {int(row["remaining_seconds"] % 60)}s remaining\n'
                    'Only the organizer starts a set.')
        else:
            text = 'You have no active performer registration. Ordinary event RSVPs are separate.'
    await interaction.response.send_message(text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def run_action(interaction, event_id, action, revision=None, target_id=None):
    if not member_access(interaction):
        return await interaction.response.send_message('Use this inside the configured server.', ephemeral=True)
    with Session() as db:
        config = db.get(PerformanceEvent, event_id)
        if not config or config.channel_id != interaction.channel_id:
            return await interaction.response.send_message('Use the event’s assigned performance channel or thread.', ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    try:
        with Session() as db:
            result = service.execute(db, event_id, interaction.user.id, action,
                f'discord:{interaction.id}', organizer=interaction.user.id in ADMIN_IDS,
                verified=any(r.id == VERIFIED_ROLE_ID for r in interaction.user.roles),
                expected_revision=revision, target_id=target_id)
    except service.PerformanceError as exc:
        result = str(exc)
    await interaction.followup.send(result, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def refresh_board(bot, event_id):
    with Session() as db:
        state = service.snapshot(db, event_id)
        config = state['config']
        channel_id, message_id = config.channel_id, config.board_message_id
        deleted = state['event'].deleted_at is not None
        if not state['event'].published and not message_id:
            return  # Never announce a draft event or its private title.
        content = stage_text(state)
        view = StageView.from_state(state)
    channel = bot.get_channel(channel_id)
    if channel is None:
        channel = await bot.fetch_channel(channel_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread)) or channel.guild.id != GUILD_ID:
        return
    message = None
    if message_id:
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            pass
    if deleted:
        if message is not None:
            await message.delete()
        return
    if message is None:
        # Stable marker lets a restart recover a message sent just before a DB save failed.
        marker = f'Event board #{event_id}'
        async for recent in channel.history(limit=100):
            if recent.author.id == bot.user.id and recent.content.endswith(marker):
                message = recent; break
        if message is None:
            message = await channel.send(content + f'\n{marker}', view=view, allowed_mentions=discord.AllowedMentions.none())
        with Session.begin() as db:
            config = db.get(PerformanceEvent, event_id); config.board_message_id = message.id
    updated = content + f'\nEvent board #{event_id}'
    # Also update buttons when the stage revision changes but displayed labels do not.
    existing_components = [row.to_dict() for row in message.components]
    # Discord assigns component IDs that are absent from the locally built view.
    for row in existing_components:
        row.pop('id', None)
        for button in row.get('components', []):
            button.pop('id', None)
    if message.content != updated or existing_components != view.to_components():
        await message.edit(content=updated, view=view, allowed_mentions=discord.AllowedMentions.none())


async def deliver_notices(bot, event_id):
    with Session() as db:
        config = db.get(PerformanceEvent, event_id)
        if not config or config.lifecycle != 'live': return
        channel_id = config.channel_id
        ids = list(db.scalars(select(PerformanceNotice.id).where(PerformanceNotice.event_id == event_id,
            PerformanceNotice.sent_at.is_(None), PerformanceNotice.obsolete == False)))
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread)) or channel.guild.id != GUILD_ID: return
    for notice_id in ids:
        with Session() as db:
            row = db.get(PerformanceNotice, notice_id)
            if not row or row.sent_at or row.obsolete: continue
            content, recipient = row.content, row.recipient_id
        marker = f'Notice #{notice_id}'
        message = None
        # Recover a successful send if the process died before recording its message ID.
        async for recent in channel.history(limit=100):
            if recent.author.id == bot.user.id and recent.content.endswith(marker):
                message = recent; break
        if message is None:
            # History lookup awaits Discord. Re-read after it so a pause,
            # cancellation, or unpublish during that request suppresses the notice.
            with Session() as db:
                row = db.get(PerformanceNotice, notice_id)
                state = service.snapshot(db, event_id)
                role = row.delivery_key.rsplit(':', 1)[-1] if row else ''
                upcoming = state.get(role)
                if role.startswith('current-'):
                    warning = service.set_warning(state)
                    upcoming = state['current'] if warning and warning[0] == role else None
                if (not row or row.sent_at or row.obsolete or state['suspended'] or
                        state['config'].lifecycle != 'live' or not upcoming or
                        row.delivery_key != f'{event_id}:{upcoming["id"]}:{role}'):
                    continue
                content, recipient = row.content, row.recipient_id
            message = await channel.send(content + '\n' + marker,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=[discord.Object(id=recipient)]))
        with Session.begin() as db:
            row = db.get(PerformanceNotice, notice_id)
            row.sent_at = now(); row.message_id = message.id


async def reconcile(bot):
    with Session() as db:
        ids = list(db.scalars(select(PerformanceEvent.event_id)))
    for event_id in ids:
        try:
            with Session() as db:
                service.lock(db)
                service.queue_notices(db, event_id, now())
                db.commit()
            await refresh_board(bot, event_id)
            await deliver_notices(bot, event_id)
        except (discord.HTTPException, service.PerformanceError, SQLAlchemyError):
            log.exception('Performance reconciliation failed for event %s', event_id)


def register_performances(bot):
    group = app_commands.Group(name='perform', description='Performer registration and live stage coordination')

    @group.command(name='action', description='Register, withdraw, check in, or update readiness')
    @app_commands.choices(action=[app_commands.Choice(name=label, value=value) for value, label in [
        ('register','Register as performer'),('unregister','Withdraw performer registration'),('checkin','Arrived'),
        ('ready','Ready to perform'),('notready','Not ready')]])
    async def action(interaction: discord.Interaction, action: str):
        with Session() as db:
            config = db.scalar(select(PerformanceEvent).where(PerformanceEvent.channel_id == interaction.channel_id))
            event_id = config.event_id if config else None
        if event_id is None:
            return await interaction.response.send_message('This channel has no performance event configured.', ephemeral=True)
        await run_action(interaction, event_id, action)

    @group.command(name='stage', description='Show current, next, and on-deck performers')
    async def stage(interaction: discord.Interaction):
        if not member_access(interaction):
            return await interaction.response.send_message('Use this in the server.', ephemeral=True)
        with Session() as db:
            config = db.scalar(select(PerformanceEvent).where(PerformanceEvent.channel_id == interaction.channel_id))
            if not config:
                return await interaction.response.send_message('No performance event in this channel.', ephemeral=True)
            state = service.snapshot(db, config.event_id)
            content = stage_text(state)
            view = StageView.from_state(state)
        await interaction.response.send_message(content, view=view, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @group.command(name='mystatus', description='Show your performance position, arrival, and readiness')
    async def mystatus(interaction: discord.Interaction):
        if not member_access(interaction):
            return await interaction.response.send_message('Use this in the server.', ephemeral=True)
        with Session() as db:
            config = db.scalar(select(PerformanceEvent).where(PerformanceEvent.channel_id == interaction.channel_id))
            if not config:
                return await interaction.response.send_message('No performance event in this channel.', ephemeral=True)
            event_id = config.event_id
        await show_member_status(interaction, event_id)

    @group.command(name='setlist', description='Show original, projected, and actual performance times')
    async def setlist(interaction: discord.Interaction):
        if not member_access(interaction):
            return await interaction.response.send_message('Use this in the server.', ephemeral=True)
        with Session() as db:
            config = db.scalar(select(PerformanceEvent).where(PerformanceEvent.channel_id == interaction.channel_id))
            if not config:
                return await interaction.response.send_message('No performance event in this channel.', ephemeral=True)
            state = service.snapshot(db, config.event_id)
            lines = ['PERFORMER SET SHEET — original / projected / actual']
            def stamp(t): return f'<t:{int(t.timestamp())}:t>' if t else '—'
            for row in state['queue']:
                lines.append(f'{row["position"]}. <@{row["discord_id"]}> · {row["status"]} · {stamp(row["original_start"])} / {stamp(row["projected_start"])} / {stamp(row["actual_start"])}')
        chunks = []; chunk = ''
        for line in lines:
            if len(chunk) + len(line) + 1 > 1900: chunks.append(chunk); chunk = ''
            chunk += line + '\n'
        if chunk: chunks.append(chunk)
        await interaction.response.send_message(chunks[0], ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        for chunk in chunks[1:]: await interaction.followup.send(chunk, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @group.command(name='post_set_sheet', description='Post the final set sheet CSV in the event channel')
    async def post_set_sheet(interaction: discord.Interaction):
        if not member_access(interaction) or interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message('Organizer access required.', ephemeral=True)
        with Session() as db:
            config = db.scalar(select(PerformanceEvent).where(PerformanceEvent.channel_id == interaction.channel_id))
            if not config:
                return await interaction.response.send_message('Use this in the event channel.', ephemeral=True)
            event_id = config.event_id
            try:
                data = service.final_set_sheet_csv(service.snapshot(db, event_id))
            except service.PerformanceError as exc:
                return await interaction.response.send_message(str(exc), ephemeral=True)
        await interaction.response.send_message('Final performance set sheet',
            file=discord.File(BytesIO(data), filename=f'meetup-{event_id}-set-sheet.csv'))

    @group.command(name='organize', description='Control event lifecycle or explicitly skip an unavailable performer')
    @app_commands.choices(action=[app_commands.Choice(name=x, value=x) for x in ['activate','pause','resume','pause_set','resume_set','recover_set','close','open','skip','end_event']])
    async def organize(interaction: discord.Interaction, action: str):
        if not member_access(interaction) or interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message('Organizer access required.', ephemeral=True)
        with Session() as db:
            config = db.scalar(select(PerformanceEvent).where(PerformanceEvent.channel_id == interaction.channel_id))
            if not config: return await interaction.response.send_message('No event configured.', ephemeral=True)
            state = service.snapshot(db, config.event_id)
            event_id, revision = config.event_id, config.revision
            target = state['next']['id'] if action == 'skip' and state['next'] else None
            if action in ('pause_set','resume_set') and state['current']: target = state['current']['id']
            if action == 'recover_set' and state['recoverable']: target = state['recoverable']['id']
        await run_action(interaction, event_id, action, revision, target)

    bot.tree.add_command(group, guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)

    @tasks.loop(seconds=15)
    async def worker():
        try: await reconcile(bot)
        except Exception: log.exception('Performance worker failed; retrying on the next cycle')

    @worker.before_loop
    async def before_worker(): await bot.wait_until_ready()
    return worker
