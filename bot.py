import _thread
import copy
import datetime
import importlib
import json
import logging
import os
import sys
import threading
import time
import traceback
import urllib.parse
import zlib
from collections import defaultdict
from subprocess import run

import requests
import websocket

import command
import config
import log

if config.bot.user_audit_log:
    import user_audit_log

from timer import readable_rel

class Bot:
    def __init__(self, commands):
        self.ws = None
        self.rs = requests.Session()
        self.rs.headers['Authorization'] = 'Bot ' + config.bot.token
        self.rs.headers['User-Agent'] = 'DiscordBot (https://github.com/lgbtqia-portugal/sbot 0.0)'
        self.heartbeat_thread = None
        self.timer_thread = None
        self.timer_condvar = threading.Condition()
        self.currency_thread = None
        self.currency_condvar = threading.Condition()
        self.channel_cleanup_thread = None
        self.channel_cleanup_condvar = threading.Condition()
        self.user_id = None
        self.seq = None
        self.guilds = {} # guild id -> Guild
        self.channels = {} # channel id -> guild id


        self.handlers = {
            OP.HELLO: self.handle_hello,
            OP.DISPATCH: self.handle_dispatch,
        }
        self.events = {
            'READY': self.handle_ready,
            'MESSAGE_CREATE': self.handle_message_create,
            'MESSAGE_DELETE': self.handle_message_delete,
            'MESSAGE_UPDATE': self.handle_message_update,
            'MESSAGE_DELETE_BULK': self.handle_message_delete_bulk,
            'INTERACTION_CREATE': self.handle_interaction_create,
            # 'MESSAGE_REACTION_ADD': self.handle_reaction_add,
            # 'MESSAGE_REACTION_REMOVE': self.handle_reaction_remove,
            'THREAD_CREATE': self.handle_forum_thread,
            'GUILD_CREATE': self.handle_guild_create,
            'GUILD_ROLE_CREATE': self.handle_guild_role_create,
            'GUILD_ROLE_UPDATE': self.handle_guild_role_update,
            'GUILD_ROLE_DELETE': self.handle_guild_role_delete,
            'GUILD_AUDIT_LOG_ENTRY_CREATE': self.handle_audit_log_entry_create,
        }
        self.commands = commands

        if config.bot.autoreload:
            self.mtimes = {}
            self.modules = defaultdict(list)
            for trigger, handler in commands.items():
                module_name = handler.__module__
                module = sys.modules[module_name]
                path = module.__file__
                if module_name not in self.mtimes:
                    self.mtimes[module_name] = os.stat(path).st_mtime
                self.modules[module_name].append(trigger)

    def connect(self):
        if config.state.gateway_url is None:
            data = self.get('/gateway/bot')
            config.state.gateway_url = data['url']
            config.state.save()

        url = config.state.gateway_url + '?v=9&encoding=json'
        self.ws = websocket.create_connection(url)

    def run_forever(self):
        self.currency_thread = _thread.start_new_thread(self.generic_recurring_loop, \
            (self.currency_update, self.currency_condvar, 'next_cur_update', 7*24))
        self.channel_cleanup_thread_thread = _thread.start_new_thread(self.generic_recurring_loop, \
            (self.channel_cleanup, self.channel_cleanup_condvar, 'next_channel_cleanup', 1*24))
        user_audit_log.setup()
        while True:
            raw_data = self.ws.recv()
            # one might think that after sending "compress": true, we can expect to only receive
            # compressed data. one would be underestimating discord's incompetence
            if isinstance(raw_data, bytes):
                raw_data = zlib.decompress(raw_data).decode('utf-8')
            if not raw_data:
                break
            if config.bot.debug:
                print('<-', raw_data)
            data = json.loads(raw_data)
            self.seq = data['s']
            if config.bot.user_audit_log and data['t'] in config.bot.user_audit_log['events'] \
                and data['d']['channel_id'] not in config.bot.user_audit_log['ignored_channels']:
                logging.info(json.dumps(data))
            handler = self.handlers.get(data['op'])
            if handler:
                try:
                    handler(data['t'], data['d'])
                except Exception:
                    tb = traceback.format_exc()
                    log.write(data)
                    log.write(tb)
                    if config.bot.err_channel:
                        try:
                            # messages can be up to 2000 characters
                            self.send_message(config.bot.err_channel,
                                    '```\n%s\n```\n```\n%s\n```' % (raw_data[:800], tb[:1000]))
                        except Exception:
                            log.write('error sending to err_channel:\n' + traceback.format_exc())
            log.flush()

    def get(self, path, params=None):
        response = self.rs.get('https://discord.com/api' + path, params=params)
        # https://discord.com/developers/docs/topics/rate-limits#header-format
        if response.headers.get('X-RateLimit-Remaining') == '0':
            wait_time = int(response.headers['X-RateLimit-Reset-After'])
            log.write('waiting %d for rate limit' % wait_time)
            time.sleep(wait_time)
        response.raise_for_status()
        return response.json()

    def post(self, path, data, files=None, method='POST'):
        if config.bot.debug:
            print('=>', path, data)
        response = self.rs.request(method, 'https://discord.com/api' + path, files=files, json=data)
        if response.headers.get('X-RateLimit-Remaining') == '0':
            wait_time = int(response.headers['X-RateLimit-Reset-After'])
            log.write(f"waiting {wait_time} for rate limit bucket reset")
            time.sleep(wait_time)
        if response.status_code >= 400:
            log.write(f"response: {response.content}")
        if response.status_code == 429: # retry when explicitly ratelimited
            self.post(path, data, files, method)
        else:
            response.raise_for_status()
            log.write(f"response: {response.content}")
        if response.status_code == 429: # retry when explicitly ratelimited
            self.post(path, data, files, method)
        else:
            response.raise_for_status()
        if response.status_code != 204: # No Content
            return response.json()
        return None

    def send(self, op, d):
        raw_data = json.dumps({'op': op, 'd': d})
        if config.bot.debug:
            print('->', raw_data)
        self.ws.send(raw_data)

    def send_message(self, channel_id, text: str, embed=None, files=None):
        if files is None:
            data = {'content': text}
            if embed is not None:
                if isinstance(embed, list):
                    data['embeds'] = embed
                else:
                    data['embed'] = embed
            self.post('/channels/%s/messages' % channel_id, data)
        else:
            assert text is None
            self.post('/channels/%s/messages' % channel_id, None, files)

    def get_message(self, channel_id, message_id):
        return self.get('/channels/%s/messages/%s' % (channel_id, message_id))

    def iter_messages(self, channel_id, after, last):
        path = '/channels/%s/messages' % (channel_id)
        params = {'after': after}
        while True:
            messages = self.get(path, params)
            messages.sort(key=lambda m: m['id'])
            for message in messages:
                yield message
                if message['id'] >= last:
                    return
            params['after'] = message['id']
            time.sleep(2)

    def get_channel_messages(self, channel_id, backlog_limit=1000):
        rslimit = 100
        messages = self.get(f"/channels/{channel_id}/messages", \
                    {'limit': rslimit})
        rslen = len(messages)
        while rslen == rslimit and len(messages) < backlog_limit:
            rs = self.get(f"/channels/{channel_id}/messages", \
                    {'limit': rslimit, 'before': messages[-1]['id']})
            rslen = len(rs)
            messages += rs
        return messages

    def delete_messages(self, channel_id, message_ids):
        if len(message_ids) == 1:
            path = '/channels/%s/messages/%s' % (channel_id, message_ids[0])
            self.post(path, None, method='DELETE')
        else:
            path = '/channels/%s/messages/bulk-delete' % channel_id
            for i in range(0, len(message_ids), 100):
                try:
                    self.post(path, {'messages': message_ids[i:i+100]})
                except requests.exceptions.HTTPError as e:
                    if e.response.json()['code'] == 50034:
                    #50034 - A message provided was too old to bulk delete
                        for msg in message_ids[i:i+100]:
                            self.delete_messages(channel_id, [msg])
                            time.sleep(1)
                    else:
                        raise e

    def react(self, channel_id, message_id, emoji):
        path = '/channels/%s/messages/%s/reactions/%s/@me' % (
                channel_id, message_id, urllib.parse.quote(emoji))
        self.post(path, None, method='PUT')


    def remove_reaction(self, channel_id, message_id, emoji):
        path = '/channels/%s/messages/%s/reactions/%s/@me' % (
                channel_id, message_id, urllib.parse.quote(emoji))
        self.post(path, None, method='DELETE')

    def get_reactions(self, channel_id, message_id, emoji):
        return self.get('/channels/%s/messages/%s/reactions/%s' % (channel_id, message_id, emoji))

    def ban(self, guild_id, user_id):
        self.post('/guilds/%s/bans/%s' % (guild_id, user_id), {}, method='PUT')

    def handle_hello(self, _, d):
        log.write('connected to %s' % d['_trace'])
        self.heartbeat_thread = _thread.start_new_thread(self.heartbeat_loop, (d['heartbeat_interval'],))
        self.send(OP.IDENTIFY, {
            'token': config.bot.token,
            'intents': INTENT.GUILDS | INTENT.GUILD_MESSAGES | INTENT.GUILD_MESSAGE_REACTIONS \
                | INTENT.DIRECT_MESSAGES | INTENT.GUILD_MODERATION,
            'properties': {
                '$browser': 'github.com/lgbtqia-portugal/sbot',
                '$device': 'github.com/lgbtqia-portugal/sbot',
            },
            'compress': True,
            'large_threshold': 50,
            'shard': [0, 1],
        })

    def handle_dispatch(self, event, d):
        handler = self.events.get(event)
        if handler:
            handler(d)

    def handle_ready(self, d):
        log.write('connected as ' + d['user']['username'])
        self.user_id = d['user']['id']
        self.timer_thread = _thread.start_new_thread(self.timer_loop, ())

    def handle_message_create(self, d):
        if d['author'].get('bot'):
            return
        content = d['content']
        if not content.startswith(config.bot.prefix_char):
            return

        lines = content[1:].split('\n', 1)
        split = lines[0].split(' ', 1)
        handler = self.commands.get(split[0])
        if handler:
            if config.bot.autoreload:
                handler = self._autoreload(split[0], handler)

            arg = ''
            if len(split) == 2:
                arg = split[1]
            if len(lines) == 2:
                arg += '\n' + lines[1]
            cmd = CommandEvent(d, arg, self)
            cmd.sender['pretty_name'] = cmd.d['member']['nick'] or \
                                        cmd.sender['global_name'] or \
                                        cmd.sender['username']
            handler(cmd)

    def handle_message_update(self, d): # TODO wrap audit log operations in its own function for readability
        if not config.bot.user_audit_log or d['channel_id'] in config.bot.user_audit_log['ignored_channels']:
            return
        if len(d['embeds'])>0 and d['embeds'][0]['type'] not in ['link', 'article']:
            return
        if 'author' in d and 'bot' in d['author'] and d['author']['bot']: # ignore bot dynamic message edits
            return
        messages = user_audit_log.search(d['id'])
        if messages:
            new_message = messages[0]['d']
            if 'content' not in messages[1]['d']:
                old_message = messages[2]['d']
            else:
                old_message = messages[1]['d']
            embed_rm_msg = ""
            if len(old_message['embeds']) > 0 and len(new_message['embeds']) == 0:
                embed_rm_msg = "`[embeds removed]`"
            if 'content' not in messages[0]['d']: #embed triggered message updates dont have content
                return
            embed = {
                "type": "rich",
                "title": f"Message edited in <#{d['channel_id']}>",
                "description": f"### Before:\n{old_message['content']}\n### After:  {embed_rm_msg}\n{new_message['content']}",
                "color": 0xffce2d,
                "fields": [
                    {
                    "name": "\u200B",
                    "value": f"Message ID: `{d['id']}`"
                    },
                ],
                "timestamp": f"{datetime.datetime.utcnow().isoformat()}",
                "author": {
                    "name": f"{d['author']['username']}",
                    "icon_url": f"https://cdn.discordapp.com/avatars/{d['author']['id']}/{d['author']['avatar']}.png?size=128"
                },
                "footer": {
                    "text": f"Account ID: {d['author']['id']}"
                },
                "url": f"https://discord.com/channels/{d['guild_id']}/{d['channel_id']}/{d['id']}"
            }
            self.send_message(config.bot.user_audit_log['channel'], '', embed=embed)
        return

    def handle_message_delete(self, d): # TODO wrap audit log operations in its own function for readability
        if not config.bot.user_audit_log or d['channel_id'] in config.bot.user_audit_log['ignored_channels']:
            return
        messages = user_audit_log.search(d['id'])
        reply = ""
        if messages:
            if 'content' not in messages[1]['d']: # embed edits dont have content, get content from older log
                old_message = messages[2]['d']
            else:
                old_message = messages[1]['d']
            if 'author' in old_message \
                    and 'bot' in old_message['author'] \
                    and old_message['author']['bot']: # ignore bot dynamic message edits
                return
            if 'attachments' in old_message and old_message['attachments']:
                filenames = []
                urls = []
                for att in old_message['attachments']:
                    filenames.append(att['filename'])
                    urls.append(att['url'])
                reply = "**Attachments:**\n"
                reply += "\n".join(urls)

            embed = {
                "type": "rich",
                "title": f"Message deleted in <#{d['channel_id']}>",
                "description": f"{old_message['content']}",
                "color": 0xf71414,
                "fields": [
                    {
                    "name": "\u200B",
                    "value": f"Message ID: `{d['id']}`"
                    },
                ],
                "timestamp": f"{datetime.datetime.utcnow().isoformat()}",
                "author": {
                    "name": f"{old_message['author']['username']}",
                    "icon_url": f"https://cdn.discordapp.com/avatars/{old_message['author']['id']}/{old_message['author']['avatar']}.png?size=128"
                },
                "footer": {
                    "text": f"Account ID: {old_message['author']['id']}"
                },
            }
            self.send_message(config.bot.user_audit_log['channel'], reply, embed=embed)
        return

    def handle_message_delete_bulk(self, d): # TODO wrap audit log operations in its own function for readability
        if not config.bot.user_audit_log or d['channel_id'] in config.bot.user_audit_log['ignored_channels']:
            return
        embed = {
            "type": "rich",
            "title": f"Bulk message delete in <#{d['channel_id']}>",
            "description": f"`{len(d['ids'])}` messages were deleted",
            "color": 0xa60063,
            "timestamp": f"{datetime.datetime.utcnow().isoformat()}",
        }
        self.send_message(config.bot.user_audit_log['channel'], '', embed=embed)

    def handle_interaction_create(self, d):
        if d.get('member', {}).get('user', {}).get('bot'):
            return

        handler = self.commands.get(d['data']['name'])
        if handler:
            if config.bot.autoreload:
                handler = self._autoreload(d['data']['name'], handler)

            path = '/interactions/%s/%s/callback' % (d['id'], d['token'])
            self.post(path, {'type': INTERACTION.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE})

            cmd = InteractionEvent(d, self)
            try:
                handler(cmd)
            except Exception:
                cmd.reply('an error occurred')
                raise

    def handle_audit_log_entry_create(self, d):
        if d['action_type'] == 25:
            self.handle_member_role_update(d)
        return

    def handle_member_role_update(self, d):
        if d['changes'][0]['key'] == '$add' and d['changes'][0]['new_value'][0]['id'] == config.bot.verify["role"]:
            self.send_message(config.bot.babies_greet['greet_channel'], \
                f'<@{d["target_id"]}> bem-vinde ao servidor <:emoji:{config.bot.babies_greet["greet_emoji"]}> ' \
                    f'passa pelos <#{config.bot.babies_greet["roles_channel"]}> por favor :>')
        return


    def _autoreload(self, command_name, handler):
        module_name = handler.__module__
        module = sys.modules[module_name]
        path = module.__file__
        new_mtime = os.stat(path).st_mtime
        if new_mtime > self.mtimes[module_name]:
            importlib.reload(module)
            self.mtimes[module_name] = new_mtime
            for trigger in self.modules[module_name]:
                handler_name = self.commands[trigger].__name__
                self.commands[trigger] = getattr(module, handler_name)
                if trigger == command_name:
                    handler = self.commands[trigger]
                    # continue replacing all the commands in the reloaded file; do not break/return
        return handler

    def handle_forum_thread(self, d):
        if config.bot.forum_react is None:
            return

        if d['parent_id'] not in config.bot.forum_react.keys():
            return
        time.sleep(1)
        for emoji in config.bot.forum_react[d['parent_id']]:
            self.react(d['id'], d['id'], emoji)


    def handle_reaction_add(self, d):
        if config.bot.forum_react is None:
            return

        if d['channel_id'] not in config.bot.forum_react.keys():
            return

        #message = self.get_message(d['channel_id'], d['message_id'])
        self.react(d['channel_id'], d['message_id'], '✅')

    def handle_reaction_remove(self, d):
        if config.bot.forum_react is None:
            return

        if d['channel_id'] not in config.bot.forum_react.keys():
            return

        self.remove_reaction(d['channel_id'], d['message_id'], '✅')

    def handle_guild_create(self, d):
        log.write('in guild %s (%d members)' % (d['name'], d['member_count']))
        self.guilds[d['id']] = Guild(d)
        for channel in d['channels']:
            self.channels[channel['id']] = d['id']

    def handle_guild_role_create(self, d):
        role = d['role']
        self.guilds[d['guild_id']].roles[role['name']] = role

    def handle_guild_role_update(self, d):
        role = d['role']
        if self._del_role(d['guild_id'], role['id']):
            self.guilds[d['guild_id']].roles[role['name']] = role
        else:
            log.write("couldn't find role for deletion: %r" % d)

    def handle_guild_role_delete(self, d):
        if not self._del_role(d['guild_id'], d['role_id']):
            log.write("couldn't find role for deletion: %r" % d)

    def _del_role(self, guild_id, role_id):
        roles = self.guilds[guild_id].roles
        for role in roles.values():
            if role['id'] == role_id:
                del roles[role['name']]
                return True
        return False

    def heartbeat_loop(self, interval_ms):
        interval_s = interval_ms / 1000
        while True:
            time.sleep(interval_s)
            self.send(OP.HEARTBEAT, self.seq)

    def timer_loop(self):
        while True:
            wakeups = []
            now = datetime.datetime.now(datetime.timezone.utc)
            hour_from_now = now + datetime.timedelta(hours=1)
            for channel_id, timers in config.state.timers.items():
                for name, dt in copy.copy(timers).items():
                    if dt <= now:
                        self.send_message(channel_id, 'removing expired timer "%s" for %s' %
                                (name, dt.strftime('%Y-%m-%d %H:%M:%S')))
                        del timers[name]
                        config.state.save()
                    elif dt <= hour_from_now:
                        self.send_message(channel_id, '%s until %s' % (readable_rel(dt - now), name))
                        wakeups.append(dt)
                    else:
                        wakeups.append(dt - datetime.timedelta(hours=1))
            wakeup = None
            if wakeups:
                wakeups.sort()
                wakeup = (wakeups[0] - now).total_seconds()
            with self.timer_condvar:
                self.timer_condvar.wait(wakeup)

    def currency_update(self):
        run(['units_cur'], check=True)
        log.write('completed units currency update')

    def channel_cleanup(self):
        if config.bot.cleanup_channels is None:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        for channel in config.bot.cleanup_channels.keys():
            msg_del = []
            msg_max_age = config.bot.cleanup_channels[channel]
            messages = self.get_channel_messages(channel)
            for msg in messages:
                if not msg['pinned'] and \
                    now - datetime.datetime.fromisoformat(msg['timestamp']) > datetime.timedelta(hours=msg_max_age):
                    msg_del.append(msg['id'])
            if msg_del:
                log.write(f"deleting {len(msg_del)} messages in <#{channel}>")
                self.delete_messages(channel, msg_del)
                log.write(f"message deletion in <#{channel}> completed")

    def generic_recurring_loop(self, func, condvar, state_attr, interval_h):
        while True:
            state_var = getattr(config.state, state_attr)
            now = datetime.datetime.now(datetime.timezone.utc)
            if state_var is None or datetime.datetime.fromisoformat(state_var) < now:
                log.write(f"running {func.__name__}")
                setattr(config.state, state_attr, str(now + datetime.timedelta(hours=interval_h)))
                config.state.save()
                func()
            with condvar:
                if state_var:
                    condvar.wait((datetime.datetime.fromisoformat(state_var) - now).total_seconds())

