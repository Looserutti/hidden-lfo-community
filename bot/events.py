"""Verified-member event proposals; never publishes before staff approval."""
import logging
import discord
from app.branding import SITE
from app.calendar_utils import local_event_start, calendar_time
from app.db import Session
from app.config import GUILD_ID
from app.submissions import submit_event
from bot.shows import verified_member


class EventProposal(discord.ui.Modal, title='Submit an event for admin review'):
    def __init__(self, user_id):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.event_title = discord.ui.TextInput(label='Event title', max_length=200)
        self.date = discord.ui.TextInput(label='Event date (YYYY-MM-DD)', placeholder='2026-11-14', max_length=10)
        zone = SITE.get('calendar_timezone', 'UTC').split('/')[-1].replace('_', ' ')
        self.time = discord.ui.TextInput(label=('Start time (24h) · ' + zone)[:45], placeholder='19:30', max_length=5)
        self.location = discord.ui.TextInput(label='Venue or location', max_length=250)
        self.description = discord.ui.TextInput(label='Description (optional)', style=discord.TextStyle.paragraph,
                                                required=False, max_length=4000)
        for item in (self.event_title, self.date, self.time, self.location, self.description):
            self.add_item(item)

    async def on_submit(self, interaction):
        if interaction.user.id != self.user_id or not verified_member(interaction):
            return await interaction.response.send_message('Only verified members may submit events inside the server.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            start = local_event_start(self.date.value, self.time.value, SITE.get('calendar_timezone', 'UTC'))
            with Session.begin() as db:
                proposal = submit_event(db, interaction_id=interaction.id, submitted_by=interaction.user.id,
                    submitted_name=interaction.user.display_name, title=self.event_title.value,
                    description=self.description.value, starts_at=start, location=self.location.value)
                receipt_id = proposal.id
        except ValueError as exc:
            return await interaction.followup.send(str(exc) + ' Run /event to try again.', ephemeral=True,
                                                    allowed_mentions=discord.AllowedMentions.none())
        embed = discord.Embed(title='EVENT SUBMITTED', description='An admin will review your event. It is not published yet.', colour=0xD9D9D9)
        embed.set_author(name=SITE['name'].upper())
        embed.add_field(name=discord.utils.escape_markdown(self.event_title.value)[:250],
                        value=calendar_time(start, SITE.get('calendar_timezone', 'UTC')).strftime('%a, %b %d · %I:%M %p %Z'), inline=False)
        embed.set_footer(text=f'Submission #{receipt_id} · Awaiting admin approval')
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    async def on_error(self, interaction, error):
        logging.error('Event submission failed', exc_info=(type(error), error, error.__traceback__))
        if interaction.response.is_done():
            await interaction.followup.send('Could not save your event. Please try again shortly.', ephemeral=True)
        else:
            await interaction.response.send_message('Could not save your event. Please try again shortly.', ephemeral=True)


def register_events(bot):
    @bot.tree.command(name='event', description='Submit an event for admin approval',
                      guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
    async def event(interaction: discord.Interaction):
        if not verified_member(interaction):
            return await interaction.response.send_message('Only verified members can submit events inside the server.', ephemeral=True)
        await interaction.response.send_modal(EventProposal(interaction.user.id))
    return event
