import operator

import requests

import config
import log

from subprocess import CalledProcessError, run

def join(cmd):
    guild_id, role_id = _ids(cmd)
    if config.bot.roles is None or guild_id != config.bot.roles['server']:
        return
    roles = cmd.bot.guilds[guild_id].roles
    if role_id is None or cmd.args not in _allowed_role_names(roles):
        cmd.reply('no joinable role named %s' % cmd.args)
    else:
        cmd.bot.post('/guilds/%s/members/%s/roles/%s' % (guild_id, cmd.sender['id'], role_id), None,
                method='PUT')
        cmd.reply('put <@!%s> in %s' % (cmd.sender['id'], cmd.args))

def leave(cmd):
    guild_id, role_id = _ids(cmd)
    if config.bot.roles is None or guild_id != config.bot.roles['server']:
        return
    roles = cmd.bot.guilds[guild_id].roles
    if role_id is None or cmd.args not in _allowed_role_names(roles):
        cmd.reply('no joinable role named %s' % cmd.args)
    else:
        cmd.bot.post('/guilds/%s/members/%s/roles/%s' % (guild_id, cmd.sender['id'], role_id), None,
                method='DELETE')
        cmd.reply('removed <@!%s> from %s' % (cmd.sender['id'], cmd.args))

def list_roles(cmd):
    bot = cmd.bot
    guild_id = bot.channels[cmd.channel_id]
    if config.bot.roles is None or guild_id != config.bot.roles['server']:
        return

    roles = list(_allowed_roles(bot.guilds[guild_id].roles))
    roles.sort(key=operator.itemgetter('position'), reverse=True)

    desc = ' '.join('<@&%s>' % role['id'] for role in roles)
    embed = {'description': desc}
    cmd.reply('', embed)

def verify(cmd):
    if not any(r in cmd.d['member']['roles'] for r in config.bot.priv_roles):
        return
    if not cmd.args:
        return
    cmd.bot.delete_messages(cmd.channel_id, [cmd.d['id']])
    args = cmd.args.split()
    if len(args) < 1:
        cmd.bot.send_message(config.bot.err_channel, \
            f"<@{cmd.sender['id']}> usage: `{config.bot.prefix_char}verify all|USER_ID...`")
        return
    rslimit = 100
    messages = cmd.bot.get(f"/channels/{config.bot.verify['channel']}/messages", \
                {'limit': rslimit})
    rslen = len(messages)
    while rslen == rslimit:
        rs = cmd.bot.get(f"/channels/{config.bot.verify['channel']}/messages", \
                {'limit': rslimit, 'before': messages[-1]['id']})
        rslen = len(rs)
        messages += rs

    msg_del = []
    verified_users = []
    for msg in messages:
        print(msg)
        if args[0] == 'all' or msg['author']['id'] in args:
            if msg['author']['id'] not in verified_users:
                cmd.bot.post(f"/guilds/{cmd.d['guild_id']}/members/{msg['author']['id']}/roles/{config.bot.verify['role']}", \
                    None, method='PUT')  # noqa: E501
                verified_users.append(msg['author']['id'])
            if not msg['pinned']:
                msg_del.append(msg['id'])
    if msg_del:
        cmd.bot.delete_messages(config.bot.verify['channel'], msg_del)
        return
    cmd.bot.send_message(config.bot.err_channel, 'verify: no users to verify')

def cleanup(cmd):
    if not any(r in cmd.d['member']['roles'] for r in config.bot.priv_roles):
        return
    cmd.bot.delete_messages(cmd.channel_id, [cmd.d['id']])
    try:
        start, end = cmd.args.split()
        int(start)
        int(end)
    except ValueError:
        cmd.bot.send_message(config.bot.err_channel, \
            f"<@{cmd.sender['id']}> usage: `{config.bot.prefix_char}cleanup start_msg_id end_msg_id`")
        return
    messages = cmd.bot.iter_messages(cmd.channel_id, str(int(start) - 1), end)
    message_ids = [msg['id'] for msg in messages]
    cmd.bot.send_message(config.bot.err_channel, f"cleanup started by <@{cmd.sender['id']}> in <#{cmd.channel_id}>")
    if len(message_ids) > 0:
        cmd.bot.delete_messages(cmd.channel_id, message_ids)
        cmd.bot.send_message(config.bot.err_channel, 'cleanup completed')
    else:
        cmd.bot.send_message(config.bot.err_channel, f"<@{cmd.sender['id']}> cleanup: no messages in range")

def mass_ban(cmd):
    if not any(r in cmd.d['member']['roles'] for r in config.bot.priv_roles):
        return
    cmd.bot.delete_messages(cmd.channel_id, [cmd.d['id']])
    try:
        start, end = cmd.args.split()
    except ValueError:
        cmd.bot.send_message(config.bot.err_channel, \
            f"<@{cmd.sender['id']}> usage: `{config.bot.prefix_char}massban start_msg_id end_msg_id`")
        return
    try:
        cmd.bot.get_message(cmd.channel_id, start)
        cmd.bot.get_message(cmd.channel_id, end)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code != 404:
            raise
        cmd.bot.send_message(config.bot.err_channel, \
            f'could not find {start=} or {end=}')
        return
    cmd.bot.send_message(config.bot.err_channel, f"mass banning started (by <@{cmd.sender['id']}> in <#{cmd.channel_id}>)")
    msg_del = []
    for msg in cmd.bot.iter_messages(cmd.channel_id, str(int(start) - 1), end):
        user_id = msg['author']['id']
        log.write(f'banning {user_id}')
        cmd.bot.ban(cmd.d['guild_id'], user_id)
        msg_del.append(msg['id'])

    cmd.bot.delete_messages(cmd.channel_id, msg_del)
    cmd.bot.send_message(config.bot.err_channel, 'mass banning complete')

def listbots(cmd):
    if not any(r in cmd.d['member']['roles'] for r in config.bot.priv_roles):
        return
    rslimit = 1000
    members = cmd.bot.get(f"/guilds/{cmd.d['guild_id']}/members", \
                {'limit': rslimit})
    rslen = len(members)

    while rslen == rslimit:
        rs = cmd.bot.get(f"/guilds/{cmd.d['guild_id']}/members", \
                {'limit': rslimit, 'after': members[-1]['user']['id']})
        rslen = len(rs)
        members += rs

    bots = []
    for member in members:
        if 'bot' in member['user'] and member['user']['bot']:
            bots.append(f"`{member['user']['id']:<20}`   {member['user']['username']}")

    cmd.reply(f'**{len(bots)} bots found**\n' + '\n'.join(bots))

def units_update(cmd):
    if not any(r in cmd.d['member']['roles'] for r in config.bot.priv_roles):
        return
    try:
        result = run(['units_cur'], check=True, text=True, capture_output=True)
        output = result.stdout
    except CalledProcessError as e:
        output = e
    cmd.bot.send_message(config.bot.err_channel, str(output))

def _ids(cmd):
    bot = cmd.bot
    guild_id = bot.channels[cmd.channel_id]
    roles = bot.guilds[guild_id].roles
    try:
        role_id = roles[cmd.args]['id']
        return guild_id, role_id
    except KeyError:
        return guild_id, None

def _allowed_roles(roles):
    sbot_position = roles['sbot']['position']
    for role in roles.values():
        # exclude roles higher than ours, @everyone (position 0), bots, and Nitro Booster
        if 0 < role['position'] < sbot_position and role['name'] not in ['bots', 'Nitro Booster']:
            yield role

def _allowed_role_names(roles):
    for role in _allowed_roles(roles):
        yield role['name']