class Guild:
    def __init__(self, d):
        self.roles = {} # name -> {
        #	'color': 0,
        #	'hoist': False,
        #	'id': '282441120896516096',
        #	'managed': True,
        #	'mentionable': False,
        #	'name': 'sbot',
        #	'permissions': 805637184,
        #	'position': 5,
        # }
        for role in d['roles']:
            self.roles[role['name']] = role

class CommandEvent:
    def __init__(self, d, args: str, bot: Bot):
        self.d = d
        self.channel_id = d['channel_id']
        # sender = {
        #     'username': 'raylu',
        #     'id': '109405765848088576',
        #     'discriminator': '8396',
        #     'avatar': '464d73d2ca17733636282ab58b8cc3f5',
        # }
        self.sender = d['author']
        self.args = args
        self.bot = bot

    def reply(self, message, embed=None, files=None):
        self.bot.send_message(self.channel_id, message, embed, files)

    def react(self, emoji):
        self.bot.react(self.channel_id, self.d['id'], emoji)

class InteractionEvent:
    def __init__(self, d, bot):
        self.token = d['token']
        self.channel_id = d['channel_id']
        self.sender = d['member']['user']
        self.options = d['data'].get('options', [])
        self.args = ' '.join(InteractionEvent.iter_option_values(self.options))
        self.bot = bot
        self.d = d

    def reply(self, message, embed=None):
        path = '/webhooks/%s/%s/messages/@original' % (config.bot.app_id, self.token)
        data = {'content': message}
        if embed:
            data['embeds'] = [embed]
        self.bot.post(path, data, method='PATCH')

    @classmethod
    def iter_option_values(cls, options):
        for option in options:
            if option['type'] in (command.OPTION_TYPE.SUB_COMMAND, command.OPTION_TYPE.SUB_COMMAND_GROUP):
                yield option['name']
                yield from cls.iter_option_values(option.get('options', []))
            else:
                yield str(option['value'])

