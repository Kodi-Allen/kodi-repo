# -*- coding: utf-8 -*-
# IPTV Manager integration
#
# https://github.com/add-ons/service.iptv.manager/wiki/Integration
#
# IPTV Manager finds this addon through the iptv.* settings, then calls
# plugin://plugin.video.tubitv/iptv/channels?port=N and .../iptv/epg?port=N.
# Each call is expected to open a TCP connection back to 127.0.0.1 on that
# port and write a JSON document - JSON-STREAMS for the channel line-up,
# JSON-EPG for the guide.
#
import html
import json
import os
import re
import socket
import time

import xbmc

from resources.lib.tubi_api import TubiApiError

VERSION = 1
TIMEOUT = 30

# The route Kodi hands us in sys.argv[0] for each of the two calls
CHANNELS_ROUTE = '/iptv/channels'
EPG_ROUTE = '/iptv/epg'


def send(port, produce):
    """Hand a JSON document back to IPTV Manager over its callback socket.

    IPTV Manager allows ten seconds for the addon to connect and then waits
    as long as the connection stays open, so the socket is opened *before*
    the document is built. Building the guide takes a request per batch of
    channels, which is far more than ten seconds' work - doing it first is
    what makes IPTV Manager give up and leave the guide empty.
    """
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(TIMEOUT)
    try:
        connection.connect(('127.0.0.1', int(port)))
        connection.settimeout(None)
        connection.sendall(json.dumps(produce()).encode('utf-8'))
    finally:
        connection.close()


TAG = re.compile(r'<[^<>]{0,120}>')
# XML 1.0 forbids most control characters outright
CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
ANGLE = re.compile(r'[<>]')


def plainText(value):
    """Turn Tubi's guide text into something safe to hand on.

    Tubi writes its titles and descriptions as HTML: entity-escaped, and
    occasionally with markup in them. What consumes this JSON turns it into
    XMLTV, and HTML entities are not XML entities - `&eacute;` is undefined
    in XML and takes the whole guide down with it, and a stray tag breaks
    the document just as thoroughly.

    So markup goes, entities are resolved to the characters they stand for,
    and anything left that could still be read as a tag is dropped. A bare
    angle bracket in prose is a fair price for a guide that parses.
    """
    if not value:
        return value
    text = str(value)
    # Entities can hide markup and markup can hide entities, so do both twice
    for _ in range(2):
        text = TAG.sub('', text)
        text = html.unescape(text)
    text = CONTROL.sub('', text)
    return ANGLE.sub('', text).strip()


def firstImage(images, *keys):
    for key in keys:
        values = (images or {}).get(key)
        if values:
            return values[0]
    return None


def episodeOf(program):
    """An S00E00 label, when the programme carries both numbers."""
    season = program.get('season_number')
    episode = program.get('episode_number')
    if not season or not episode:
        return None
    return 'S%02dE%02d' % (int(season), int(episode))


def warn(message):
    xbmc.log(msg=''.join(['plugin.video.tubitv : ', message]), level=xbmc.LOGWARNING)


def loadStore(path):
    """What the last line-up left behind: channel numbers and the streams."""
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


def assignNumbers(channelIds, numbers):
    """Give every channel a number that stays with it.

    Tubi has no channel numbers, and numbering by position would move every
    channel along whenever Tubi adds or reorders one. So a channel keeps the
    number it was first given: the first line-up is numbered in Tubi's order,
    a new channel goes on the end, and the number of one Tubi drops stays
    reserved in case it comes back.
    """
    numbers = dict((key, value) for key, value in (numbers or {}).items()
                   if isinstance(value, int))
    following = max(list(numbers.values()) or [0]) + 1
    for channelId in channelIds:
        if channelId not in numbers:
            numbers[channelId] = following
            following += 1
    return numbers


