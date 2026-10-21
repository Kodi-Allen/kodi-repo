# -*- coding: utf-8 -*-
"""The add-on object every page shares, and channels as Kodi list items."""
import json
import os
import re
import time
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib import routing
from resources.lib.data import Region

ADDON_ID = 'plugin.video.samsungtvplus.kodiallen'
ROOT = 'plugin://%s/' % ADDON_ID
REGION = 'it'              # the one region so far; data and settings are region-ready
PROPERTY = 'stv.channel'

_FALLBACK = {}


def fallbackString(stringId):
    """The English text of a string Kodi has not loaded yet.

    Kodi reads an add-on's strings at start-up or when its installer puts
    the add-on in place; files copied in between leave new ids empty.
    """
    if not _FALLBACK:
        path = os.path.join(xbmcaddon.Addon(ADDON_ID).getAddonInfo('path'), 'resources', 'language',
                            'resource.language.en_gb', 'strings.po')
        try:
            with open(path, 'r') as handle:
                for match in re.finditer(r'msgctxt "#(\d+)"\nmsgid "(.*)"', handle.read()):
                    _FALLBACK[int(match.group(1))] = match.group(2).replace('\\"', '"')
        except (IOError, OSError):
            _FALLBACK[0] = ''
    return _FALLBACK.get(stringId, '')


def clock(seconds):
    return time.strftime('%H:%M', time.localtime(seconds))


class StvAddon(object):
    def __init__(self, region=None):
        self.addon = xbmcaddon.Addon(ADDON_ID)
        self.addonName = self.addon.getAddonInfo('name')
        self.homeDir = self.addon.getAddonInfo('path')
        self.profile = xbmcvfs.translatePath(self.addon.getAddonInfo('profile'))
        images = os.path.join(self.homeDir, 'resources', 'images')
        self.addonIcon = os.path.join(images, 'icon.png')
        self.addonFanart = os.path.join(images, 'fanart.jpg')
        self.region = region or REGION
        self.regionName = self.localLang(30201)
        self.router = routing.MediaRouter(self.addon)
        self._data = None

    # ------------------------------------------------------------ helpers

    @property
    def data(self):
        if self._data is None:
            self._data = Region(self.profile, self.region)
        return self._data

    def localLang(self, stringId):
        return self.addon.getLocalizedString(stringId) or fallbackString(stringId)

    def note(self, txt, level=None):
        xbmc.log(msg=''.join([ADDON_ID, ' : ', str(txt)]),
                 level=xbmc.LOGINFO if level is None else level)

    def debug(self, txt):
        xbmc.log(msg=''.join([ADDON_ID, ' : ', str(txt)]), level=xbmc.LOGDEBUG)

    def mediaUrl(self, url):
        """Route a stream URL through the Italian relay when chosen."""
        return self.router.route(url)

    def url(self, mode, **query):
        query = dict((key, value) for key, value in query.items() if value not in (None, ''))
        query['mode'] = mode
        return ROOT + '?' + urllib.parse.urlencode(sorted(query.items()))

    # --------------------------------------------------------- favourites

    def _favouritesPath(self):
        return os.path.join(self.profile, 'favourites.json')

    def favourites(self):
        try:
            with open(self._favouritesPath(), 'r') as handle:
                ids = json.load(handle)
            return [channelId for channelId in ids if isinstance(channelId, str)]
        except (IOError, OSError, ValueError):
            return []

    def toggleFavourite(self, channelId):
        ids = self.favourites()
        added = channelId not in ids
        ids = ids + [channelId] if added else [i for i in ids if i != channelId]
        if not os.path.isdir(self.profile):
            os.makedirs(self.profile)
        with open(self._favouritesPath() + '.tmp', 'w') as handle:
            json.dump(ids, handle)
        os.replace(self._favouritesPath() + '.tmp', self._favouritesPath())
        return added

    # -------------------------------------------------------------- items

    def channelItem(self, channel, now=None):
        """(url, ListItem, isFolder) for a channel with what is on now and next."""
        current, following = self.data.nowNext(channel['id'], now)
        item = xbmcgui.ListItem(channel['name'], offscreen=True)
        still = (current[2].get('icon') if current else '') or ''
        art = {'icon': channel['logo'], 'thumb': channel['logo'], 'clearlogo': channel['logo'],
               'poster': channel['logo'], 'landscape': still or channel['logo'], 'fanart': still or self.addonFanart}
        item.setArt(art)
        tag = item.getVideoInfoTag()
        tag.setTitle(channel['name'])
        tag.setGenres([channel['group']] if channel['group'] else [])
        plot = []
        if current:
            start, stop, programme = current
            item.setLabel2(programme['title'])
            item.setProperty('stv.now', programme['title'])
            item.setProperty('stv.when', '%s – %s' % (clock(start), clock(stop)))
            item.setProperty('stv.progress', str(int(100 * (time.time() - start) / max(1, stop - start))))
            plot.append('[B]%s – %s  %s[/B]' % (clock(start), clock(stop), programme['title']))
            if programme.get('description'):
                plot.append(programme['description'])
        if following:
            start, _, programme = following
            item.setProperty('stv.next', '%s  %s' % (clock(start), programme['title']))
            plot.append('%s %s  %s' % (self.localLang(30411), clock(start), programme['title']))
        if not plot and channel['description']:
            plot.append(channel['description'])
        tag.setPlot('\n'.join(plot))
        item.setProperty('stv.group', channel['group'])
        item.setProperty(PROPERTY, json.dumps({'id': channel['id'], 'name': channel['name']}))
        item.setProperty('IsPlayable', 'true')
        return self.url('play', id=channel['id']), item, False
