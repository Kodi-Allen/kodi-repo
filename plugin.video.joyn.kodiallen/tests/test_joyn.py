# -*- coding: utf-8 -*-
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import kodistub  # noqa: F401  (installs the Kodi stubs)

from resources.lib import iptv, joyn_api, lineup, regions, routing


class Settings(object):
    def __init__(self, **values):
        self.values = values

    def getSetting(self, key):
        return self.values.get(key, '')


class RoutingTest(unittest.TestCase):
    def test_regions_read_their_own_route(self):
        addon = Settings(**{'de.route_mode': '1', 'de.proxy_host': '192.0.2.20', 'de.proxy_port': '8899',
                            'ch.route_mode': '0'})
        self.assertIsNone(routing.addon_http_proxy(addon, 'at'))
        self.assertIsNone(routing.addon_http_proxy(addon, 'ch'))
        self.assertEqual('http://192.0.2.20:8899', routing.addon_http_proxy(addon, 'de'))

    def test_custom_route_without_proxy_fails_closed(self):
        addon = Settings(**{'ch.route_mode': '1'})
        self.assertEqual(routing.BLOCKED_PROXY, routing.addon_http_proxy(addon, 'ch'))
        self.assertEqual({'proxies': {'http': routing.BLOCKED_PROXY, 'https': routing.BLOCKED_PROXY}},
                         routing.request_kwargs(addon, 'ch'))

    def test_custom_media_without_relay_key_fails_closed(self):
        addon = Settings(**{'de.route_mode': '1', 'de.relay_host': '192.0.2.20'})
        router = routing.MediaRouter(addon, prefix='de')
        self.assertEqual(routing.BLOCKED_MEDIA, router.route('https://example.joyn.de/a.mpd'))

    def test_custom_media_is_signed_for_the_region_relay(self):
        addon = Settings(**{'de.route_mode': '1', 'de.relay_host': '192.0.2.20', 'de.relay_port': '34410',
                            'de.relay_signing_key': 'k' * 40})
        url = routing.MediaRouter(addon, prefix='de', now=1000).route('https://example.joyn.de/a.mpd')
        self.assertTrue(url.startswith('http://192.0.2.20:34410/v1/relay?u='))
        # Another region in direct mode is left alone.
        self.assertEqual('https://example.joyn.de/a.mpd',
                         routing.MediaRouter(addon, prefix='at').route('https://example.joyn.de/a.mpd'))


