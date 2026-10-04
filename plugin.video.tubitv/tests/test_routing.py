import base64
import hashlib
import hmac
import importlib
import os
import sys
import types
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit


ADDON_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ADDON_ROOT not in sys.path:
    sys.path.insert(0, ADDON_ROOT)


class Addon(object):
    def __init__(self, **values):
        self.values = values

    def getSetting(self, key):
        return self.values.get(key, '')

    def setSetting(self, key, value):
        self.values[key] = value

    def getAddonInfo(self, key):
        return {'name': 'Tubi test',
                'profile': '/tmp/tubi-routing-unit-test'}[key]


CUSTOM = {
    'route_mode': '1',
    'proxy_host': '192.0.2.10',
    'proxy_port': '8883',
    'proxy_username': 'kodi user',
    'proxy_password': 'p@ss/word',
    'relay_host': '192.0.2.10',
    'relay_port': '8893',
    'relay_signing_key': 'a' * 64,
}


from resources.lib import routing  # noqa: E402


class RoutingTest(unittest.TestCase):
    def test_direct_mode_has_no_proxy_and_does_not_wrap_media(self):
        addon = Addon(route_mode='0')
        self.assertIsNone(routing.addon_http_proxy(addon))
        self.assertEqual({}, routing.request_kwargs(addon))
        self.assertEqual('https://cdn.example/video.m3u8',
                         routing.MediaRouter(addon).route('https://cdn.example/video.m3u8'))

    def test_custom_proxy_credentials_are_url_encoded(self):
        addon = Addon(**CUSTOM)
        expected = 'http://kodi%20user:p%40ss%2Fword@192.0.2.10:8883'
        self.assertEqual(expected, routing.addon_http_proxy(addon))
        self.assertEqual({'proxies': {'http': expected, 'https': expected}},
                         routing.request_kwargs(addon))

    def test_ipv6_proxy_literal_is_bracketed(self):
        values = dict(CUSTOM, proxy_host='2001:db8::10')
        self.assertIn('@[2001:db8::10]:8883', routing.addon_http_proxy(Addon(**values)))

    def test_missing_custom_proxy_fails_closed(self):
        self.assertEqual(routing.BLOCKED_PROXY,
                         routing.addon_http_proxy(Addon(route_mode='1')))

    def test_media_url_signature_matches_relay_protocol(self):
        addon = Addon(**CUSTOM)
        target = 'https://cdn.example/master.m3u8?token=a&b=2'
        result = routing.MediaRouter(addon, now=100).route(target)
        query = parse_qs(urlsplit(result).query)
        encoded = query['u'][0]
        decoded = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode()
        self.assertEqual(target, decoded)
        payload = '%s\n%s' % (query['exp'][0], encoded)
        expected = hmac.new(CUSTOM['relay_signing_key'].encode(),
                            payload.encode('ascii'), hashlib.sha256).hexdigest()
        self.assertEqual(expected, query['sig'][0])

    def test_missing_relay_key_fails_closed(self):
        values = dict(CUSTOM, relay_signing_key='')
        self.assertEqual(routing.BLOCKED_MEDIA,
                         routing.MediaRouter(Addon(**values)).route('https://cdn.example/a.m3u8'))


sys.modules['xbmc'] = types.SimpleNamespace(
    LOGDEBUG=0, LOGINFO=1, LOGWARNING=2, log=lambda **kwargs: None)
sys.modules['xbmcvfs'] = types.SimpleNamespace(
    translatePath=lambda value: value, exists=os.path.exists, mkdirs=os.makedirs)


class ApiProxyTest(unittest.TestCase):
    def test_api_get_uses_addon_proxy(self):
        from resources.lib import tubi_api
        module = importlib.reload(tubi_api)
        response = mock.Mock()
        response.json.return_value = {'containers': []}
        with mock.patch.object(module.requests, 'get', return_value=response) as get:
            api = module.TubiApi({}, 'device-id', addon=Addon(**CUSTOM))
            self.assertEqual([], api.browseList())
        self.assertEqual(routing.request_kwargs(Addon(**CUSTOM))['proxies'],
                         get.call_args.kwargs['proxies'])

    def test_widevine_dash_is_preferred_over_equivalent_hls(self):
        from resources.lib import tubi_api
        base = {'resolution': 'VIDEO_RESOLUTION_576P',
                'codec': 'VIDEO_CODEC_H264',
                'license_server': {'hdcp_version': 'hdcp_disabled'}}
        hls = dict(base, type=tubi_api.HLS_WIDEVINE,
                   manifest={'url': 'https://cdn.example/title.m3u8'})
        dash = dict(base, type=tubi_api.DASH_WIDEVINE,
                    manifest={'url': 'https://cdn.example/title.mpd'})
        self.assertIs(dash, tubi_api.chooseResource(
            {'video_resources': [hls, dash]}))

    def test_clear_hls_still_wins_over_widevine_dash(self):
        from resources.lib import tubi_api
        clear = {'type': tubi_api.CLEAR,
                 'resolution': 'VIDEO_RESOLUTION_480P',
                 'codec': 'VIDEO_CODEC_H264',
                 'manifest': {'url': 'https://cdn.example/clear.m3u8'}}
        dash = {'type': tubi_api.DASH_WIDEVINE,
                'resolution': 'VIDEO_RESOLUTION_576P',
                'codec': 'VIDEO_CODEC_H264',
                'license_server': {'hdcp_version': 'hdcp_disabled'},
                'manifest': {'url': 'https://cdn.example/protected.mpd'}}
        self.assertIs(clear, tubi_api.chooseResource(
            {'video_resources': [dash, clear]}))


class AuthProxyTest(unittest.TestCase):
    def test_auth_post_uses_addon_proxy(self):
        from resources.lib import tubi_auth
        module = importlib.reload(tubi_auth)
        addon = Addon(**CUSTOM)
        with mock.patch.object(module.requests, 'post') as post:
            auth = module.TubiAuth(addon)
            auth._post('https://account.example.test/token', '{}')
        self.assertEqual(routing.request_kwargs(addon)['proxies'],
                         post.call_args.kwargs['proxies'])


if __name__ == '__main__':
    unittest.main()