class OP:
    DISPATCH              = 0
    HEARTBEAT             = 1
    IDENTIFY              = 2
    STATUS_UPDATE         = 3
    VOICE_STATE_UPDATE    = 4
    VOICE_SERVER_PING     = 5
    RESUME                = 6
    RECONNECT             = 7
    REQUEST_GUILD_MEMBERS = 8
    INVALID_SESSION       = 9
    HELLO                 = 10
    HEARTBEAT_ACK         = 11

# https://discord.com/developers/docs/topics/gateway#gateway-intents
class INTENT:
    GUILDS                    = 1 << 0
    GUILD_MEMBERS             = 1 << 1
    GUILD_MODERATION          = 1 << 2
    GUILD_EMOJIS_AND_STICKERS = 1 << 3
    GUILD_INTEGRATIONS        = 1 << 4
    GUILD_WEBHOOKS            = 1 << 5
    GUILD_INVITES             = 1 << 6
    GUILD_VOICE_STATES        = 1 << 7
    GUILD_PRESENCES           = 1 << 8
    GUILD_MESSAGES            = 1 << 9
    GUILD_MESSAGE_REACTIONS   = 1 << 10
    GUILD_MESSAGE_TYPING      = 1 << 11
    DIRECT_MESSAGES           = 1 << 12
    DIRECT_MESSAGE_REACTIONS  = 1 << 13
    DIRECT_MESSAGE_TYPING     = 1 << 14

# https://discord.com/developers/docs/interactions/slash-commands#interaction-response-object-interaction-callback-type
class INTERACTION:
    CHANNEL_MESSAGE_WITH_SOURCE          = 4
    DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5