class Response(object):
    def __init__(self, status, body):
        self.status_code = status
        self.body = body

    def json(self):
        if isinstance(self.body, (dict, list)):
            return self.body
        raise ValueError('not JSON')


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.profile = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.profile)

    def test_sessions_are_kept_per_region(self):
        at = joyn_api.Session(self.profile, 'at')
        de = joyn_api.Session(self.profile, 'de')
        at.store({'access_token': 'A', 'expires_in': 86400})
        self.assertNotEqual(at.deviceId, de.deviceId)
        self.assertFalse(joyn_api.Session(self.profile, 'de').valid())
        self.assertTrue(joyn_api.Session(self.profile, 'at').valid())
        self.assertEqual(0o600, os.stat(at.path).st_mode & 0o777)
        joyn_api.Session(self.profile, 'de').clear()
        self.assertEqual('A', joyn_api.Session(self.profile, 'at').data['access_token'])

    def test_requests_carry_the_route_and_the_tenant(self):
        api = joyn_api.JoynApi('ch', self.profile, {'proxies': {'https': 'http://proxy:1'}})
        calls = []

        def request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            if url.endswith('/anonymous'):
                return Response(200, {'access_token': 'T', 'expires_in': 86400})
            return Response(200, {'data': {'navigation': []}})

        api.http.request = request
        api.navigation()
        self.assertEqual(['POST', 'GET'], [method for method, _, _ in calls])
        for _, _, kwargs in calls:
            self.assertEqual({'https': 'http://proxy:1'}, kwargs['proxies'])
            self.assertEqual('JOYN_CH', kwargs['headers']['joyn-distribution-tenant'])
        self.assertFalse(api.http.trust_env)

    def test_playlist_is_signed_over_the_exact_body(self):
        api = joyn_api.JoynApi('at', self.profile)
        api.session.store({'access_token': 'T', 'expires_in': 86400})
        sent = {}

        def request(method, url, **kwargs):
            if 'entitlement' in url:
                return Response(200, {'entitlement_token': 'E'})
            sent.update(url=url, **kwargs)
            return Response(200, {'manifestUrl': 'https://cdn/x.mpd', 'licenseUrl': 'https://lic'})

        api.http.request = request
        api.playlist('orf1-at', joyn_api.LIVE)
        expected = hashlib.sha1(('%s,E%s' % (joyn_api.PLAYLIST_BODY, joyn_api.SIGNATURE_SECRET))
                                .encode('utf-8')).hexdigest()
        self.assertEqual(expected, sent['params']['signature'])
        self.assertEqual(joyn_api.PLAYLIST_BODY, sent['data'])
        self.assertTrue(sent['url'].endswith('/v1/channel/orf1-at/playlist'))

    def test_account_token_is_renewed_and_sign_out_returns_to_anonymous(self):
        api = joyn_api.JoynApi('de', self.profile)
        api.session.data['account'] = 'viewer@example.org'
        api.session.store({'access_token': 'OLD', 'refresh_token': 'R', 'expires_in': 0})
        device = api.session.deviceId
        sent = []

        def request(method, url, **kwargs):
            sent.append((url, kwargs.get('json')))
            if url.endswith('/refresh'):
                return Response(201, {'access_token': 'NEW', 'expires_in': 86400})
            if url.endswith('/anonymous'):
                return Response(200, {'access_token': 'ANON', 'expires_in': 86400})
            return Response(200, {})

        api.http.request = request
        self.assertEqual('NEW', api.token())
        self.assertEqual('R', sent[0][1]['refresh_token'])
        self.assertEqual('R', api.session.data['refresh_token'])
        api.logout()
        self.assertIsNone(api.account)
        self.assertEqual(device, api.session.deviceId)
        self.assertEqual('ANON', api.token())

    def test_a_refused_refresh_ends_the_sign_in(self):
        api = joyn_api.JoynApi('de', self.profile)
        api.session.data['account'] = 'viewer@example.org'
        api.session.store({'access_token': 'OLD', 'refresh_token': 'R', 'expires_in': 0})
        api.http.request = lambda method, url, **kwargs: Response(401, {'error': 'invalid_grant'})
        with self.assertRaises(joyn_api.JoynError) as caught:
            api.token()
        self.assertEqual('SIGNED_OUT', caught.exception.code)
        self.assertIsNone(joyn_api.Session(self.profile, 'de').data.get('account'))

    def test_entitlement_errors_keep_joyns_code(self):
        api = joyn_api.JoynApi('de', self.profile)
        api.session.store({'access_token': 'T', 'expires_in': 86400})
        api.http.request = lambda method, url, **kwargs: Response(
            400, [{'code': 'ENT_USER_VPN_DETECTED', 'msg': 'VPN'}])
        with self.assertRaises(joyn_api.JoynError) as caught:
            api.playlist('daserste-de-hd', joyn_api.LIVE)
        self.assertEqual('ENT_USER_VPN_DETECTED', caught.exception.code)
        self.assertIn('ENT_USER_VPN_DETECTED', joyn_api.MESSAGES)


def stream(streamId, title, kind='LINEAR', groups=(), plus=False, events=()):
    return {'id': streamId, 'title': title, 'type': kind, 'liveStreamGroups': list(groups),
            'markings': ['PLUS'] if plus else [], 'logo': {'url': 'https://img/%s.png' % streamId},
            'epgEvents': [{'startDate': start, 'endDate': end, 'program': {'title': name}}
                          for start, end, name in events]}


STREAMS = [stream('orf1-at', 'ORF1', events=[(200, 300, 'Later'), (100, 200, 'Now')]),
           stream('puls24-at-hd', 'PULS 24', groups=['SPORTS']),
           stream('odc-k11-at', 'K11', kind='ON_DEMAND'),
           stream('prosiebenfun-de-hd', 'ProSieben FUN', plus=True),
           stream('event', 'Event', kind='EVENT')]


class LineUpTest(unittest.TestCase):
    def test_channels_categories_and_programmes(self):
        channels = lineup.channels(STREAMS)
        self.assertEqual(['orf1-at', 'puls24-at-hd', 'odc-k11-at', 'prosiebenfun-de-hd'], list(channels))
        names = dict(lineup.categories(channels, kodistub.STRINGS.get))
        self.assertEqual(['orf1-at', 'puls24-at-hd', 'prosiebenfun-de-hd'], names['All channels'])
        self.assertEqual(['puls24-at-hd'], names['Sport'])
        self.assertEqual(['odc-k11-at'], names['Theme channels'])
        self.assertNotIn('Public service', names)
        guide = lineup.programmes(STREAMS)
        self.assertEqual(['Now', 'Later'], [p['title'] for _, _, p in guide['orf1-at']])
        self.assertEqual([], guide['puls24-at-hd'])


