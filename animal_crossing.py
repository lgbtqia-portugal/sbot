from datetime import datetime, timezone
import sqlite3

import dateutil
import dateutil.parser
import dateutil.tz

import config
from timer import readable_rel

if config.bot.acnh_db is not None:
	db = sqlite3.connect(config.bot.acnh_db)
	db.row_factory = sqlite3.Row

	# enable foreign key constraints
	with db:
		db.execute('PRAGMA foreign_keys = ON')

time_format = '%Y-%m-%d %H:%M'

def stalk_market(cmd):
	if not cmd.args:
		cmd.reply('''Please register your friend code with '!fc set <friend-code>' before using the following commands:
- !stalks tz <tz>: will set your local timezone. See https://en.wikipedia.org/wiki/List_of_tz_database_time_zones. **This is required for the following commands.**
- !stalks sell: will list all currently available offers.
- !stalks sell <value>: will add a new offer listed at <value> bells.
- !stalks trigger <value>: will ping you if a new offer is listed above <value> bells. 
		''')
		return

	split = cmd.args.split(' ', 1)
	subcmd = split[0]
	subargs = len(split) == 2 and split[1] or ''
	if subcmd == 'tz':
		_stalk_set_timezone(cmd, subargs)
	elif subcmd == 'sell':
		_stalk_set_sell_price(cmd, subargs)
	elif subcmd == 'trigger':
		_stalks_set_sell_trigger(cmd, subargs)
	else:
		cmd.reply('Unrecognized stalks subcommand %s' % subcmd)

def _stalk_set_sell_price(cmd, price):
	if not price:
		_stalk_list_sale_prices(cmd)
		return

	user_id = cmd.sender['id']
	current_time = datetime.now(timezone.utc)
	cur = db.execute('SELECT timezone FROM user WHERE id=?', (user_id,))
	res = cur.fetchone()
	if not res:
		cmd.reply('Could not add sale price. Have you registered a friend code?')
		return
	elif res['timezone'] is None:
		cmd.reply('Could not add sale price. Please register a time zone with !stalks tz')
		return

	user_time = current_time.astimezone(dateutil.tz.gettz(res['timezone']))
	if (user_time.hour < 8 or user_time.hour >= 22):
		cmd.reply('Your shops are closed. Your current time zone is %s, where it is currently %s.' %
			(res['timezone'], user_time.strftime(time_format)))
		return
	elif user_time.weekday() == 6:
		cmd.reply('It is currently Sunday in your selected time zone, %s. Turnip offers cannot be submitted.' %
			(res['timezone']))
		return

	if user_time.hour >= 12:
		expiration = user_time.replace(hour=22, minute=0, second=0, microsecond=0)
	else:
		expiration = user_time.replace(hour=12, minute=0, second=0, microsecond=0)

	expires_in = readable_rel(expiration - user_time)

	try:
		value = int(price)
	except ValueError:
		cmd.reply('Could not parse sell value. Usage: !stalks sell 123')
		return

	with db:
		db.execute('''
		INSERT INTO sell_price VALUES (?, ?, ?, ?)
		ON CONFLICT(user_id, expiration)
		DO UPDATE SET price=excluded.price
		''', (user_id, current_time, expiration.astimezone(timezone.utc), value))

	cmd.reply('Sale price recorded at %d bells. Offer expires in %s.' %
		(value, expires_in))
	_stalk_check_sell_triggers(cmd, price, expires_in)

def _stalk_check_sell_triggers(cmd, price, expires_in):
	cur = db.execute('''
	SELECT user_id FROM sell_trigger WHERE sell_trigger.price <= ?
	''', (price,))

	triggers = [x['user_id'] for x in cur.fetchall() if x['user_id'] != cmd.sender['id']]
	if triggers:
		msg = ' '.join(['<@!%s>' % (x) for x in triggers])
		msg += (': %s has reported a sell price of %s, above your configured trigger. Their offer will expire in %s.' %
			(cmd.sender['username'], price, expires_in))
		cmd.reply(msg)

def _stalk_list_sale_prices(cmd):
	current_time = datetime.now(timezone.utc)
	cur = db.execute('''
	SELECT sell_price.rowid, username, expiration, price
	FROM sell_price
	INNER JOIN user ON sell_price.user_id = user.id
	WHERE expiration > ?
	''', (str(current_time),))

	prices = cur.fetchall()
	if not prices:
		cmd.reply('No turnip offers are currently active.')
		return

	output = []
	for row in prices:
		expires_in = readable_rel(dateutil.parser.parse(row['expiration']) - current_time)
		output.append('%s: %d (expires in %s)' % (row['username'], row['price'], expires_in))

	cmd.reply('\n'.join(output))

def _stalks_set_sell_trigger(cmd, price):
	if not price:
		cmd.reply('usage: !stalks trigger 123\nWill ping you if someone reports a sale price higher than 123.')

	try:
		with db:
			db.execute('''
			INSERT INTO sell_trigger VALUES (?, ?)
			ON CONFLICT(user_id)
			DO UPDATE SET price=excluded.price
			''', (cmd.sender['id'], price))
		cmd.reply('Trigger has been set for %s. You will be pinged if someone reports a price above this.' %
			(price))
	except sqlite3.IntegrityError:
		cmd.reply('Could not insert trigger. Have you registered a friend code?')

def _stalk_set_timezone(cmd, tz_name):
	if not tz_name:
		cmd.reply('''
		Specify a time zone from the tz database.
See https://en.wikipedia.org/wiki/List_of_tz_database_time_zones for a complete list.
		''')
		return

	tz = dateutil.tz.gettz(tz_name)

	if tz is None:
		cmd.reply('Could not find your specified timzone. See https://en.wikipedia.org/wiki/List_of_tz_database_time_zones')
		return

	cur = None
	with db:
		cur = db.execute('''
		UPDATE user SET timezone=? WHERE id=?
		''', (tz_name, cmd.sender['id']))

	if cur.rowcount:
		current_time = datetime.now().astimezone(tz)
		cmd.reply('Time zone successfully updated. Your current time should be %s.'
			% (current_time.strftime(time_format)))
	else:
		cmd.reply('Time zone could not be updated. Have you registered a friend code?')
