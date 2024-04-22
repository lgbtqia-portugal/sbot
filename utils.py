import datetime
import hashlib
import re
import struct
import subprocess
import sys
import traceback
import random
import urllib.parse

import dateutil.parser
import dateutil.tz
import requests
import websocket

import command
import config

rs = requests.Session()
rs.headers['User-Agent'] = 'sbot (github.com/lgbtqia-portugal/sbot)'

def help(cmd):
    commands = list(cmd.bot.commands.keys())
    mod_commands = []
    guild_id = cmd.bot.channels[cmd.channel_id]
    if config.bot.roles is None or guild_id != config.bot.roles['server']:
        for name, func in cmd.bot.commands.items():
            if func.__module__ in ['management', 'canned']:
                commands.remove(name)
                mod_commands.append(name)

    reply = '**commands:** ' + ', '.join(config.bot.prefix_char + cmd for cmd in commands)
    if any(r in cmd.d['member']['roles'] for r in config.bot.priv_roles):
        reply += f"\n**mod commands:** {', '.join(config.bot.prefix_char + cmd for cmd in mod_commands)}"
    cmd.reply(reply)

def botinfo(cmd):
    embed = {
        'fields': [
            {
                'name': 'source',
                'value': 'https://github.com/lgbtqia-portugal/sbot',
            },
            {
                'name': 'python',
                'value': sys.version,
            },
            {
                'name': 'websocket_client',
                'value': websocket.__version__,
            },
        ],
    }
    cmd.reply('', embed)

def ping(cmd):
    dt = datetime.datetime.fromisoformat(cmd.d['timestamp'])
    delta = datetime.datetime.now(datetime.timezone.utc) - dt
    cmd.reply('***PONG***    `%.3f ms`' % (delta.total_seconds() * 1000))

def calc(cmd):
    if not cmd.args:
        return
    response = rs.post('https://api.mathjs.org/v4/', json={'expr': cmd.args})
    if response.status_code in (200, 400):
        data = response.json()
        if data['error']:
            cmd.reply('<@!%s>: %s' % (cmd.sender['id'], data['error']))
        else:
            cmd.reply(data['result'][:1000])
    else:
        cmd.reply('<@!%s>: error calculating' % cmd.sender['id'])

def unicode(cmd):
    if not cmd.args:
        return
    unicode_cmd = ['unicode', '--max', '5', '--color', '0',
            '--format', '{pchar} U+{ordc:04X} {name} (UTF-8: {utf8})\\n', cmd.args]
    with subprocess.Popen(unicode_cmd, universal_newlines=True, stdout=subprocess.PIPE) as proc:
        output, _ = proc.communicate()
    cmd.reply(output)

temp_re = re.compile(r'\A(-?[0-9 ]*)(C|F)\Z')

