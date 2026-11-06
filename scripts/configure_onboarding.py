"""Plan/apply explicit onboarding channel permissions; snapshot before changes."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import quote
import httpx
from app.config import GUILD_ID, VERIFIED_ROLE_ID, MEMBER_ROLE_ID, INTRO_CHANNEL_ID, RULES_CHANNEL_ID
from app.db import Session, Setting
from app.onboarding_permissions import plan_overwrites


async def run(args):
    policy = json.loads(args.policy.read_text())
    community = set(map(str, policy['community_channel_ids']))
    private = set(map(str, policy['private_channel_ids']))
    lobby = {str(INTRO_CHANNEL_ID): 'banter', str(RULES_CHANNEL_ID): 'rules'}
    if not GUILD_ID or not MEMBER_ROLE_ID or MEMBER_ROLE_ID == VERIFIED_ROLE_ID:
        raise ValueError('Configure distinct guild, Verified, Member and lobby IDs first')
    if community & private or (community | private) & set(lobby):
        raise ValueError('Policy channel groups must not overlap')
    async with httpx.AsyncClient(timeout=30, headers={
        'Authorization': 'Bot ' + os.environ['DISCORD_BOT_TOKEN'],
        'X-Audit-Log-Reason': quote('Two-step onboarding: rules acknowledgment then introduction')}) as client:
        async def request(method, path, **kwargs):
            for _ in range(8):
                response = await client.request(method, 'https://discord.com/api/v10' + path, **kwargs)
                if response.status_code != 429:
                    response.raise_for_status()
                    return response.json() if response.content else None
                await asyncio.sleep(float(response.json().get('retry_after', 3)) + .2)
            raise RuntimeError('Discord rate limit did not clear; saved snapshot is available')
        guild = await request('GET', f'/guilds/{GUILD_ID}')
        roles = await request('GET', f'/guilds/{GUILD_ID}/roles')
        channels = await request('GET', f'/guilds/{GUILD_ID}/channels')
        actual = {c['id'] for c in channels}
        if actual != community | private | set(lobby):
            raise ValueError('Every channel/category must be classified explicitly in the policy')
        bot_roles = [r['id'] for r in roles if r.get('tags', {}).get('bot_id')]
        staff_roles = [r['id'] for r in roles if int(r['permissions']) & 8]
        plan = []
        for channel in channels:
            if channel['id'] in private:
                continue
            kind = lobby.get(channel['id'], 'community')
            rows = plan_overwrites(channel, str(GUILD_ID), str(MEMBER_ROLE_ID), str(VERIFIED_ROLE_ID), bot_roles, staff_roles, kind)
            plan.append((channel, kind, rows))
        # Open onboarding first, then set category defaults, then each community channel.
        plan.sort(key=lambda x: (0 if x[1] != 'community' else 1 if x[0]['type'] == 4 else 2, x[0]['id']))
        args.backup.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump({'guild': guild, 'roles': roles, 'channels': channels,
                       'policy': policy, 'plan': [{'id': c['id'], 'name': c['name'], 'kind': k, 'overwrites': r} for c,k,r in plan]}, out)
        print('Snapshot saved; planned channels/categories:', len(plan), '; private untouched:', len(private), flush=True)
        for channel, kind, rows in plan:
            print(channel['name'], kind, flush=True)
        if not args.apply:
            return
        with Session() as db:
            if not db.get(Setting, 'onboarding.rules_message_id'):
                raise ValueError('Start the configured bot and confirm the rules button before applying channel gates')
        me = await request('GET', '/users/@me')
        own_roles = {r['id'] for r in roles if r.get('tags', {}).get('bot_id') == me['id']}
        for channel, kind, rows in plan:
            # Fetch again because changes to synced categories can affect child overwrites.
            current = await request('GET', '/channels/' + channel['id'])
            existing = {str(x['id']): x for x in current.get('permission_overwrites', [])}
            rows.sort(key=lambda r: (0 if r['id'] in own_roles else 1 if r['id'] == str(MEMBER_ROLE_ID) else 3 if r['id'] == str(GUILD_ID) else 2))
            for row in rows:
                previous = existing.get(str(row['id']))
                if previous and all(str(previous[k]) == str(row[k]) for k in ('type','allow','deny')):
                    continue
                await request('PUT', f"/channels/{channel['id']}/permissions/{row['id']}", json={k: row[k] for k in ('type','allow','deny')})
            print('Applied:', channel['name'], flush=True)
        print('Permission plan applied. Verify newcomer/Verified/Member views before inviting a test member.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', required=True, type=Path)
    parser.add_argument('--backup', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
