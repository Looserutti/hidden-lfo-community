import os
from dotenv import load_dotenv
load_dotenv()

def env_int(name: str) -> int:
    value = os.getenv(name, '').strip()
    return int(value) if value else 0

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./community.db')
GUILD_ID = env_int('DISCORD_GUILD_ID')
VERIFIED_ROLE_ID = env_int('VERIFIED_ROLE_ID')
RULES_CHANNEL_ID = env_int('RULES_CHANNEL_ID')
EVENTS_CHANNEL_ID = env_int('EVENTS_CHANNEL_ID')
ADMIN_IDS = {int(x.strip()) for x in os.getenv('ADMIN_DISCORD_IDS', '').split(',') if x.strip()}
BASE_URL = os.getenv('PUBLIC_BASE_URL', 'http://localhost:8000').rstrip('/')

DISCORD_INVITE_URL = os.getenv("DISCORD_INVITE_URL", "").strip()

STAFF_REPORT_CHANNEL_ID = env_int("STAFF_REPORT_CHANNEL_ID")

# Outbound bot jobs are opt-in, including on staging.
EVENT_PUBLISHING_ENABLED = os.getenv('EVENT_PUBLISHING_ENABLED', 'false').lower() == 'true'
STAFF_REPORTS_ENABLED = os.getenv('STAFF_REPORTS_ENABLED', 'false').lower() == 'true'

# Optional two-step onboarding; IDs remain community-specific configuration.
ONBOARDING_ENABLED = os.getenv('ONBOARDING_ENABLED', 'false').lower() == 'true'
MEMBER_ROLE_ID = env_int('MEMBER_ROLE_ID')
INTRO_CHANNEL_ID = env_int('INTRO_CHANNEL_ID')

MEMBER_EVENT_ANNOUNCEMENTS_ENABLED = os.getenv('MEMBER_EVENT_ANNOUNCEMENTS_ENABLED', 'false').lower() == 'true'
MEMBER_EVENT_ANNOUNCEMENTS_SINCE = os.getenv('MEMBER_EVENT_ANNOUNCEMENTS_SINCE', '')

# Optional first-publication notifications; configure each community's channel.
PROJECT_ANNOUNCEMENTS_CHANNEL_ID = env_int('PROJECT_ANNOUNCEMENTS_CHANNEL_ID')

# New outbound performance board and preparation notices are opt-in.
PERFORMANCE_MANAGEMENT_ENABLED = os.getenv('PERFORMANCE_MANAGEMENT_ENABLED', 'false').lower() == 'true'
