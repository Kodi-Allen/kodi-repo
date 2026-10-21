# -*- coding: utf-8 -*-
# IPTV Manager integration (optional, off by default)
#
# https://github.com/add-ons/service.iptv.manager/wiki/Integration
#
# IPTV Manager calls plugin://plugin.video.samsungtvplus.kodiallen/iptv/channels
# and .../iptv/epg with a port; the add-on connects back and writes
# JSON-STREAMS or JSON-EPG. IPTV Manager keeps every add-on's channels apart.
#
# Only one way into Kodi TV at a time: when Kodi already shows channels in
# this add-on's number range from another source (for example a Threadfin
# list of the same Samsung channels), nothing is exported.
#
import json
import os
import re
import socket
import time

import xbmc

VERSION = 1
TIMEOUT = 30
ADDON_ID = 'plugin.video.samsungtvplus.kodiallen'
CHANNELS_ROUTE = '/iptv/channels'
EPG_ROUTE = '/iptv/epg'
STORE = 'iptv.json'
FIRST, LAST = 8001, 8499
GROUP = 'Samsung TV Plus IT'
# A plain plugin route, resolved when the channel is tuned; nothing that expires goes into the playlist.
PLAY = 'plugin://%s/?id=%s&mode=play'
CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def send(port, produce):
    """Open IPTV Manager's socket first, then build the document (see the Tubi add-on)."""
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(TIMEOUT)
    try:
        connection.connect(('127.0.0.1', int(port)))
        connection.settimeout(None)
        connection.sendall(json.dumps(produce()).encode('utf-8'))
    finally:
        connection.close()


def warn(message):
    xbmc.log(msg=''.join([ADDON_ID, ' : ', message]), level=xbmc.LOGWARNING)


def plainText(value):
    return re.sub(r'[<>]', '', CONTROL.sub('', str(value or ''))).strip()


def loadStore(path):
    try:
        with open(path, 'r') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (IOError, OSError, ValueError):
        return {}


def saveStore(path, data):
    try:
        folder = os.path.dirname(path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(path + '.tmp', 'w') as handle:
            json.dump(data, handle)
        os.replace(path + '.tmp', path)
    except (IOError, OSError) as err:
        warn('iptv store not saved : %s' % err)


def assignNumbers(channelIds, numbers, taken=()):
    """A number per Samsung id that never changes; numbers in use elsewhere are skipped."""
    numbers = dict((key, value) for key, value in (numbers or {}).items() if isinstance(value, int) and FIRST <= value <= LAST)
    used = set(numbers.values()) | set(taken)
    following = max(list(numbers.values()) or [FIRST - 1]) + 1
    for channelId in channelIds:
        if channelId in numbers:
            continue
        while following in used and following <= LAST:
            following += 1
        if following > LAST:
            warn('number range %d-%d is full, %s left out' % (FIRST, LAST, channelId))
            continue
        numbers[channelId] = following
        used.add(following)
        following += 1
    return numbers


def existingChannels():
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'PVR.GetChannels',
               'params': {'channelgroupid': 'alltv', 'properties': ['channelnumber']}}
    try:
        result = json.loads(xbmc.executeJSONRPC(json.dumps(request))).get('result') or {}
    except (TypeError, ValueError):
        return []
    return [(channel.get('channelnumber'), channel.get('label') or '') for channel in result.get('channels') or []]


def foreignInRange(existing, saved):
    """Channels in this add-on's range that this add-on did not export itself."""
    own = set((stream.get('preset'), stream.get('name')) for stream in saved.get('streams') or [])
    return [(number, name) for number, name in existing
            if isinstance(number, int) and FIRST <= number <= LAST and (number, name) not in own]


def channels(data, store, existing=()):
    saved = loadStore(store)
    clash = foreignInRange(existing, saved)
    if clash:
        warn('%d channels from another source already use %d-%d (e.g. %s); not exporting to avoid duplicates'
             % (len(clash), FIRST, LAST, clash[0][1]))
        return {'version': VERSION, 'streams': []}
    try:
        lineUp = data()
    except Exception as err:
        warn('channel data unavailable, serving the saved line-up : %s' % type(err).__name__)
        return {'version': VERSION, 'streams': saved.get('streams') or []}
    taken = [number for number, _ in existing if isinstance(number, int)]
    numbers = assignNumbers(list(lineUp.channels), saved.get('numbers'), taken)
    streams = []
    for channelId, channel in lineUp.channels.items():
        if channelId not in numbers:
            continue
        streams.append({'id': 'samsung.it.%s' % channelId, 'name': plainText(channel['name']), 'logo': channel['logo'] or None,
                        'preset': numbers[channelId], 'stream': PLAY % (ADDON_ID, channelId),
                        'group': [GROUP] + ([channel['group']] if channel['group'] else [])})
    saveStore(store, {'numbers': numbers, 'streams': streams})
    return {'version': VERSION, 'streams': streams}


def epg(data, store):
    exported = set(stream['id'] for stream in loadStore(store).get('streams') or [])
    try:
        guide = data().guide()
    except Exception as err:
        warn('guide unavailable : %s' % type(err).__name__)
        return {'version': VERSION, 'epg': {}}
    stamp = lambda seconds: time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime(seconds))
    out = {}
    for channelId, items in guide.items():
        key = 'samsung.it.%s' % channelId
        if key not in exported:
            continue
        out[key] = [dict({'start': stamp(start), 'stop': stamp(stop), 'title': plainText(program['title'])},
                         **({'description': plainText(program['description'])} if program.get('description') else {}),
                         **({'image': program['icon']} if program.get('icon') else {}))
                    for start, stop, program in items]
    return {'version': VERSION, 'epg': out}


def handle(route, port):
    """Answer one IPTV Manager call. Returns True when it was ours."""
    if not (route.endswith(CHANNELS_ROUTE) or route.endswith(EPG_ROUTE)):
        return False
    if port is None:
        warn('iptv call without a port')
        return True
    import xbmcaddon
    import xbmcvfs
    from resources.lib.catalog import StvAddon
    store = os.path.join(xbmcvfs.translatePath(xbmcaddon.Addon(ADDON_ID).getAddonInfo('profile')), STORE)
    data = lambda: StvAddon().data
    outcome = {}

    def produce():
        started = time.time()
        if route.endswith(CHANNELS_ROUTE):
            result = channels(data, store, existingChannels())
            outcome['message'] = 'iptv served %d channels in %.1fs' % (len(result['streams']), time.time() - started)
        else:
            result = epg(data, store)
            outcome['message'] = 'iptv served guide for %d channels in %.1fs' % (len(result['epg']), time.time() - started)
        return result

    try:
        send(port, produce)
    finally:
        xbmc.log(msg=''.join([ADDON_ID, ' : ', outcome.get('message', 'iptv failed to serve ' + route)]), level=xbmc.LOGINFO)
    return True
