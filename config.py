import yaml

import log

class YamlAttrs:
	def __init__(self, filename, defaults=None):
		self.filename = filename

		try:
			with open(filename, 'r') as f:
				doc = yaml.safe_load(f)
		except FileNotFoundError:
			doc = defaults
			log.write('creating ' + self.filename)
			self.save()

		for k, v in doc.items():
			setattr(self, k, v)

	def save(self):
		with open(self.filename, 'w') as f:
			data = dict(self.__dict__)
			del data['filename']
			yaml.dump(data, f)

	def __str__(self):
		return '%s %s' % (self.__class__, self.__dict__)

bot = YamlAttrs('config.yaml')
state = YamlAttrs('state.yaml',
	defaults={
		'gateway_url': None, 'timers': {}, 'reddit_access_token': None, 'tweet_ids': {},
		'twitter_queue': [], 'steam_news_ids': {}, 'twitch_last_times': {},
	})