def channels(api, playPath, store=None):
    """The JSON-STREAMS document for Tubi's linear channels.

    Logos go across as Tubi's own URLs. They are public, never expire and
    load from anywhere, whereas a signed relay URL would expire inside the
    playlists IPTV Manager and IPTV Simple keep.

    If Tubi cannot be reached the last line-up is served again. IPTV Manager
    turns a failed call into an empty playlist, and IPTV Simple then removes
    every channel - a much worse outcome than a line-up a few hours old. The
    streams are plugin paths resolved at play time, so they cannot go stale.
    """
    saved = loadStore(store)
    try:
        lineUp, groups = api.liveChannels(allGroups=True)
    except TubiApiError as err:
        if not saved.get('streams'):
            raise
        warn('Tubi line-up unavailable, serving the saved one : %s' % err)
        return {'version': VERSION, 'streams': saved['streams']}

    numbers = assignNumbers([str(channel.get('id')) for channel in lineUp],
                            saved.get('numbers'))
    streams = []
    for channel in lineUp:
        channelId = str(channel.get('id'))
        streams.append({'id': channelId,
                        'name': plainText(channel.get('title')),
                        'logo': firstImage(channel.get('images'),
                                           'thumbnail', 'poster', 'landscape'),
                        'preset': numbers[channelId],
                        'stream': playPath % channelId,
                        'group': groups.get(channelId) or []})
    saveStore(store, {'numbers': numbers, 'streams': streams})
    return {'version': VERSION, 'streams': streams}


def epg(api, channelIds):
    """The JSON-EPG document for the given channels.

    Tubi timestamps its programmes in ISO-8601 UTC already, which is what
    IPTV Manager wants, so they go across untouched. A batch that fails is
    skipped rather than abandoning the whole guide.
    """
    guide = {}
    for row in api.liveProgramming(channelIds, tolerant=True):
        programs = []
        for program in row.get('programs') or []:
            entry = {'start': program.get('start_time'),
                     'stop': program.get('end_time'),
                     'title': plainText(program.get('title'))}
            if program.get('description'):
                entry['description'] = plainText(program['description'])
            if program.get('episode_title'):
                entry['subtitle'] = plainText(program['episode_title'])
            episode = episodeOf(program)
            if episode is not None:
                entry['episode'] = episode
            image = firstImage(program.get('images'), 'thumbnail', 'landscape', 'poster')
            if image is not None:
                entry['image'] = image
            tags = program.get('tags') or []
            if tags:
                entry['genre'] = plainText(tags[0])
            programs.append(entry)
        guide[str(row.get('content_id'))] = programs
    return {'version': VERSION, 'epg': guide}


def guideFor(api, store=None):
    try:
        lineUp, _ = api.liveChannels()
        channelIds = [str(channel.get('id')) for channel in lineUp]
    except TubiApiError as err:
        channelIds = [stream['id'] for stream in loadStore(store).get('streams') or []]
        if not channelIds:
            raise
        warn('Tubi line-up unavailable, guiding the saved one : %s' % err)
    return epg(api, channelIds)


def summarise(route, data, seconds):
    if 'streams' in data:
        what = '%d channels' % len(data['streams'])
    else:
        guide = data.get('epg') or {}
        what = '%d channels, %d programmes' % (len(guide),
                                               sum(len(v) for v in guide.values()))
    return 'iptv served %s : %s in %.1fs' % (route, what, seconds)


def handle(route, port, api, playPath, log=None, store=None):
    """Answer one IPTV Manager call. Returns True when it was ours.

    The work is deferred into a callable so the socket can be opened first -
    see send(). The store is a file that keeps the channel numbers and the
    last line-up between calls.
    """
    if route.endswith(CHANNELS_ROUTE):
        build = lambda: channels(api, playPath, store=store)
    elif route.endswith(EPG_ROUTE):
        build = lambda: guideFor(api, store=store)
    else:
        return False

    if port is None:
        # Nothing to reply to - the call did not come from IPTV Manager
        xbmc.log(msg='plugin.video.tubitv : iptv call without a port', level=xbmc.LOGWARNING)
        return True

    # Report what was handed over, so a guide that arrives empty can be told
    # apart from one that was never asked for.
    outcome = {}

    def produce():
        started = time.time()
        data = build()
        outcome['message'] = summarise(route, data, time.time() - started)
        return data

    try:
        send(port, produce)
    finally:
        message = outcome.get('message', ''.join(['iptv failed to serve ', route]))
        xbmc.log(msg=''.join(['plugin.video.tubitv : ', message]), level=xbmc.LOGINFO)
        if log is not None:
            log(message)
    return True
