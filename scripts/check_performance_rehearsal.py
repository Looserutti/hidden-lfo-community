"""Read-only checks for a dedicated Discord test configuration. Prints no secrets."""
import argparse
from pathlib import Path
from dotenv import dotenv_values

REQUIRED = ('DISCORD_BOT_TOKEN', 'DISCORD_CLIENT_ID', 'DISCORD_GUILD_ID',
            'VERIFIED_ROLE_ID', 'RULES_CHANNEL_ID', 'ADMIN_DISCORD_IDS',
            'PERFORMANCE_CHANNEL_ID', 'SESSION_SECRET', 'DATABASE_URL')
DISABLED = ('EVENT_PUBLISHING_ENABLED', 'MEMBER_EVENT_ANNOUNCEMENTS_ENABLED',
            'STAFF_REPORTS_ENABLED', 'ONBOARDING_ENABLED')


def database_path(url, directory):
    prefix = 'sqlite:///'
    if not url.startswith(prefix) or '?' in url or '#' in url or ':memory:' in url:
        return None
    path = Path(url[len(prefix):])
    return (directory / path).resolve() if not path.is_absolute() else path.resolve()


def validate(values, production, *, directory, allowed_database_root):
    issues = []
    for key in REQUIRED:
        if not str(values.get(key) or '').strip(): issues.append(f'{key}: missing')
    for key in ('DISCORD_CLIENT_ID','DISCORD_GUILD_ID','VERIFIED_ROLE_ID','RULES_CHANNEL_ID','PERFORMANCE_CHANNEL_ID'):
        value = str(values.get(key) or '')
        if value and (not value.isdigit() or int(value) <= 0): issues.append(f'{key}: must be a positive ID')
    admins = str(values.get('ADMIN_DISCORD_IDS') or '').split(',')
    if any(not x.strip().isdigit() or int(x.strip() or '0') <= 0 for x in admins):
        issues.append('ADMIN_DISCORD_IDS: supply positive Discord IDs')
    if len(str(values.get('SESSION_SECRET') or '')) < 32:
        issues.append('SESSION_SECRET: use at least 32 random characters')
    for key in ('DISCORD_BOT_TOKEN','DISCORD_CLIENT_ID','DISCORD_GUILD_ID'):
        if values.get(key) and values.get(key) == production.get(key):
            issues.append(f'{key}: must differ from the production configuration')
    for key in ('DISCORD_BOT_TOKEN','DISCORD_CLIENT_ID','DISCORD_GUILD_ID'):
        if not production.get(key): issues.append(f'Production reference is missing {key}; cannot verify separation')
    for key in DISABLED:
        if str(values.get(key) or '').lower() != 'false': issues.append(f'{key}: set false for rehearsal')
    if str(values.get('PERFORMANCE_MANAGEMENT_ENABLED') or '').lower() != 'true':
        issues.append('PERFORMANCE_MANAGEMENT_ENABLED: set true in the test configuration')
    if str(values.get('PROJECT_ANNOUNCEMENTS_CHANNEL_ID') or '') not in ('','0'):
        issues.append('PROJECT_ANNOUNCEMENTS_CHANNEL_ID: leave blank for rehearsal')
    path = database_path(str(values.get('DATABASE_URL') or ''), directory)
    allowed = allowed_database_root.resolve()
    if path is None or not path.is_relative_to(allowed):
        issues.append('DATABASE_URL: must be a file-backed SQLite database inside the rehearsal directory')
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True, type=Path)
    parser.add_argument('--production-env', required=True, type=Path)
    parser.add_argument('--database-root', required=True, type=Path)
    args = parser.parse_args()
    for file in (args.env_file, args.production_env):
        if not file.is_file(): parser.error('A required configuration file is missing')
    if args.env_file.resolve() == args.production_env.resolve():
        parser.error('Test and production configuration files must differ')
    # Do not merge inherited environment values into either explicit file.
    values = dotenv_values(args.env_file, interpolate=False)
    production = dotenv_values(args.production_env, interpolate=False)
    issues = validate(values, production, directory=Path.cwd(), allowed_database_root=args.database_root)
    if issues:
        print('Rehearsal configuration needs attention (values withheld):')
        for issue in issues: print('- ' + issue)
        return 1
    print('Rehearsal configuration passed local separation checks. No network requests were made.')
    print('Token validity, Discord permissions, and real delivery still require the test-server rehearsal.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
