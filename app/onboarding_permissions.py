"""Permission plan for two-step onboarding; no network calls or side effects."""
VIEW, SEND, HISTORY = 1 << 10, 1 << 11, 1 << 16


def plan_overwrites(channel, everyone, member_role, verified_role, bot_roles, staff_roles, kind):
    rows = {str(x['id']): dict(x) for x in channel.get('permission_overwrites', [])}
    def set_bits(role_id, allow=0, deny=0):
        key = str(role_id)
        row = rows.setdefault(key, dict(id=key, type=0, allow='0', deny='0'))
        row['allow'] = str((int(row['allow']) & ~deny) | allow)
        row['deny'] = str((int(row['deny']) & ~allow) | deny)
    if kind == 'community':
        for row in rows.values():
            if str(row['id']) not in {str(member_role), *map(str, bot_roles), *map(str, staff_roles)}:
                row['allow'] = str(int(row['allow']) & ~VIEW)
        set_bits(everyone, deny=VIEW)
        set_bits(member_role, allow=VIEW)
        # Keep the tracker and existing service bots able to operate.
        for role_id in bot_roles:
            set_bits(role_id, allow=VIEW)
    else:
        for row in rows.values():
            if str(row['id']) not in {*map(str, staff_roles), *map(str, bot_roles)}:
                row['allow'] = str(int(row['allow']) & ~SEND)
        set_bits(everyone, allow=VIEW|HISTORY, deny=SEND)
        for role_id in (verified_role, member_role):
            set_bits(role_id, allow=VIEW|HISTORY|(SEND if kind == 'banter' else 0), deny=SEND if kind == 'rules' else 0)
        for role_id in bot_roles:
            set_bits(role_id, allow=VIEW|HISTORY|SEND)
    return list(rows.values())
