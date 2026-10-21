# -*- coding: utf-8 -*-
import gzip
import json
import os
import shutil
import tempfile
import time
import unittest

import kodistub  # noqa: F401  (installs the Kodi stubs)

from resources.lib import data, iptv

APP = {'slug': 'stvp-{id}', 'headers': {'user-agent': 'okhttp/4.12.0'}, 'regions': {'it': {'channels': {
    'IT2': {'name': 'Second', 'chno': 2, 'group': 'News', 'logo': 'https://logo/2.png', 'programs': []},
    'IT1': {'name': 'First', 'chno': 1, 'group': 'Film', 'logo': 'https://logo/1.png', 'programs': []},
    'IT3': {'name': 'Locked', 'chno': 3, 'group': 'Film', 'logo': '', 'license_url': 'https://lic', 'programs': []}}}}}
XMLTV = b'''<?xml version="1.0"?><tv>
<programme channel="IT1" start="20261021100000 +0000" stop="20261021110000 +0000"><title>Now</title><desc>d</desc><icon src="https://img/1"/></programme>
<programme channel="IT1" start="20261021110000 +0000" stop="20261021120000 +0000"><title>Next</title></programme>
<programme channel="IT1" start="20261021150000 +0200" stop="20261021160000 +0200"><title>Shifted</title></programme>
<programme channel="OTHER" start="20261021100000 +0000" stop="20261021110000 +0000"><title>x</title></programme></tv>'''
NOW = 1792576800 + 1800   # 2026-10-21 10:30 UTC


class DataTest(unittest.TestCase):
    def setUp(self):
        self.profile = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.profile, 'cache'))
        for name, payload in (('.channels.json.gz', json.dumps(APP).encode()), ('it.xml.gz', XMLTV)):
            with open(os.path.join(self.profile, 'cache', name), 'wb') as handle:
                handle.write(gzip.compress(payload))

    def tearDown(self):
        shutil.rmtree(self.profile)

    def test_channels_follow_samsung_order_without_the_widevine_ones(self):
        region = data.Region(self.profile, 'it')
        self.assertEqual(['IT1', 'IT2'], list(region.channels))
        self.assertEqual(1, region.locked)
        self.assertEqual(['Film', 'News'], region.groups())
        self.assertEqual('https://jmp2.uk/stvp-IT1', region.playUrl('IT1'))

    def test_guide_times_are_utc_and_now_next_is_found(self):
        region = data.Region(self.profile, 'it')
        guide = region.guide()
        self.assertNotIn('OTHER', guide)
        self.assertEqual(1792576800, guide['IT1'][0][0])
        self.assertEqual(1792576800 + 3 * 3600, guide["IT1"][2][0])      # 15:00 +0200 is 13:00 UTC
        current, following = region.nowNext('IT1', NOW)
        self.assertEqual('Now', current[2]['title'])
        self.assertEqual('https://img/1', current[2]['icon'])
        self.assertEqual('Next', following[2]['title'])
        self.assertEqual((None, None), region.nowNext('IT2', NOW))

    def test_a_failed_download_falls_back_to_the_cache(self):
        os.utime(os.path.join(self.profile, 'cache', '.channels.json.gz'), (0, 0))      # stale, so a download is tried
        original = data.requests.get
        data.requests.get = lambda *args, **kwargs: (_ for _ in ()).throw(data.requests.ConnectionError('down'))
        try:
            self.assertEqual(2, len(data.Region(self.profile, 'it').channels))
        finally:
            data.requests.get = original


class Lineup(object):
    def __init__(self, ids):
        self.channels = dict((cid, {'name': cid, 'logo': '', 'group': 'Film'}) for cid in ids)


class IptvTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.store = os.path.join(self.folder, 'iptv.json')

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_numbers_are_stable_and_skip_taken_ones(self):
        numbers = iptv.assignNumbers(['a', 'b'], {}, taken=[8002])
        self.assertEqual({'a': 8001, 'b': 8003}, numbers)
        self.assertEqual({'a': 8001, 'b': 8003, 'c': 8004}, iptv.assignNumbers(['c', 'b', 'a'], numbers))

    def test_nothing_is_exported_when_another_source_uses_the_range(self):
        result = iptv.channels(lambda: Lineup(['IT1']), self.store, existing=[(8001, 'Cine Paura')])
        self.assertEqual([], result['streams'])

    def test_own_earlier_export_is_not_a_conflict(self):
        first = iptv.channels(lambda: Lineup(['IT1', 'IT2']), self.store)
        own = [(s['preset'], s['name']) for s in first['streams']]
        again = iptv.channels(lambda: Lineup(['IT1', 'IT2']), self.store, existing=own)
        self.assertEqual(first['streams'], again['streams'])
        self.assertEqual('plugin://plugin.video.samsungtvplus.kodiallen/?id=IT1&mode=play', first['streams'][0]['stream'])

    def test_a_data_failure_serves_the_saved_line_up(self):
        first = iptv.channels(lambda: Lineup(['IT1']), self.store)

        def broken():
            raise data.DataError('down')
        self.assertEqual(first['streams'], iptv.channels(broken, self.store)['streams'])


if __name__ == '__main__':
    unittest.main()
