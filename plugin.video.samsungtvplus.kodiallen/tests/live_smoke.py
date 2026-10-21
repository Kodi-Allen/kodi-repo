# -*- coding: utf-8 -*-
"""Live check against the published Samsung TV Plus data (reads only). Run: python3 tests/live_smoke.py"""
import time

import kodistub

from resources.lib import iptv, live, player
from resources.lib.catalog import StvAddon


def main():
    addon = StvAddon()
    t0 = time.monotonic(); data = addon.data
    print('channels', len(data.channels), 'groups', len(data.groups()), 'left out (Widevine)', data.locked,
          '%.1fs' % (time.monotonic() - t0))
    t0 = time.monotonic(); guide = data.guide()
    print('guide channels', len(guide), 'programmes', sum(len(v) for v in guide.values()), '%.1fs' % (time.monotonic() - t0))
    items = [addon.channelItem(c) for c in data.channels.values()]
    now = sum(1 for _, item, _ in items if item.getProperty('stv.now'))
    print('items', len(items), 'with now', now, 'example:', items[1][1].getLabel(), '|', items[1][1].getProperty('stv.now'), '|', items[1][1].getProperty('stv.next'))
    cats, channels, g = live.lineUp(addon)
    print('guide categories', [(n, len(i)) for n, i in cats][:6])
    first = next(iter(data.channels))
    del kodistub.RESOLVED[:]
    player.resolve(addon, 1, first)
    ok, item = kodistub.RESOLVED[-1]
    print('resolve direct', first, ok, item.path[:40], sorted(k for k in item.properties if 'adaptive' in k))
    kodistub.SETTINGS.update({'route_mode': '1', 'relay_host': '192.0.2.10', 'relay_port': '34405', 'relay_signing_key': 'k' * 64})
    relayed = StvAddon(); del kodistub.RESOLVED[:]
    player.resolve(relayed, 1, first)
    item = kodistub.RESOLVED[-1][1]
    print('resolve relay', item.path[:45])
    kodistub.SETTINGS.clear()
    store = kodistub.PROFILE + '/iptv.json'
    print('iptv export (Kodi free):', len(iptv.channels(lambda: data, store, existing=[(1, 'Tubi')])['streams']))
    print('iptv export (Threadfin already 8001+):', len(iptv.channels(lambda: data, store + '2', existing=[(8001, 'Cine Paura')])['streams']))


if __name__ == '__main__':
    main()
