import yaml

import command
import config

can_usage = f' usage: `{config.bot.prefix_char}can list`, \
    `{config.bot.prefix_char}can set cow moo`, \
    `{config.bot.prefix_char}can cow`, \
    `{config.bot.prefix_char}can del cow`'

@command.command('canned responses', command.CMD_TYPE.CHAT_INPUT, {
    'type': command.OPTION_TYPE.SUB_COMMAND,
    'name': 'list',
    'description': 'list canned response names',
}, {
    'type': command.OPTION_TYPE.SUB_COMMAND,
    'name': 'set',
    'description': 'set a canned response',
    'options': [
        {
            'type': command.OPTION_TYPE.STRING,
            'name': 'name',
            'description': 'the name of the can',
            'required': True,
        },
        {
            'type': command.OPTION_TYPE.STRING,
            'name': 'text',
            'description': "what's in the can",
            'required': True,
        },
    ],
}, {
    'type': command.OPTION_TYPE.SUB_COMMAND,
    'name': 'del',
    'description': 'delete a canned response',
    'options': [
        {
            'type': command.OPTION_TYPE.STRING,
            'name': 'name',
            'description': 'the name of the can',
            'required': True,
        },
    ],
}, {
    'type': command.OPTION_TYPE.SUB_COMMAND,
    'name': 'get',
    'description': 'display a canned response',
    'options': [
        {
            'type': command.OPTION_TYPE.STRING,
            'name': 'name',
            'description': 'the name of the can',
            'required': True,
        },
    ],
})
def canned(cmd):
    if not any(r in cmd.d['member']['roles'] for r in config.bot.priv_roles):
        cmd.bot.send_message(config.bot.err_channel, \
            f"<@{cmd.sender['id']}>: you don't have permissions to use this command")
        return
    options = getattr(cmd, 'options', None)
    if options is not None:
        # this is an InteractionEvent (slash-command)
        subcmd = options[0]['name']
        if subcmd == 'list':
            _can_list(cmd)
        elif subcmd == 'add':
            name = options[0]['options'][0]['value']
            text = options[0]['options'][1]['value']
            _can_set(cmd, name, text)
        elif subcmd == 'del':
            name = options[0]['options'][0]['value']
            _can_del(cmd, name)
        elif subcmd == 'get':
            name = options[0]['options'][0]['value']
            _can_get(cmd, name)
        else:
            raise AssertionError('unexpected can sub-command: %r' % subcmd)
    else:
        cmd.bot.delete_messages(cmd.channel_id, [cmd.d['id']])
        if not cmd.args:
            cmd.bot.send_message(config.bot.err_channel, f"<@{cmd.sender['id']}>" + can_usage)
            return
        split = cmd.args.split(' ', 1)
        subcmd = split[0]
        if subcmd == 'list':
            _can_list(cmd)
        elif subcmd == 'set':
            try:
                name, text = split[1].split(' ', 1)
            except IndexError:
                cmd.reply('%s: missing args to `set`; %s' % (cmd.sender['pretty_name'], can_usage))
                return
            except ValueError:
                cmd.reply('%s: must specify can name and text' % cmd.sender['pretty_name'])
                return
            _can_set(cmd, name, text)
        elif subcmd == 'del':
            try:
                name = split[1]
            except IndexError:
                cmd.reply('%s: missing args to `del`; %s' % (cmd.sender['pretty_name'], can_usage))
                return
            _can_del(cmd, name)
        else:
            _can_get(cmd, subcmd)

def _can_list(cmd):
    names = _get_cans().keys()
    if names:
        embed = {'description': '\n'.join(names)}
        cmd.reply('canned responses:', embed=embed)
    else:
        cmd.reply('no canned responses')

def _can_set(cmd, name, text):
    if name in ['list', 'set', 'del']:
        cmd.reply(name + ' is a reserved word')
        return
    elif ' ' in name: # possible via InteractionEvent
        cmd.reply('can names cannot have spaces')
        return
    cans = _get_cans()
    cans[name] = text
    _set_cans(cans)
    cmd.reply(f'set canned reply; retrieve via `{config.bot.prefix_char}can {name}`')

def _can_del(cmd, name):
    cans = _get_cans()
    try:
        del cans[name]
    except KeyError:
        cmd.reply(f'no can found with name `{name}`')
        return
    _set_cans(cans)
    cmd.reply('deleted canned reply ' + name)

def _can_get(cmd, name):
    try:
        cmd.reply(_get_cans()[name])
    except KeyError:
        cmd.reply('unknown can ' + name)

_cans = None

def _get_cans():
    global _cans
    if _cans is None:
        try:
            with open('config/cans.yaml', 'r', encoding='utf-8') as f:
                _cans = yaml.safe_load(f)
        except FileNotFoundError:
            _cans = {}
    return _cans

def _set_cans(cans):
    with open('config/cans.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(cans, f)
