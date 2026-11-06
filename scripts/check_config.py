"""Validate deployment settings without printing credential values."""
import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import dotenv_values


def validate_config(values, production=False, bot=False):
    issues = []
    required = ['SESSION_SECRET', 'DISCORD_CLIENT_ID', 'DISCORD_CLIENT_SECRET',
                'ADMIN_DISCORD_IDS', 'PUBLIC_BASE_URL', 'DISCORD_REDIRECT_URI']
    if bot:
        required += ['DISCORD_BOT_TOKEN', 'DISCORD_GUILD_ID', 'VERIFIED_ROLE_ID', 'RULES_CHANNEL_ID']
    if bot and str(values.get('ONBOARDING_ENABLED', '')).lower() == 'true':
        required += ['MEMBER_ROLE_ID', 'INTRO_CHANNEL_ID']
        if values.get('MEMBER_ROLE_ID') == values.get('VERIFIED_ROLE_ID'):
            issues.append('MEMBER_ROLE_ID: must differ from VERIFIED_ROLE_ID')
    for key in required:
        value = (values.get(key) or '').strip()
        if not value or value.startswith(('replace-with-', 'your_')):
            issues.append(f'{key}: required value is missing or a placeholder')
    if len(values.get('SESSION_SECRET') or '') < 32:
        issues.append('SESSION_SECRET: use at least 32 random characters')
    for key in ('DISCORD_CLIENT_ID', 'DISCORD_GUILD_ID', 'VERIFIED_ROLE_ID', 'RULES_CHANNEL_ID', 'EVENTS_CHANNEL_ID', 'STAFF_REPORT_CHANNEL_ID', 'MEMBER_ROLE_ID', 'INTRO_CHANNEL_ID'):
        value = (values.get(key) or '').strip()
        if value and (not value.isdigit() or int(value) <= 0):
            issues.append(f'{key}: must be a positive Discord ID')
    ids = [x.strip() for x in (values.get('ADMIN_DISCORD_IDS') or '').split(',') if x.strip()]
    if any(not x.isdigit() or int(x) <= 0 for x in ids):
        issues.append('ADMIN_DISCORD_IDS: use comma-separated positive Discord IDs')
    base = (values.get('PUBLIC_BASE_URL') or '').rstrip('/')
    callback = values.get('DISCORD_REDIRECT_URI') or ''
    try:
        parsed = urlsplit(base)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.path
                or parsed.query or parsed.fragment or parsed.username or parsed.password):
            issues.append('PUBLIC_BASE_URL: use an origin URL without a path, query or credentials')
        if callback != base + '/auth/callback':
            issues.append('DISCORD_REDIRECT_URI: must match PUBLIC_BASE_URL plus /auth/callback')
        if production:
            domain = (values.get('SITE_DOMAIN') or '').strip().lower()
            if (not domain or '/' in domain or ':' in domain or domain == 'localhost'
                    or domain.endswith('.example.com') or domain == 'example.com'):
                issues.append('SITE_DOMAIN: set your real staging or production hostname')
            if parsed.scheme != 'https' or parsed.netloc.lower() != domain:
                issues.append('PUBLIC_BASE_URL: production requires HTTPS and the SITE_DOMAIN hostname')
    except ValueError:
        issues.append('PUBLIC_BASE_URL: malformed URL')
    if bot:
        for flag, key in [('EVENT_PUBLISHING_ENABLED', 'EVENTS_CHANNEL_ID'), ('STAFF_REPORTS_ENABLED', 'STAFF_REPORT_CHANNEL_ID')]:
            if str(values.get(flag, '')).lower() == 'true' and not (values.get(key) or '').strip():
                issues.append(f'{key}: required when {flag} is true')
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, help='Optional dotenv file; otherwise use .env if present and the process environment')
    parser.add_argument('--production', action='store_true')
    parser.add_argument('--bot', action='store_true')
    args = parser.parse_args()
    if args.env_file is not None and not args.env_file.is_file():
        parser.error('Environment file does not exist')
    env_file = args.env_file or Path('.env')
    file_values = dotenv_values(env_file) if env_file.is_file() else {}
    values = {**file_values, **os.environ}
    issues = validate_config(values, args.production, args.bot)
    if issues:
        print('Configuration needs attention (credential values are never printed):')
        for issue in issues:
            print('- ' + issue)
        return 1
    print('Configuration checks passed. Network access, DNS, Discord permissions and Docker still require live checks.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
