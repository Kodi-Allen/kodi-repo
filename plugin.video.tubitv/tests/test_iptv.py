import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock


ADDON_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ADDON_ROOT not in sys.path:
    sys.path.insert(0, ADDON_ROOT)

sys.modules.setdefault('xbmc', types.SimpleNamespace(
    LOGDEBUG=0, LOGINFO=1, LOGWARNING=2, log=lambda **kwargs: None))

from resources.lib import iptv  # noqa: E402
from resources.lib import tubi_api  # noqa: E402


PLAY = 'plugin://plugin.video.tubitv/?mode=LV&url=%s'
LOGO = 'https://canvas-lb.tubitv.com/opts/abc/%s/thumb'


def channel(channelId, title=None):
    return {'id': channelId, 'title': title or 'Channel %s' % channelId,
            'images': {'thumbnail': [LOGO % channelId]}}


class FakeApi(object):
    def __init__(self, lineUp, groups=None, rows=None):
        self.lineUp = lineUp
        self.groups = groups or {}
        self.rows = rows or []
        self.fail = False
        self.allGroups = None

    def liveChannels(self, allGroups=False):
        self.allGroups = allGroups
        if self.fail:
            raise iptv.TubiApiError('SSL: UNEXPECTED_EOF_WHILE_READING')
        return self.lineUp, self.groups

    def liveProgramming(self, channelIds, tolerant=False):
        self.asked = list(channelIds)
        return self.rows