@command.command('unit conversions', command.CMD_TYPE.CHAT_INPUT, {
    'type': command.OPTION_TYPE.STRING,
    'name': 'from',
    'description': 'what to convert from (74F, 1 USD)',
    'required': True,
}, {
    'type': command.OPTION_TYPE.STRING,
    'name': 'to',
    'description': 'what to convert to',
    'required': True,
})
def units(cmd):
    options = getattr(cmd, 'options', None)
    if options is not None:
        # this is an InteractionEvent (slash-command)
        split = [options[0]['value'], options[1]['value']]
    else:
        split = cmd.args.split(' in ', 1)
        if len(split) == 1:
            split = cmd.args.split(' to ', 1)

    for i, part in enumerate(split):
        match = temp_re.match(part)
        if match:
            # turn "20 C" into "tempC(20)"
            if match.group(1):
                split[i] = 'temp%s(%s)' % (match.group(2), match.group(1))
            else:
                split[i] = 'temp%s' % (match.group(2))
    units_cmd = ['units', '--compact', '--one-line', '--quiet', '--', *split]
    # in case we get in interactive mode, PIPE stdin so communicate will close it
    proc = subprocess.Popen(units_cmd, universal_newlines=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    output, _ = proc.communicate()
    if proc.wait() == 0:
        cmd.reply(output)
    else:
        cmd.reply('<@!%s>: error running `units`' % cmd.sender['id'])


@command.command('', command.CMD_TYPE.USER)
@command.command('', command.CMD_TYPE.MESSAGE)
def bonk(cmd):
    if not config.bot.bonk_emoji:
        return
    app_cmd_type = cmd.d['data']['type']
    if app_cmd_type == command.CMD_TYPE.USER:
        target = cmd.d['data']['target_id']
    elif app_cmd_type == command.CMD_TYPE.MESSAGE:
        msg_id =  cmd.d['data']['target_id']
        target = cmd.d['data']['resolved']['messages'][msg_id]['author']['id']
    else:
        return
    embed = {
        'title': 'GET BONKED',
        'image': {
            'url': random.choice(config.bot.bonk_emoji),
        }
    }
    cmd.reply(f"<@{target}>", embed=embed)

def roll(cmd):
    args = cmd.args or '1d6'
    response = rs.get('https://rolz.org/api/?' + args) # don't urlencode
    response.raise_for_status()
    split = response.text.split('\n')
    try:
        details = split[2].split('=', 1)[1].strip()
        details = details.replace(' +', ' + ').replace(' +  ', ' + ')
        result = split[1].split('=', 1)[1]
        cmd.reply(f'**Total:** `{result}`    **Rolls:** `{details}`')
    except IndexError:
        cmd.reply('%s: error rolling' % cmd.sender['pretty_name'])

tzinfos = {
    'PST':  dateutil.tz.gettz('America/Los_Angeles'),
    'PDT':  dateutil.tz.gettz('America/Los_Angeles'),
    'MST':  dateutil.tz.gettz('America/Denver'),
    'MDT':  dateutil.tz.gettz('America/Denver'),
    'CST':  dateutil.tz.gettz('America/Chicago'),
    'CDT':  dateutil.tz.gettz('America/Chicago'),
    'EST':  dateutil.tz.gettz('America/New_York'),
    'EDT':  dateutil.tz.gettz('America/New_York'),
    'WET':  dateutil.tz.gettz('Europe/Lisbon'),
    'WEST': dateutil.tz.gettz('Europe/Lisbon'),
}
def time(cmd):
    if cmd.args:
        try:
            dt = dateutil.parser.parse(cmd.args, tzinfos=tzinfos, fuzzy=True)
        except (ValueError, AttributeError) as e:
            cmd.reply(str(e))
            return
    else:
        dt = datetime.datetime.utcnow()
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    ts = int(dt.timestamp())
    cmd.reply(r'<t:%d> (<t:%d:R>) \<t:%d\>' % (ts, ts, ts))

def weather(cmd):
    if not cmd.args:
        return
    flags = ('format=**%l:**+%c+++🌡+`%t(%f)`++💦+`%h`++💨+`%w`++**☔**+`%p/3h`++**UVI:**+`%u`\n'
                    '**Time:**+`%T`++**Sunrise:**+`%S`++**Sunset:**+`%s`++**Moon:**+%m')
    location = cmd.args
    url = f'https://wttr.in/{urllib.parse.quote_plus(location.title())}?{flags}'
    try:
        response = rs.get(url)
        if response.status_code == 503:
            cmd.reply(f'{cmd.sender["pretty_name"]}: service unavailable for {location}')
            return
        if response.status_code == 404:
            cmd.reply(f'{cmd.sender["pretty_name"]}: {location} not found')
            return
        response.raise_for_status()
    except Exception:
        cmd.reply(f'{cmd.sender["pretty_name"]}: error getting weather at {url}',
                {'description': f'```{traceback.format_exc()[-500:]}```'})
        return
    cmd.reply(response.text)

def ddd(cmd):
    guild_id = cmd.d['guild_id']
    if not cmd.args:
        cmd.reply('https://ddd.raylu.net/guild/%s/' % guild_id)
        return
    user_id = cmd.args
    if guild_id == '181866934353133570':
        # https://github.com/strinking/statbot/blob/8873bb8f5e0e3ae4d475807eba522d69fd76149d/statbot/util.py#L44-L48
        hashed = hashlib.sha512(struct.pack('>q', int(user_id))).digest()
        user_id = str(struct.unpack('>q', hashed[24:32])[0])

    r = rs.get('https://ddd.raylu.net/guild/%s/by_channel.json?int_user_id=%s' %
            (guild_id, user_id))
    r.raise_for_status()
    channels = r.json()[:5]
    if not channels:
        cmd.reply('no messages found for ' + user_id)
        return
    max_len = max(len(channel['name']) for channel in channels)
    lines = []
    for channel in channels:
        name = (channel['name'] + ':').ljust(max_len + 1)
        filled = int(channel['percentage'] / 5)
        bar = '#' * filled + ' ' * (20 - filled)
        lines.append('{} {:9,d} {}'.format(name, channel['count'], bar))

    r = rs.get('https://ddd.raylu.net/guild/%s/by_user.json?int_user_id=%s' % (guild_id, user_id))
    r.raise_for_status()
    username = r.json()[0]['name']

    embed = {
        'description': '```%s```' % '\n'.join(lines),
        'author': {
            'name': username,
            'url': 'https://ddd.raylu.net/guild/%s/?int_user_id=%s' % (guild_id, user_id),
        },
    }
    cmd.reply('', embed)

def color(cmd):
    pass
