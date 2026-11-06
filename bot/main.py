import asyncio
import logging
import os
from datetime import timezone
import discord
from discord import app_commands
from discord.ext import commands, tasks
from sqlalchemy import select, func
from app.config import GUILD_ID, VERIFIED_ROLE_ID, RULES_CHANNEL_ID, EVENTS_CHANNEL_ID, ADMIN_IDS, STAFF_REPORT_CHANNEL_ID, EVENT_PUBLISHING_ENABLED, STAFF_REPORTS_ENABLED
from app.db import Session, Member, Event, Registration, init_db, now
from app.services import member, sync_member_identity, touch, rsvp, inactive_members, event_announcement
from app.activity import report, report_text, classify

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.message_content = False
intents.voice_states = True

class RulesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label='I Agree', style=discord.ButtonStyle.success, custom_id='community:rules:agree')
    async def agree(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or interaction.guild.id != GUILD_ID or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message('This button only works inside the server.', ephemeral=True)
        role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        if role is None:
            return await interaction.response.send_message('Verified role is not configured.', ephemeral=True)

        already_verified = role in interaction.user.roles

        try:
            if not already_verified:
                await interaction.user.add_roles(
                    role,
                    reason='Accepted community rules'
                )
        except discord.Forbidden:
            return await interaction.response.send_message(
                'I cannot assign that role. Please contact an administrator.',
                ephemeral=True
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                'Discord could not complete verification. Please try again.',
                ephemeral=True
            )
        try:
            with Session() as db:
                m = member(db, interaction.user.id)
                if m.verified_at is None:
                    m.verified_at = now()
                db.commit()
        except Exception:
            logging.exception(
                'Failed to save verification for member %s',
                interaction.user.id
            )
            return await interaction.response.send_message(
                'Your Discord role was verified, but the database '
                'could not be updated. Please try again or contact an administrator.',
                ephemeral=True
            )
        await interaction.response.send_message('Thanks! You are now verified.', ephemeral=True)

class RSVPView(discord.ui.View):
    def __init__(self, event_id: int):
        super().__init__(timeout=None)
        self.event_id = event_id
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.custom_id = f'community:event:{event_id}:{"yes" if item.label == "Register" else "no"}'
    @discord.ui.button(label='Register', style=discord.ButtonStyle.success, custom_id='community:event:placeholder:yes')
    async def register(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.respond(interaction, True)
    @discord.ui.button(label='Cancel RSVP', style=discord.ButtonStyle.secondary, custom_id='community:event:placeholder:no')
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.respond(interaction, False)
    async def respond(self, interaction, attending):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild or interaction.guild.id != GUILD_ID:
            return await interaction.response.send_message('You must be a member of this Discord server.', ephemeral=True)
        verified = any(role.id == VERIFIED_ROLE_ID for role in interaction.user.roles)
        with Session() as db:
            message = rsvp(db, self.event_id, interaction.user.id, verified, attending)
        await interaction.response.send_message(message, ephemeral=True)
        if message in ('You are registered!', 'Your registration has been cancelled.'):
            await refresh_event_message(self.event_id)

class CommunityBot(commands.Bot):
    async def setup_hook(self):
        # Schema must already exist (run Alembic migrations before startup).
        self.add_view(RulesView())
        with Session() as db:
            events = db.scalars(select(Event).where(Event.discord_message_id.is_not(None))).all()
            for e in events:
                self.add_view(RSVPView(e.id), message_id=e.discord_message_id)
        if GUILD_ID:
            await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        if EVENT_PUBLISHING_ENABLED and not publish_events.is_running():
            publish_events.start()
        if STAFF_REPORTS_ENABLED and not weekly_report.is_running():
            weekly_report.start()

bot = CommunityBot(command_prefix=commands.when_mentioned, intents=intents)

def authorized(interaction: discord.Interaction) -> bool:
    return bool(interaction.guild and interaction.guild.id == GUILD_ID and interaction.user.id in ADMIN_IDS)

@bot.tree.command(name='post-rules', description='Post persistent rules agreement button', guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
async def post_rules(interaction: discord.Interaction):
    if not authorized(interaction):
        return await interaction.response.send_message('Not authorized.', ephemeral=True)
    channel = bot.get_channel(RULES_CHANNEL_ID)
    if not isinstance(channel, discord.TextChannel):
        return await interaction.response.send_message('Rules channel not configured.', ephemeral=True)
    await channel.send('Please read the server rules and click **I Agree** to access the community.', view=RulesView())
    await interaction.response.send_message('Rules message posted.', ephemeral=True)

@bot.tree.command(name='inactive', description='Review inactive members (observed activity only)', guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
async def inactive(interaction: discord.Interaction):
    if not authorized(interaction):
        return await interaction.response.send_message('Not authorized.', ephemeral=True)
    with Session() as db:
        ids = [m.discord_id for m in inactive_members(db)]
    msg = f'{len(ids)} potentially inactive members (manual review required). IDs: ' + ', '.join(map(str, ids[:15]))
    await interaction.response.send_message(msg[:1900], ephemeral=True)

@bot.tree.command(name='exempt', description='Exempt or unexempt a member from inactivity review', guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
async def exempt(interaction: discord.Interaction, user: discord.Member, enabled: bool):
    if not authorized(interaction):
        return await interaction.response.send_message('Not authorized.', ephemeral=True)
    with Session() as db:
        m = member(db, user.id)
        m.exempt = enabled
        db.commit()
    await interaction.response.send_message(f'Exemption for {user.display_name}: {enabled}', ephemeral=True)

@bot.event
async def on_member_join(m):
    if m.guild.id != GUILD_ID: return
    with Session() as db:
        record = sync_member_identity(db, m)
        record.joined_at = m.joined_at
        db.commit()

@bot.event
async def on_member_update(before, after):
    if after.guild.id != GUILD_ID:
        return
    with Session() as db:
        sync_member_identity(db, after)
        db.commit()

@bot.event
async def on_user_update(before, after):
    guild = bot.get_guild(GUILD_ID)
    guild_member = guild.get_member(after.id) if guild else None
    if guild_member is None:
        return
    with Session() as db:
        record = sync_member_identity(db, guild_member)
        record.discord_username = after.name
        record.server_display_name = guild_member.nick or after.global_name or after.name
        db.commit()

@bot.event
async def on_message(message):
    if message.guild and message.guild.id == GUILD_ID and not message.author.bot:
        with Session() as db: touch(db, message.author.id)

@bot.event
async def on_reaction_add(reaction, user):
    if reaction.message.guild and reaction.message.guild.id == GUILD_ID and not user.bot:
        with Session() as db: touch(db, user.id)

@bot.event
async def on_voice_state_update(m, before, after):
    if m.guild.id == GUILD_ID and before.channel != after.channel:
        with Session() as db: touch(db, m.id)

@bot.event
async def on_presence_update(before, after):
    if after.guild.id == GUILD_ID and after.status != discord.Status.offline:
        with Session() as db: touch(db, after.id, 'last_observed_online')

@bot.event
async def on_ready():
    logging.info('Bot logged in as %s', bot.user)
    guild = bot.get_guild(GUILD_ID)
    if guild:
        with Session() as db:
            for m in guild.members:
                record = sync_member_identity(db, m)
                if record.joined_at is None: record.joined_at = m.joined_at
                if record.verified_at is None and any(r.id == VERIFIED_ROLE_ID for r in m.roles):
                    record.verified_at = now()
                if m.status != discord.Status.offline:
                    record.last_observed_online = now()
            db.commit()



async def refresh_event_message(event_id: int):
    with Session() as db:
        e = db.get(Event, event_id)
        if e is None or not e.discord_message_id or not e.discord_channel_id:
            return
        channel_id, message_id = e.discord_channel_id, e.discord_message_id
        published = e.published
        content = event_announcement(e, db.scalar(select(func.count()).select_from(Registration).where(
            Registration.event_id == e.id, Registration.status == 'going')) or 0)
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return
    try:
        message = await channel.fetch_message(message_id)
        if published:
            if message.content != content:
                await message.edit(content=content, view=RSVPView(event_id))
        else:
            await message.delete()
    except discord.NotFound:
        pass
    except discord.HTTPException:
        logging.exception('Failed to reconcile Discord event %s', event_id)
        return
    if not published:
        with Session.begin() as db:
            e = db.get(Event, event_id)
            if e and not e.published and e.discord_message_id == message_id:
                e.discord_message_id = None
                e.discord_channel_id = None


@tasks.loop(seconds=30)
async def publish_events():
    channel = bot.get_channel(EVENTS_CHANNEL_ID)
    if not isinstance(channel, discord.TextChannel):
        return
    with Session() as db:
        ids = db.scalars(select(Event.id)).all()
    for event_id in ids:
        with Session() as db:
            e = db.get(Event, event_id)
            if e.published and e.discord_message_id is None:
                count = db.scalar(select(func.count()).select_from(Registration).where(
                    Registration.event_id == e.id, Registration.status == 'going')) or 0
                try:
                    message = await channel.send(event_announcement(e, count), view=RSVPView(e.id))
                    e.discord_message_id = message.id
                    e.discord_channel_id = channel.id
                    db.commit()
                except discord.HTTPException:
                    logging.exception('Could not publish event %s', e.id)
                continue
        await refresh_event_message(event_id)

@publish_events.before_loop
async def before_publish():
    await bot.wait_until_ready()

@tasks.loop(hours=168)
async def weekly_report():
    channel = bot.get_channel(STAFF_REPORT_CHANNEL_ID)
    if not isinstance(channel, discord.TextChannel):
        logging.warning('No private staff report channel configured; weekly report not sent')
        return
    with Session() as db:
        _, totals = report(db)
    try:
        await channel.send(report_text(totals))
    except discord.HTTPException:
        logging.exception('Could not send weekly report')

@bot.tree.command(name='activity', description='Review observed activity for one member', guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
async def activity(interaction: discord.Interaction, user: discord.Member):
    if not authorized(interaction):
        return await interaction.response.send_message('Not authorized.', ephemeral=True)
    with Session() as db:
        m = db.get(Member, user.id)
        row = classify(m) if m else None
    if not row:
        return await interaction.response.send_message('No observations for this member.', ephemeral=True)
    def stamp(value):
        return value.strftime('%Y-%m-%d %H:%M UTC') if value else 'Not observed'
    await interaction.response.send_message(
        f"{user.display_name} — {row['status']}\nServer activity: {stamp(row['last_server_activity'])}\n"
        f"Online observed: {stamp(row['last_observed_online'])}\nJoined: {stamp(row['joined_at'])}", ephemeral=True)

@bot.tree.command(name='activity-summary', description='Summarize observed activity statuses', guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
async def activity_summary(interaction: discord.Interaction):
    if not authorized(interaction):
        return await interaction.response.send_message('Not authorized.', ephemeral=True)
    with Session() as db:
        _, totals = report(db)
    await interaction.response.send_message(report_text(totals), ephemeral=True)

@weekly_report.before_loop
async def before_report():
    await bot.wait_until_ready()

from bot.shows import register_shows
register_shows(bot)

if __name__ == '__main__':
    token = os.getenv('DISCORD_BOT_TOKEN', '')
    if not token or not GUILD_ID or not VERIFIED_ROLE_ID:
        raise RuntimeError('Configure DISCORD_BOT_TOKEN, DISCORD_GUILD_ID, VERIFIED_ROLE_ID in .env')
    bot.run(token)
