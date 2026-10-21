# -*- coding: utf-8 -*-
"""Samsung TV Plus channel data and programme guide for one region.

Both come from Matt Huisman's published Samsung TV Plus data, the same
source samsung-tvplus-for-channels and SlyGuy's add-on read:

    .channels.json.gz    every region's channels: name, group, logo,
                         description, Samsung's number, the next few
                         programme titles, and a licence URL for the few
                         Widevine channels, which are left out: Samsung's
                         licence server serves Samsung devices only
    <region>.xml.gz      XMLTV for the region: titles, descriptions,
                         images, start and stop in UTC

Playback is jmp2.uk/<slug>, which redirects to the stream Samsung currently
serves for that channel. Each file is cached in the add-on's profile; when a
download fails the last good copy is used, so a short outage never empties
the channel list.
"""
import calendar
import gzip
import json
import os
import time
import xml.etree.ElementTree as ET

import requests

SOURCE = 'https://i.mjh.nz/SamsungTVPlus/'
PLAY = 'https://jmp2.uk/'
CHANNELS_TTL = 15 * 60      # the source is rebuilt several times an hour
GUIDE_TTL = 30 * 60
TIMEOUT = 20


class DataError(Exception):
    pass


def _cached(profile, name, ttl):
    """The file's bytes: fresh from the source, or the cached copy."""
    folder = os.path.join(profile, 'cache')
    path = os.path.join(folder, name)
    try:
        if time.time() - os.path.getmtime(path) < ttl:
            with open(path, 'rb') as handle:
                return handle.read()
    except OSError:
        pass
    try:
        response = requests.get(SOURCE + name, timeout=TIMEOUT, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        data = response.content
        gzip.decompress(data)                     # refuse a broken download
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(path + '.tmp', 'wb') as handle:
            handle.write(data)
        os.replace(path + '.tmp', path)
        return data
    except Exception as err:
        try:
            with open(path, 'rb') as handle:
                return handle.read()
        except OSError:
            raise DataError('%s: %s' % (name, type(err).__name__))


class Region(object):
    """One region's channels and guide."""

    def __init__(self, profile, region):
        self.profile = profile
        self.region = region
        app = json.loads(gzip.decompress(_cached(profile, '.channels.json.gz', CHANNELS_TTL)))
        self.slug = app.get('slug') or 'stvp-{id}'
        self.headers = app.get('headers') or {}
        raw = (app.get('regions') or {}).get(region, {}).get('channels') or {}
        self.channels = {}
        self.locked = 0
        for channelId, channel in sorted(raw.items(), key=lambda kv: (kv[1].get('chno') or 99999, kv[0])):
            if channel.get('license_url'):
                self.locked += 1
                continue
            self.channels[channelId] = {
                'id': channelId, 'name': channel.get('name') or channelId, 'group': channel.get('group') or '',
                'logo': channel.get('logo') or '', 'description': channel.get('description') or '',
                'chno': channel.get('chno'), 'titles': channel.get('programs') or []}
        self._guide = None

    def playUrl(self, channelId):
        return PLAY + self.slug.format(id=channelId)

    def groups(self):
        """Samsung's groups in the order its channel numbers give them."""
        seen = []
        for channel in self.channels.values():
            if channel['group'] and channel['group'] not in seen:
                seen.append(channel['group'])
        return seen

    def guide(self):
        """{channel id: [(start, stop, {title, description, icon})]}, sorted by start."""
        if self._guide is None:
            self._guide = {}
            try:
                root = ET.fromstring(gzip.decompress(_cached(self.profile, '%s.xml.gz' % self.region, GUIDE_TTL)))
            except DataError:
                return self._guide
            for programme in root.findall('programme'):
                start, stop = _epoch(programme.get('start')), _epoch(programme.get('stop'))
                channelId = programme.get('channel')
                if channelId not in self.channels or start is None or stop is None or stop <= start:
                    continue
                icon = programme.find('icon')
                self._guide.setdefault(channelId, []).append((start, stop, {
                    'title': programme.findtext('title') or '', 'description': programme.findtext('desc') or '',
                    'episode_title': '', 'icon': icon.get('src') if icon is not None else ''}))
            for items in self._guide.values():
                items.sort(key=lambda item: item[0])
        return self._guide

    def nowNext(self, channelId, now=None):
        """(now, next) programme dicts with their times, None where the guide has none."""
        now = time.time() if now is None else now
        current = following = None
        for start, stop, programme in self.guide().get(channelId) or []:
            if start <= now < stop:
                current = (start, stop, programme)
            elif start >= now and following is None:
                following = (start, stop, programme)
                break
        return current, following


def _epoch(stamp):
    """XMLTV time 'YYYYmmddHHMMSS +hhmm' as Unix time."""
    if not stamp or len(stamp) < 14:
        return None
    try:
        seconds = calendar.timegm(time.strptime(stamp[:14], '%Y%m%d%H%M%S'))
    except ValueError:
        return None
    offset = stamp[14:].strip()
    if len(offset) == 5 and offset[0] in '+-':
        sign = 1 if offset[0] == '+' else -1
        seconds -= sign * (int(offset[1:3]) * 3600 + int(offset[3:5]) * 60)
    return seconds