class FakeApi(object):
    def __init__(self, streams):
        self.streams = streams
        self.fail = False

    def live(self, hours=12):
        if self.fail:
            raise joyn_api.JoynError('down')
        return self.streams


class IptvTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.store = os.path.join(self.folder, 'iptv.json')

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_numbers_stay_with_their_channel_and_skip_taken_ones(self):
        numbers = iptv.assignNumbers(['a', 'b'], {}, (6001, 6499), taken=[6002])
        self.assertEqual({'a': 6001, 'b': 6003}, numbers)
        numbers = iptv.assignNumbers(['c', 'b', 'a'], numbers, (6001, 6499))
        self.assertEqual({'a': 6001, 'b': 6003, 'c': 6004}, numbers)
        # Dropped channels keep their numbers reserved.
        self.assertEqual({'a': 6001, 'b': 6003, 'c': 6004, 'd': 6005},
                         iptv.assignNumbers(['d'], numbers, (6001, 6499)))

    def test_full_range_leaves_channels_out(self):
        self.assertEqual({'a': 7001, 'b': 7002}, iptv.assignNumbers(['a', 'b', 'c'], {}, (7001, 7002)))

    def test_streams_are_plugin_routes_in_region_groups(self):
        data = iptv.channels([('at', FakeApi(STREAMS))], self.store, existing=[(1, 'Tubi Channel')])
        first = data['streams'][0]
        self.assertEqual('joyn.at.orf1-at', first['id'])
        self.assertEqual(6001, first['preset'])
        self.assertEqual(['Joyn AT'], first['group'])
        self.assertEqual('plugin://plugin.video.joyn.kodiallen/?id=orf1-at&mode=live&region=at', first['stream'])
        for entry in data['streams']:
            self.assertNotIn('token', entry['stream'])
            self.assertTrue(6001 <= entry['preset'] <= 6499)

    def test_a_failed_region_serves_its_saved_line_up(self):
        api = FakeApi(STREAMS)
        before = iptv.channels([('at', api)], self.store)
        api.fail = True
        after = iptv.channels([('at', api)], self.store)
        self.assertEqual(before['streams'], after['streams'])

    def test_existing_channels_can_be_left_out_and_numbers_are_never_reused(self):
        existing = [(5001, 'ORF 1 HD'), (6001, 'Something else')]
        data = iptv.channels([('at', FakeApi(STREAMS))], self.store, existing=existing, skipExisting=True)
        ids = [entry['id'] for entry in data['streams']]
        self.assertNotIn('joyn.at.orf1-at', ids)
        self.assertNotIn(6001, [entry['preset'] for entry in data['streams']])
        # The add-on's own earlier export does not count as somebody else's.
        own = [(entry['preset'], entry['name']) for entry in data['streams']]
        again = iptv.channels([('at', FakeApi(STREAMS))], self.store, existing=existing + own)
        self.assertEqual(sorted(entry['preset'] for entry in data['streams']),
                         sorted(entry['preset'] for entry in again['streams'] if entry['id'] != 'joyn.at.orf1-at'))

    def test_name_keys_match_across_line_ups(self):
        self.assertEqual(iptv.nameKey('ORF 1 HD'), iptv.nameKey('ORF1'))
        self.assertEqual(iptv.nameKey('Das Erste HD'), iptv.nameKey('Das Erste'))
        self.assertEqual(iptv.nameKey('PULS 4 AT'), iptv.nameKey('PULS 4'))
        self.assertNotEqual(iptv.nameKey('ORF 1'), iptv.nameKey('ORF 2'))

    def test_epg_uses_utc_iso_times_for_exported_channels(self):
        iptv.channels([('at', FakeApi(STREAMS))], self.store)
        guide = iptv.epg([('at', FakeApi(STREAMS))], self.store)['epg']
        self.assertEqual({'start': '1970-01-01T00:01:40+00:00', 'stop': '1970-01-01T00:03:20+00:00',
                          'title': 'Now'}, guide['joyn.at.orf1-at'][0])

    def test_region_ranges_do_not_overlap_existing_ranges(self):
        used = [(1, 190), (2001, 5203)]
        for first, last in regions.CHANNEL_RANGES.values():
            for low, high in used:
                self.assertTrue(last < low or first > high)


if __name__ == '__main__':
    unittest.main()
