"""What the resolved playback item tells Kodi, and so Trakt's scrobbler."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_rc import Settings, isolated, kodiStubs  # noqa: E402
from resources.lib import tubi_api  # noqa: E402

CLEAR = [{'type': tubi_api.CLEAR, 'resolution': 'VIDEO_RESOLUTION_720P',
          'codec': 'VIDEO_CODEC_H264', 'manifest': {'url': 'https://cdn.example/c.m3u8'}}]
ENCRYPTED = [{'type': tubi_api.DASH_WIDEVINE, 'resolution': 'VIDEO_RESOLUTION_576P',
              'codec': 'VIDEO_CODEC_H264', 'manifest': {'url': 'https://cdn.example/e.mpd'},
              'license_server': {'url': 'https://license.example/l', 'hdcp_version': 'hdcp_disabled'}}]


def seasonPage(seriesTitle, season, episodes):
    """One page of /api/v3/content for a series and season, as Tubi answers it."""
    return {'id': '0300001', 'title': seriesTitle, 'year': 2023, 'children': [
        {'id': str(season), 'title': 'Season %d' % season, 'children': episodes}]}


class PlaybackMetadataTest(unittest.TestCase):

    def setUp(self):
        self.argv = mock.patch.object(sys, 'argv', ['plugin://plugin.video.tubitv/', '7', ''])
        self.argv.start()
        self.addCleanup(self.argv.stop)
        self.stubs = kodiStubs(Settings({'route_mode': '0'}))
        scraper, = isolated(self.stubs, 'scraper')
        self.addon = scraper.myAddon('tubitv')
        self.api = tubi_api.TubiApi({}, 'device')
        self.addon.api = self.api

    def resolved(self, url, content=None, pages=None):
        if pages is not None:
            self.api.content = mock.Mock(side_effect=lambda *a, **k: pages[k.get('page', 1) - 1])
        else:
            self.api.content = mock.Mock(return_value=content)
        self.addon.getAddonVideo(url)
        (_, succeeded, item), = self.stubs['xbmcplugin'].setResolvedUrl.calls
        self.assertTrue(succeeded)
        return item, item.tag.values

    def assertNotExcluded(self, item):
        self.assertNotIn('script.trakt.exclude', item.properties)

    def test_movie_with_a_release_year(self):
        item, tag = self.resolved('589292', {'id': 589292, 'title': 'The Goonies', 'year': 1985,
                                             'video_resources': CLEAR})
        self.assertEqual(('movie',), tag['setMediaType'])
        self.assertEqual(('The Goonies',), tag['setTitle'])
        self.assertEqual((1985,), tag['setYear'])
        self.assertNotIn('setTvShowTitle', tag)
        self.assertNotIn('setSeason', tag)
        self.assertNotExcluded(item)
        self.assertEqual('inputstream.adaptive', item.properties['inputstream'])

    def test_movie_without_a_usable_year(self):
        for year in (None, 0, 'n/a', 3021):
            self.stubs['xbmcplugin'].setResolvedUrl.calls[:] = []
            item, tag = self.resolved('589292', {'id': 589292, 'title': 'A Film', 'year': year,
                                                 'video_resources': CLEAR})
            self.assertEqual(('movie',), tag['setMediaType'])
            self.assertEqual(('A Film',), tag['setTitle'])
            self.assertNotIn('setYear', tag, year)
            self.assertNotExcluded(item)

    def test_encrypted_movie_keeps_its_drm_and_gets_its_identity(self):
        item, tag = self.resolved('589292', {'id': 589292, 'title': 'The Mask', 'year': 1994,
                                             'video_resources': ENCRYPTED})
        self.assertIn('inputstream.adaptive.drm_legacy', item.properties)
        self.assertEqual((1994,), tag['setYear'])

    def test_first_episode(self):
        episode = {'id': 'e1', 'title': 'S01:E01 - Mole Hunt', 'episode_number': 1,
                   'year': 2009, 'video_resources': CLEAR}
        item, tag = self.resolved('e1|300001|1', pages=[seasonPage('Archer', 1, [episode])])
        self.assertEqual(('episode',), tag['setMediaType'])
        self.assertEqual(('Mole Hunt',), tag['setTitle'])
        self.assertEqual(('Archer',), tag['setTvShowTitle'])
        self.assertEqual((1,), tag['setSeason'])
        self.assertEqual((1,), tag['setEpisode'])
        self.assertNotIn('setYear', tag)  # the episode's year is not the show's
        self.assertNotExcluded(item)

    def test_later_season_episode_on_a_later_page(self):
        first = [{'id': 'f%d' % n, 'title': 'S05:E%02d - Earlier' % n, 'episode_number': n,
                  'video_resources': CLEAR} for n in range(1, tubi_api.SEASON_PAGE_SIZE + 1)]
        wanted = {'id': 'e21', 'title': 'S05:E21 - Later Episode', 'episode_number': 21,
                  'year': 2014, 'video_resources': CLEAR}
        pages = [seasonPage('Archer', 5, first), seasonPage('Archer', 5, [wanted])]
        item, tag = self.resolved('e21|300001|5', pages=pages)
        self.assertEqual(('Later Episode',), tag['setTitle'])
        self.assertEqual(('Archer',), tag['setTvShowTitle'])
        self.assertEqual((5,), tag['setSeason'])
        self.assertEqual((21,), tag['setEpisode'])
        self.assertNotIn('setYear', tag)
        self.assertNotExcluded(item)

    def test_trailer_is_excluded_and_not_described_as_the_title(self):
        item, tag = self.resolved('trailer|589292', {'trailers': [{'url': 'https://cdn.example/t.m3u8'}]})
        self.assertEqual('true', item.properties['script.trakt.exclude'])
        self.assertNotIn('setMediaType', tag)
        self.assertNotIn('setYear', tag)

    def test_live_channel_is_excluded(self):
        channel = {'id': 400000024, 'video_resources': [{
            'type': tubi_api.LIVE, 'manifest': {'url': 'https://live.example/c.m3u8'}}]}
        self.api.liveChannels = mock.Mock(return_value=([channel], {}))
        self.addon.getAddonLiveVideo('400000024')
        (_, succeeded, item), = self.stubs['xbmcplugin'].setResolvedUrl.calls
        self.assertTrue(succeeded)
        self.assertEqual('true', item.properties['script.trakt.exclude'])
        self.assertEqual('inputstream.adaptive', item.properties['inputstream'])

    def test_progress_reporting_is_unchanged(self):
        self.addon.addon.setSetting('report_progress', 'true')
        episode = {'id': '777', 'title': 'S02:E03 - X', 'episode_number': 3, 'video_resources': CLEAR}
        self.resolved('777|300001|2', pages=[seasonPage('Archer', 2, [episode])])
        playing = self.stubs['xbmcgui'].Window(10000).getProperty('tubitv.playing')
        self.assertIn('"content_type": "episode"', playing)
        self.assertIn('"parent_id": "300001"', playing)


class EpisodesKeepTheirSeriesTest(unittest.TestCase):

    def test_episodes_carry_the_series_title_of_their_page(self):
        api = tubi_api.TubiApi({}, 'device')
        api.content = mock.Mock(return_value=seasonPage('Archer', 1, [{'id': 'e1'}, {'id': 'e2'}]))
        self.assertEqual(['Archer', 'Archer'], [e['series_title'] for e in api.episodes('300001', 1)])


if __name__ == '__main__':
    unittest.main()
