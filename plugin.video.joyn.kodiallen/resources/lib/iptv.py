# -*- coding: utf-8 -*-
# IPTV Manager integration
#
# https://github.com/add-ons/service.iptv.manager/wiki/Integration
#
# IPTV Manager finds this add-on through the iptv.* settings, then calls
# plugin://plugin.video.joyn.kodiallen/iptv/channels?port=N and
# .../iptv/epg?port=N. Each call opens a TCP connection back to 127.0.0.1 on
# that port and writes a JSON document - JSON-STREAMS for the line-up,
# JSON-EPG for the guide. IPTV Manager keeps every add-on's channels apart
# and merges them into the one playlist IPTV Simple reads; nothing here
# touches IPTV Simple or another add-on's channels.
#
# iptv.enabled is off by default. Only the regions switched on for Kodi TV
# are exported, each as its own group, each in its own number range.
#
import json
import os
import re
import socket
import time

import xbmc

from resources.lib import lineup
from resources.lib import regions

VERSION = 1
TIMEOUT = 30
ADDON_ID = 'plugin.video.joyn.kodiallen'
CHANNELS_ROUTE = '/iptv/channels'
EPG_ROUTE = '/iptv/epg'
STORE = 'iptv.json'
# A plain plugin route, resolved when the channel is tuned. Nothing that
# expires (entitlement or licence tokens) ever goes into IPTV Simple's files.
PLAY = 'plugin://%s/?id=%s&mode=live&region=%s'


def send(port, produce):
    """Hand a JSON document back to IPTV Manager over its callback socket.

    IPTV Manager allows ten seconds for the add-on to connect and then waits
    as long as the connection stays open, so the socket is opened *before*
    the document is built.
    """
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(TIMEOUT)
    try:
        connection.connect(('127.0.0.1', int(port)))
        connection.settimeout(None)
        connection.sendall(json.dumps(produce()).encode('utf-8'))
    finally:
        connection.close()


CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
ANGLE = re.compile(r'[<>]')


def plainText(value):
    """Joyn's titles are plain text; drop what would break the XMLTV IPTV Manager writes."""
    if not value:
        return value
    return ANGLE.sub('', CONTROL.sub('', str(value))).strip()


def isoTime(stamp):
    return time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime(stamp))


def warn(message):
    xbmc.log(msg=''.join([ADDON_ID, ' : ', message]), level=xbmc.LOGWARNING)


