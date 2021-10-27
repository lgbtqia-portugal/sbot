import datetime
import random
import re
import subprocess
import sys
import traceback
import urllib.parse

import dateutil.parser
import requests
import websocket

import command
import config

rs = requests.Session()
rs.headers['User-Agent'] = 'sbot (github.com/raylu/sbot)'

def help(cmd):
	if cmd.args: # only reply on "!help"
		return
	commands = set(cmd.bot.commands.keys())
	guild_id = cmd.bot.channels[cmd.channel_id]
	if config.bot.roles is None or guild_id != config.bot.roles['server']:
		for name, func in cmd.bot.commands.items():
			if func.__module__ == 'management':
				commands.remove(name)
	reply = 'commands: `!%s`' % '`, `!'.join(commands)
	cmd.reply(reply)

def botinfo(cmd):
	embed = {
		'fields': [
			{
				'name': 'source',
				'value': 'https://github.com/raylu/sbot',
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
	cmd.reply('%.3f ms' % (delta.total_seconds() * 1000))

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

@command.command('unit conversions', {
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

	for i, part in enumerate(split):
		match = temp_re.match(part)
		if match:
			# turn "20 C" into "tempC(20)"
			if match.group(1):
				split[i] = 'temp%s(%s)' % (match.group(2), match.group(1))
			else:
				split[i] = 'temp%s' % (match.group(2))
	units_cmd = ['units', '--compact', '--one-line', '--quiet', '--'] + split
	# pylint: disable=consider-using-with
	# in case we get in interactive mode, PIPE stdin so communicate will close it
	proc = subprocess.Popen(units_cmd, universal_newlines=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
	output, _ = proc.communicate()
	if proc.wait() == 0:
		cmd.reply(output)
	else:
		cmd.reply('<@!%s>: error running `units`' % cmd.sender['id'])

def roll(cmd):
	args = cmd.args or '1d6'
	response = rs.get('https://rolz.org/api/?' + args) # don't urlencode
	split = response.text.split('\n')
	details = split[2].split('=', 1)[1].strip()
	details = details.replace(' +', ' + ').replace(' +  ', ' + ')
	result = split[1].split('=', 1)[1]
	cmd.reply('%s %s' % (result, details))

def time(cmd):
	if cmd.args:
		try:
			dt = dateutil.parser.parse(cmd.args)
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
	split = cmd.args.split()
	if split[0].startswith('-'):
		flags = split[0][1:]
		location = ' '.join(split[1:])
	elif split[-1].startswith('-'):
		flags = split[-1][1:]
		location = ' '.join(split[:-1])
	else:
		flags = '1Fp'
		location = cmd.args
		if location.isdecimal() and len(location) == 5:
			location += '-us'
	url = 'https://wttr.in/%s.png?%s' % (urllib.parse.quote_plus(location), flags)
	try:
		response = rs.get(url)
		response.raise_for_status()
	except Exception:
		cmd.reply('%s: error getting weather at %s' % (cmd.sender['username'], url),
				{'description': '```%s```' % traceback.format_exc()[-500:]})
		return
	cmd.reply(None, files={'weather.png': response.content})

def ohno(cmd):
	url = 'https://www.raylu.net/f/ohno/ohno%03d.png' % random.randint(1, 294)
	cmd.reply('', {'image': {'url': url}})

def ohyes(cmd):
	url = 'https://www.raylu.net/f/ohyes/ohyes%02d.gif' % random.randint(1, 19)
	cmd.reply('', {'image': {'url': url}})
