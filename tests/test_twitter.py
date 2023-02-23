import io
import unittest

import PIL.Image

from tests import mock_config

unittest.TestCase.assert_equal = unittest.TestCase.assertEqual
unittest.TestCase.assert_less_equal = unittest.TestCase.assertLessEqual

class TestTwitter(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		mock_config.set_up_class(cls, 'twitter')

	@classmethod
	def tearDownClass(cls):
		mock_config.tear_down_class(cls)

	def test_sign(self):
		params = {
			'status': 'Hello Ladies + Gentlemen, a signed OAuth request!',
			'include_entities': 'true',
			'oauth_consumer_key': 'xvz1evFS4wEEPTGEFPHBog',
			'oauth_nonce': 'kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg',
			'oauth_signature_method': 'HMAC-SHA1',
			'oauth_timestamp': '1318622958',
			'oauth_token': '370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb',
			'oauth_version': '1.0',
		}
		url = 'https://api.twitter.com/1.1/statuses/update.json'
		consumer_secret = 'kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw'
		token_secret = 'LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE'
		self.assert_equal(self.twitter.sign('POST', url, params, consumer_secret, token_secret),
				'hCtSmYh+iHYCEqBWrE7C7hYmtUk=')

		params =  {
			'oauth_consumer_key': 'xvz1evFS4wEEPTGEFPHBog',
			'oauth_nonce': '132181869514112696851604378895',
			'oauth_signature_method': 'HMAC-SHA1',
			'oauth_timestamp': '1604378895',
			'oauth_token': '370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb',
			'oauth_version': '1.0',
		}
		url = 'https://upload.twitter.com/1.1/media/upload.json'
		self.assert_equal(self.twitter.sign('POST', url, params, consumer_secret, token_secret),
				's0fC9HSsyxFWP5jCHEC+UM93avc=')

	def test_optimize_image(self):
		image = PIL.Image.new('RGB', (10000, 2))
		output = io.BytesIO()
		image.save(output, 'JPEG')

		result = self.twitter.optimize_image(output.getvalue())
		image = PIL.Image.open(io.BytesIO(result))
		self.assert_less_equal(image.width, 8192)
