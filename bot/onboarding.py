"""Rules acknowledgment followed by an introduction, without reading message bodies."""
import logging
import discord
from app.config import GUILD_ID, VERIFIED_ROLE_ID, MEMBER_ROLE_ID, INTRO_CHANNEL_ID, RULES_CHANNEL_ID, ONBOARDING_ENABLED
from app.db import Session, Setting, now


def ready():
    return ONBOARDING_ENABLED and MEMBER_ROLE_ID and INTRO_CHANNEL_ID and MEMBER_ROLE_ID != VERIFIED_ROLE_ID


def instructions(member):
    if any(role.id == MEMBER_ROLE_ID for role in member.roles):
        return 'Thanks for acknowledging the rules! You already have full member access.'
    return (f'Thanks! You are verified. Next, say hello with a quick introduction in <#{INTRO_CHANNEL_ID}>. '
            'Your first normal message there unlocks the remaining community channels.')


async def welcome(member):
    if not ready() or member.bot or member.guild.id != GUILD_ID:
        return
    channel = member.guild.get_channel(INTRO_CHANNEL_ID)
    if channel:
        await channel.send(f'Welcome {member.mention}! You can read the conversation here. '
            f'First visit <#{RULES_CHANNEL_ID}> and click **I Agree** after reading the rules. '
            'Then come back here and introduce yourself. The remaining community channels open after your introduction.',
            allowed_mentions=discord.AllowedMentions(users=[member], roles=False, everyone=False))


async def introduction(message):
    if (not ready() or message.guild is None or message.guild.id != GUILD_ID
            or message.channel.id != INTRO_CHANNEL_ID or message.author.bot
            or message.type not in (discord.MessageType.default, discord.MessageType.reply)):
        return False
    member = message.author
    if any(role.id == MEMBER_ROLE_ID for role in member.roles):
        return False
    if not any(role.id == VERIFIED_ROLE_ID for role in member.roles):
        return False
    role = message.guild.get_role(MEMBER_ROLE_ID)
    if role is None:
        logging.error('Onboarding Member role is missing')
        return False
    try:
        await member.add_roles(role, reason='Introduced themselves after acknowledging rules')
    except discord.HTTPException:
        logging.exception('Could not grant Member after introduction')
        return False
    with Session.begin() as db:
        key = f'onboarding.introduction.{member.id}'
        if db.get(Setting, key) is None:
            db.add(Setting(key=key, value=now().isoformat()))
    return True


async def ensure_rules_button(bot, view):
    if not ready():
        return
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    channel = guild.get_channel(RULES_CHANNEL_ID)
    if not isinstance(channel, discord.TextChannel):
        raise RuntimeError('Rules channel is missing')
    with Session() as db:
        stored = db.get(Setting, 'onboarding.rules_message_id')
        message_id = int(stored.value) if stored else None
    if message_id:
        try:
            await channel.fetch_message(message_id)
            return
        except discord.NotFound:
            pass
    message = await channel.send('Please read the server rules above, then click **I Agree** below. '
        f'You will receive Verified and can post a quick introduction in <#{INTRO_CHANNEL_ID}>. '
        'Your introduction grants Member and unlocks the remaining community channels.', view=view,
        allowed_mentions=discord.AllowedMentions.none())
    with Session.begin() as db:
        db.merge(Setting(key='onboarding.rules_message_id', value=str(message.id)))