class ChannelNumberTest(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.store = os.path.join(self.folder, 'profile', 'iptv.json')

    def tearDown(self):
        shutil.rmtree(self.folder)

    def presets(self, ids):
        api = FakeApi([channel(i) for i in ids])
        streams = iptv.channels(api, PLAY, store=self.store)['streams']
        return dict((stream['id'], stream['preset']) for stream in streams)

    def test_first_line_up_is_numbered_in_tubi_order(self):
        self.assertEqual({'613761': 1, '400000121': 2, '556174': 3},
                         self.presets(['613761', '400000121', '556174']))

    def test_reordering_and_a_new_channel_move_nobody(self):
        self.presets(['a', 'b', 'c'])
        self.assertEqual({'c': 3, 'new': 4, 'a': 1, 'b': 2},
                         self.presets(['c', 'new', 'a', 'b']))

    def test_dropped_channel_keeps_its_number_reserved(self):
        self.presets(['a', 'b', 'c'])
        self.assertEqual({'a': 1, 'c': 3, 'd': 4}, self.presets(['a', 'c', 'd']))
        self.assertEqual({'a': 1, 'b': 2, 'c': 3, 'd': 4},
                         self.presets(['a', 'b', 'c', 'd']))

    def test_numbers_are_kept_in_the_store_between_calls(self):
        self.presets(['a', 'b'])
        with open(self.store) as handle:
            self.assertEqual({'a': 1, 'b': 2}, json.load(handle)['numbers'])

    def test_unreadable_store_starts_afresh(self):
        os.makedirs(os.path.dirname(self.store))
        with open(self.store, 'w') as handle:
            handle.write('{not json')
        self.assertEqual({'x': 1, 'y': 2}, self.presets(['x', 'y']))

    def test_without_a_store_numbers_follow_the_line_up(self):
        api = FakeApi([channel('a'), channel('b')])
        streams = iptv.channels(api, PLAY)['streams']
        self.assertEqual([1, 2], [stream['preset'] for stream in streams])

    def test_a_store_that_cannot_be_written_still_serves_the_line_up(self):
        api = FakeApi([channel('a')])
        with mock.patch.object(iptv.os, 'replace', side_effect=OSError('read-only')):
            streams = iptv.channels(api, PLAY, store=self.store)['streams']
        self.assertEqual(['a'], [stream['id'] for stream in streams])


class ChannelDocumentTest(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.store = os.path.join(self.folder, 'iptv.json')

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_channel_carries_every_tubi_group(self):
        api = FakeApi([channel('613761', 'NFL Channel'), channel('9')],
                      groups={'613761': ['Featured', 'Sports On Now']})
        streams = iptv.channels(api, PLAY)['streams']
        self.assertTrue(api.allGroups)
        self.assertEqual(['Featured', 'Sports On Now'], streams[0]['group'])
        self.assertEqual([], streams[1]['group'])

    def test_stream_is_the_plugin_path_and_logo_is_tubis_own_url(self):
        api = FakeApi([channel('613761', 'NFL &amp; More')])
        stream = iptv.channels(api, PLAY)['streams'][0]
        self.assertEqual(PLAY % '613761', stream['stream'])
        self.assertEqual(LOGO % '613761', stream['logo'])
        self.assertEqual('NFL & More', stream['name'])

    def test_unreachable_tubi_serves_the_saved_line_up(self):
        api = FakeApi([channel('a'), channel('b')])
        served = iptv.channels(api, PLAY, store=self.store)
        api.fail = True
        self.assertEqual(served, iptv.channels(api, PLAY, store=self.store))

    def test_unreachable_tubi_without_a_saved_line_up_fails(self):
        api = FakeApi([])
        api.fail = True
        with self.assertRaises(iptv.TubiApiError):
            iptv.channels(api, PLAY, store=self.store)


class GuideTest(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.store = os.path.join(self.folder, 'iptv.json')

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_programme_image_is_tubis_own_url(self):
        image = 'https://canvas-lb.tubitv.com/opts/xyz/programme/thumb'
        rows = [{'content_id': 613761, 'programs': [
            {'start_time': '2026-10-04T17:00:00Z', 'end_time': '2026-10-04T18:00:00Z',
             'title': 'NFL Game Center Live', 'images': {'thumbnail': [image]}}]}]
        guide = iptv.epg(FakeApi([], rows=rows), ['613761'])['epg']
        self.assertEqual(image, guide['613761'][0]['image'])
        self.assertEqual('2026-10-04T17:00:00Z', guide['613761'][0]['start'])

    def test_guide_falls_back_to_the_saved_channel_ids(self):
        api = FakeApi([channel('a'), channel('b')])
        iptv.channels(api, PLAY, store=self.store)
        api.fail = True
        iptv.guideFor(api, store=self.store)
        self.assertEqual(['a', 'b'], api.asked)

    def test_guide_without_line_up_or_saved_ids_fails(self):
        api = FakeApi([])
        api.fail = True
        with self.assertRaises(iptv.TubiApiError):
            iptv.guideFor(api, store=self.store)


EPG_PAYLOAD = {
    'contents': {'613761': {'id': '613761', 'title': 'NFL Channel'},
                 '560215': {'id': '560215', 'title': 'Estrella News'},
                 '715939': {'id': '715939', 'title': 'Paws & Claws'}},
    'containers': [{'name': 'Featured', 'contents': ['613761']},
                   {'name': 'National News', 'contents': ['560215']},
                   {'name': 'Sports On Now', 'contents': ['613761']},
                   {'name': 'Español', 'contents': ['560215']}],
}


def response(payload):
    reply = mock.Mock()
    reply.json.return_value = payload
    return reply


class LiveApiTest(unittest.TestCase):

    def api(self):
        return tubi_api.TubiApi({}, 'device-id')

    def test_line_up_keeps_only_the_first_group_by_default(self):
        with mock.patch.object(tubi_api.requests, 'get', return_value=response(EPG_PAYLOAD)):
            lineUp, groups = self.api().liveChannels()
        self.assertEqual(['613761', '560215', '715939'], [c['id'] for c in lineUp])
        self.assertEqual({'613761': 'Featured', '560215': 'National News'}, groups)

    def test_line_up_can_carry_every_group_in_tubi_order(self):
        with mock.patch.object(tubi_api.requests, 'get', return_value=response(EPG_PAYLOAD)):
            _, groups = self.api().liveChannels(allGroups=True)
        self.assertEqual({'613761': ['Featured', 'Sports On Now'],
                          '560215': ['National News', 'Español']}, groups)

    def test_guide_asks_for_the_furthest_lookahead_tubi_serves(self):
        with mock.patch.object(tubi_api.requests, 'get',
                               return_value=response({'rows': []})) as get:
            self.api().liveProgramming(['613761'])
        self.assertIn(('lookahead', 2), get.call_args.kwargs['params'])

    def test_live_call_retries_a_failed_connection(self):
        failure = tubi_api.requests.exceptions.SSLError('UNEXPECTED_EOF_WHILE_READING')
        with mock.patch.object(tubi_api.requests, 'get',
                               side_effect=[failure, failure, response(EPG_PAYLOAD)]) as get:
            lineUp, _ = self.api().liveChannels()
        self.assertEqual(3, get.call_count)
        self.assertEqual(3, len(lineUp))

    def test_live_call_gives_up_after_three_failed_connections(self):
        failure = tubi_api.requests.exceptions.ConnectionError('tunnel lost')
        with mock.patch.object(tubi_api.requests, 'get', side_effect=failure) as get:
            with self.assertRaises(tubi_api.TubiApiError):
                self.api().liveChannels()
        self.assertEqual(tubi_api.LIVE_ATTEMPTS, get.call_count)

    def test_an_answer_from_tubi_is_not_retried(self):
        reply = response({})
        reply.raise_for_status.side_effect = tubi_api.requests.exceptions.HTTPError('503')
        with mock.patch.object(tubi_api.requests, 'get', return_value=reply) as get:
            with self.assertRaises(tubi_api.TubiApiError):
                self.api().liveChannels()
        self.assertEqual(1, get.call_count)

    def test_other_calls_still_try_once(self):
        failure = tubi_api.requests.exceptions.ConnectionError('tunnel lost')
        with mock.patch.object(tubi_api.requests, 'get', side_effect=failure) as get:
            with self.assertRaises(tubi_api.TubiApiError):
                self.api().browseList()
        self.assertEqual(1, get.call_count)


if __name__ == '__main__':
    unittest.main()
