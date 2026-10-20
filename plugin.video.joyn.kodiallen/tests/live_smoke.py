# -*- coding: utf-8 -*-
"""Live check against Joyn: every catalogue path and one playback per kind.

Not a unit test - it talks to Joyn over this machine's connection and only
reads. Run it from the add-on folder:

    python3 tests/live_smoke.py at
"""
import sys
import time

import kodistub  # noqa: F401  (installs the Kodi stubs)

from resources.lib import lineup
from resources.lib.catalog import JoynAddon, SERIES, MOVIE
from resources.lib.joyn_api import LIVE, VOD, JoynError
from resources.lib import player


def timed(label, call):
    started = time.monotonic()
    try:
        result = call()
        print('OK   %-28s %.2fs  %s' % (label, time.monotonic() - started, result))
        return True
    except JoynError as err:
        print('FAIL %-28s code=%s status=%s %s' % (label, err.code, err.status, err))
    except Exception as err:
        print('FAIL %-28s %s: %s' % (label, type(err).__name__, err))
    return False


def main(region):
    addon = JoynAddon(region)
    found = {}

    def home():
        blocks = addon.page('/')
        rows = addon.rows(blocks)
        hero = [b for b in blocks if b.get('__typename') == 'HeroLane']
        found['rows'] = rows
        return '%d blocks, %d poster rows, hero %d, first row "%s" (%d)' % (
            len(blocks), len(rows), len((hero or [{}])[0].get('assets') or []), rows[0][0], len(rows[0][2]))

    def page(path):
        rows = addon.rows(addon.page(path))
        return '%d rows: %s' % (len(rows), ', '.join(title for title, _, _ in rows[:4]))

    def seriesDetail():
        for _, _, items in found['rows']:
            for url, item, isFolder in items:
                if isFolder:
                    path = url.split('path=')[1].split('&')[0].replace('%2F', '/')
                    series, seasons = addon.seasonList(path)
                    episodes = addon.episodeItems(seasons[0], series.get('title'))
                    found['episode'] = episodes[0][0]
                    tag = episodes[0][1].getVideoInfoTag()
                    return '%s: %d seasons, season %s has %d episodes, first S%02dE%02d %s' % (
                        series.get('title'), len(seasons), seasons[0]['number'], len(episodes),
                        tag.getSeason(), tag.getEpisode(), episodes[0][1].getLabel())
        raise RuntimeError('no series in the start page rows')

    def searchFor():
        results = addon.api.search('Tatort')
        kinds = {}
        for asset in results:
            kinds[asset.get('__typename')] = kinds.get(asset.get('__typename'), 0) + 1
        return '%d results %s' % (len(results), kinds)

    def liveGuide():
        streams = addon.api.live()
        channels = lineup.channels(streams)
        guide = lineup.programmes(streams)
        cats = lineup.categories(channels, addon.localLang)
        now = time.time()
        airing = sum(1 for items in guide.values() if any(s <= now < e for s, e, _ in items))
        found['channel'] = [cid for cid, c in channels.items() if c['type'] == 'LINEAR' and not c['plus']][0]
        return '%d channels, %d airing now, categories %s' % (
            len(channels), airing, [(name, len(ids)) for name, ids in cats])

    def play(contentId, kind, video=None):
        def call():
            del kodistub.RESOLVED[:]
            ok = player.resolve(addon, 1, contentId, kind, videoId=video)
            item = kodistub.RESOLVED[-1][1]
            if not ok:
                raise RuntimeError('refused: %s' % (kodistub.NOTIFIED[-1:],))
            return '%s drm=%s' % (item.path.split('?')[0][:70],
                                  'yes' if any('drm' in k or 'license' in k for k in item.properties) else 'no')
        return call

    timed('token', lambda: addon.api.token()[:12] + '…')
    timed('navigation', lambda: '%d groups' % len(addon.api.navigation()))
    timed('home /', home)
    for path in ('/serien', '/filme', '/shows'):
        timed('page ' + path, lambda path=path: page(path))
    timed('series + episodes', seriesDetail)
    timed('search', searchFor)
    timed('live guide', liveGuide)
    if 'channel' in found:
        timed('play live ' + found['channel'], play(found['channel'], LIVE))
    if 'episode' in found:
        query = dict(part.split('=', 1) for part in found['episode'].split('?', 1)[1].split('&'))
        timed('play episode ' + query['id'], play(query['id'], VOD, query.get('video')))
    movies = [item for _, _, items in found.get('rows', []) for item in items if not item[2]]
    if movies:
        query = dict(part.split('=', 1) for part in movies[0][0].split('?', 1)[1].split('&'))
        timed('play movie ' + query['id'], play(query['id'], VOD, query.get('video')))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'at')
