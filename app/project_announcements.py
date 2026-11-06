"""Persistent first-publication notifications, delivered by the single gateway bot."""
import json
import logging
import discord
from sqlalchemy import select
from app.db import Setting
from app import project_store


async def deliver_pending(sessions, channel, base_url):
    with sessions() as db:
        keys=list(db.scalars(select(Setting.key).where(Setting.key.like('projects.announcement.%'))))
    for key in keys:
        with sessions() as db:
            row=db.get(Setting,key)
            if not row:continue
            queued=json.loads(row.value)
            if queued.get('message_id'):continue
            post=project_store.get(db,queued['post_id'])
            if not post or not post.get('published'):continue
            published=post['published']
            title=discord.utils.escape_markdown(discord.utils.escape_mentions(published['title']))
            member=discord.utils.escape_markdown(discord.utils.escape_mentions(published.get('member','')))
            content=f'**New member highlight**\n**{title}**'
            if member:content+=f'\n{member}'
            content+=f"\n{base_url.rstrip('/')}/projects/{post['id']}"
            try:
                message=await channel.send(content,allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                logging.exception('Could not announce project %s',post['id'])
                continue
            queued.update(message_id=message.id,channel_id=channel.id)
            row.value=json.dumps(queued);db.commit()
