"""Verified-member /shows command. Replies are private to the requester."""
import discord
from datetime import timedelta
from discord import app_commands
from app.branding import SITE
from app.calendar_utils import calendar_time
from app.config import GUILD_ID, VERIFIED_ROLE_ID, BASE_URL
from app.db import Session, now
from app.shows import upcoming_shows

PAGE_SIZE = 8


def verified_member(interaction):
    return (interaction.guild is not None and interaction.guild.id == GUILD_ID
            and isinstance(interaction.user, discord.Member)
            and any(role.id == VERIFIED_ROLE_ID for role in interaction.user.roles))


def shows_embed(rows, page, start=None):
    pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
    zone = SITE.get('calendar_timezone', 'UTC')
    start = start or now()
    first = calendar_time(start, zone).strftime('%b %d')
    last = calendar_time(start + timedelta(days=7), zone).strftime('%b %d')
    embed = discord.Embed(title='THE NEXT 7 DAYS', url=BASE_URL + '/calendar',
                          description=f'{first} — {last} · Published concerts', colour=0xD9D9D9)
    embed.set_author(name=SITE.get('name', 'Your Community').upper() + ' / COMMUNITY CALENDAR')
    if not rows:
        embed.description = 'No published concerts are listed for the next seven days. Check the calendar again soon.'
    elif page > pages:
        embed.description = f'There are {pages} pages. Try /shows page:1.'
    else:
        for event in rows[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]:
            title = discord.utils.escape_markdown(event.title)[:250]
            start = calendar_time(event.starts_at, zone).strftime('%a, %b %d · %I:%M %p %Z')
            source = discord.utils.escape_markdown(event.source_name or '')[:180]
            link = event.external_url if len(event.external_url) <= 300 else BASE_URL + '/calendar'
            embed.add_field(name=title, value=f'{start}\n{source}\n[View listing]({link})', inline=False)
    embed.set_footer(text=f'{len(rows)} concerts · Page {min(page, pages)} of {pages} · {zone}'
                          + (' · More: /shows page:2 (or another page number)' if pages > 1 else ''))
    return embed


def calendar_link():
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label='Open community calendar', url=BASE_URL + '/calendar'))
    return view


def register_shows(bot):
    @bot.tree.command(name='shows', description='See published concerts for the next seven days',
                      guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
    @app_commands.describe(page='Page number for longer concert lists (default: 1)')
    async def shows(interaction: discord.Interaction, page: app_commands.Range[int, 1] = 1):
        if not verified_member(interaction):
            return await interaction.response.send_message(
                'This command is available to verified community members inside the server.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        start = now()
        with Session() as db:
            rows = upcoming_shows(db, start)
        await interaction.followup.send(embed=shows_embed(rows, page, start), view=calendar_link(), ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())
    return shows