def loadStore(path):
    """What the last line-ups left behind: channel numbers and streams, per region."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, 'r') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (IOError, OSError, ValueError) as err:
        warn('iptv store unreadable, starting afresh : %s' % err)
        return {}


def saveStore(path, data):
    """Write the store whole or not at all - a failure costs nothing now."""
    if not path:
        return
    try:
        folder = os.path.dirname(path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        temporary = path + '.tmp'
        with open(temporary, 'w') as handle:
            json.dump(data, handle)
        os.replace(temporary, path)
    except (IOError, OSError) as err:
        warn('iptv store not saved : %s' % err)


def assignNumbers(channelIds, numbers, numberRange, taken=()):
    """Give every channel a number in its region's range that stays with it.

    Joyn has no channel numbers, and numbering by position would move every
    channel along whenever Joyn reorders its line-up. So a channel keeps the
    number it was first given; a new channel takes the lowest free number
    after the highest one handed out so far; a channel Joyn drops keeps its
    number reserved in case it comes back. A number another source already
    uses in Kodi is never handed out. When the range is full a channel gets
    no number and is left out.
    """
    first, last = numberRange
    numbers = dict((key, value) for key, value in (numbers or {}).items()
                   if isinstance(value, int) and first <= value <= last)
    used = set(numbers.values()) | set(taken)
    following = max(list(numbers.values()) or [first - 1]) + 1
    for channelId in channelIds:
        if channelId in numbers:
            continue
        while following in used and following <= last:
            following += 1
        if following > last:
            warn('number range %d-%d is full, %s left out' % (first, last, channelId))
            continue
        numbers[channelId] = following
        used.add(following)
        following += 1
    return numbers


NORMALISE = re.compile(r'[^a-z0-9]+')
SUFFIXES = re.compile(r'(hd|sd|uhd|fhd|at|de|ch|austria|deutschland|schweiz)$')


def nameKey(name):
    """A channel name reduced to what two line-ups would agree on.

    'ORF 1 HD', 'ORF1' and 'orf1-at' all become 'orf1'; 'Das Erste HD' and
    'Das Erste' become 'daserste'.
    """
    key = NORMALISE.sub('', (name or '').lower().replace('ö', 'o').replace('ä', 'a').replace('ü', 'u'))
    for _ in range(2):
        stripped = SUFFIXES.sub('', key)
        if not stripped or stripped == key:
            break
        key = stripped
    return key


def existingChannels():
    """[(number, name)] of every TV channel Kodi has now."""
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'PVR.GetChannels',
               'params': {'channelgroupid': 'alltv', 'properties': ['channelnumber']}}
    try:
        result = json.loads(xbmc.executeJSONRPC(json.dumps(request))).get('result') or {}
    except (TypeError, ValueError):
        return []
    return [(channel.get('channelnumber'), channel.get('label') or '')
            for channel in result.get('channels') or []]


def foreign(existing, saved):
    """The existing channels that are not this add-on's own earlier export.

    Kodi shows a channel by number and name; the add-on's own ones are
    those it handed out itself, with the same number and name.
    """
    own = set((stream.get('preset'), stream.get('name'))
              for streams in (saved.get('streams') or {}).values() for stream in streams)
    return [(number, name) for number, name in existing if (number, name) not in own]


def overlaps(lineUp, existing):
    """{channel id: existing name} for Joyn channels Kodi already has under another source."""
    known = dict((nameKey(name), name) for _, name in existing if nameKey(name))
    found = {}
    for channelId, channel in lineUp.items():
        key = nameKey(channel['title'])
        if key and key in known:
            found[channelId] = known[key]
    return found


def review(addon):
    """List, per region, the Joyn channels Kodi already has under another source.

    Matching is by name, so it is shown for checking before the option to
    leave them out is switched on ('ATV' and Augsburg's 'a.tv' compare equal).
    """
    import xbmcgui
    from resources.lib.catalog import JoynAddon
    existing = existingChannels()
    lines = []
    for region in regions.ORDER:
        try:
            lineUp = lineup.channels(JoynAddon(region).api.live(hours=1))
        except Exception as err:
            lines.append('%s: %s' % (region.upper(), type(err).__name__))
            continue
        found = overlaps(lineUp, existing)
        lines.append('[B]Joyn %s[/B]: %d / %d' % (region.upper(), len(found), len(lineUp)))
        lines.extend('    %s  =  %s' % (lineUp[joynId]['title'], name) for joynId, name in sorted(found.items()))
        lines.append('')
    xbmcgui.Dialog().textviewer(addon.getLocalizedString(30526), '\n'.join(lines))


def channelId(region, joynId):
    """The id IPTV Manager and IPTV Simple know a channel by, unique across add-ons."""
    return 'joyn.%s.%s' % (region, joynId)


def regionStreams(region, api, saved, existing, skipExisting):
    """One region's JSON-STREAMS entries, or its saved ones when Joyn cannot answer."""
    try:
        lineUp = lineup.channels(api.live(hours=1))
    except Exception as err:  # the API raises JoynError; a transport error is no better
        if saved.get('streams', {}).get(region):
            warn('Joyn %s line-up unavailable, serving the saved one : %s' % (region, type(err).__name__))
            return saved['streams'][region]
        raise
    taken = [number for number, _ in existing if isinstance(number, int)]
    numbers = assignNumbers(list(lineUp), saved.get('numbers', {}).get(region),
                            regions.CHANNEL_RANGES[region], taken)
    saved.setdefault('numbers', {})[region] = numbers
    skipped = overlaps(lineUp, existing) if skipExisting else {}
    if skipped:
        xbmc.log(msg='%s : %s: %d channels already in Kodi left out' % (ADDON_ID, region, len(skipped)),
                 level=xbmc.LOGINFO)
    group = 'Joyn %s' % regions.REGIONS[region]['short']
    streams = []
    for joynId, channel in lineUp.items():
        if joynId in skipped or joynId not in numbers:
            continue
        streams.append({'id': channelId(region, joynId), 'name': plainText(channel['title']),
                        'logo': channel['logo'] or None, 'preset': numbers[joynId],
                        'stream': PLAY % (ADDON_ID, joynId, region), 'group': [group]})
    saved.setdefault('streams', {})[region] = streams
    return streams


def channels(apis, store, existing=(), skipExisting=False):
    """The JSON-STREAMS document for every exported region.

    A region Joyn cannot answer for keeps its last line-up. IPTV Manager
    turns a failed call into an empty playlist and IPTV Simple then removes
    the channels - much worse than a line-up a few hours old.
    """
    saved = loadStore(store)
    existing = foreign(existing, saved)
    streams = []
    for region, api in apis:
        try:
            streams.extend(regionStreams(region, api, saved, existing, skipExisting))
        except Exception as err:
            warn('Joyn %s line-up unavailable and none saved : %s' % (region, type(err).__name__))
    saveStore(store, saved)
    return {'version': VERSION, 'streams': streams}


def epg(apis, store):
    """The JSON-EPG document for the exported channels, as Joyn sends it."""
    saved = loadStore(store)
    guide = {}
    for region, api in apis:
        exported = set(stream['id'] for stream in saved.get('streams', {}).get(region) or [])
        try:
            streams = api.live(hours=24)
        except Exception as err:
            warn('Joyn %s guide unavailable : %s' % (region, type(err).__name__))
            continue
        for joynId, items in lineup.programmes(streams).items():
            key = channelId(region, joynId)
            if exported and key not in exported:
                continue
            programs = []
            for start, end, program in items:
                entry = {'start': isoTime(start), 'stop': isoTime(end),
                         'title': plainText(program['title'])}
                if program.get('episode_title'):
                    entry['subtitle'] = plainText(program['episode_title'])
                if program.get('description'):
                    entry['description'] = plainText(program['description'])
                programs.append(entry)
            guide[key] = programs
    return {'version': VERSION, 'epg': guide}


def exportedRegions(addon):
    return [region for region in regions.ORDER if addon.getSetting('iptv.%s' % region) == 'true']


def summarise(route, data, seconds):
    if 'streams' in data:
        what = '%d channels' % len(data['streams'])
    else:
        guide = data.get('epg') or {}
        what = '%d channels, %d programmes' % (len(guide), sum(len(v) for v in guide.values()))
    return 'iptv served %s : %s in %.1fs' % (route, what, seconds)


def handle(route, port):
    """Answer one IPTV Manager call. Returns True when it was ours."""
    if not (route.endswith(CHANNELS_ROUTE) or route.endswith(EPG_ROUTE)):
        return False
    if port is None:
        # Nothing to reply to - the call did not come from IPTV Manager
        warn('iptv call without a port')
        return True

    import xbmcaddon
    import xbmcvfs
    from resources.lib.catalog import JoynAddon
    settings = xbmcaddon.Addon(ADDON_ID)
    store = os.path.join(xbmcvfs.translatePath(settings.getAddonInfo('profile')), STORE)
    outcome = {}

    def produce():
        started = time.time()
        apis = [(region, JoynAddon(region).api) for region in exportedRegions(settings)]
        if route.endswith(CHANNELS_ROUTE):
            # Kodi's numbers are always read: no number in use is handed out again.
            data = channels(apis, store, existingChannels(),
                            settings.getSetting('iptv.skip_existing') == 'true')
        else:
            data = epg(apis, store)
        outcome['message'] = summarise(route, data, time.time() - started)
        return data

    try:
        send(port, produce)
    finally:
        xbmc.log(msg=''.join([ADDON_ID, ' : ', outcome.get('message', 'iptv failed to serve ' + route)]),
                 level=xbmc.LOGINFO)
    return True
