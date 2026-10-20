# -*- coding: utf-8 -*-
"""The add-on object every page shares, and Joyn assets as Kodi list items.

One JoynAddon belongs to one region: its API session, cache and network
route are that region's. The custom windows and the classic folders both
build their items here, so a title looks and opens the same in either.
"""
import hashlib
import json
import os
import re
import time
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib import regions
from resources.lib import routing
from resources.lib.joyn_api import JoynApi

ADDON_ID = 'plugin.video.joyn.kodiallen'
ROOT = 'plugin://%s/' % ADDON_ID

MOVIE, SERIES, EPISODE = 'movie', 'series', 'episode'
KINDS = {'Movie': MOVIE, 'Series': SERIES, 'Episode': EPISODE}
# Poster rows hold what opens or plays from a poster; clips, brands and
# teasers live in rows of their own shape on Joyn and are left out.
POSTER_KINDS = (MOVIE, SERIES)
# Image profiles Joyn's CDN serves. A profile the image was not cut for
# answers with a redirect, so the delivered URLs are kept where they fit.
POSTER = 'nextgen-web-heroportrait-243x365'
BACKDROP = 'nextgen-web-primarycut-1920x1080'
STILL = 'nextgen-web-livestill-503x283'
PAGE_TTL = 600            # a landing page is re-read after ten minutes
PROPERTY = 'joyn.asset'   # what a list item's page needs to open it again


def profiled(url, profile):
    """The same Joyn image in another profile ('.../profile:<name>')."""
    if not url or '/profile:' not in url:
        return url or ''
    return url.rsplit('/profile:', 1)[0] + '/profile:' + profile


def isPlus(asset):
    """Joyn+ only: marked so, or licensed for subscribers and nobody else."""
    licences = asset.get('licenseTypes') or []
    return 'PLUS' in (asset.get('markings') or []) or (bool(licences) and 'AVOD' not in licences)


_FALLBACK = {}


def fallbackString(stringId):
    """The English text of a string Kodi has not loaded.

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


class JoynAddon(object):
    def __init__(self, region=None):
        self.addon = xbmcaddon.Addon(ADDON_ID)
        self.addonName = self.addon.getAddonInfo('name')
        self.homeDir = self.addon.getAddonInfo('path')
        self.profile = xbmcvfs.translatePath(self.addon.getAddonInfo('profile'))
        images = os.path.join(self.homeDir, 'resources', 'images')
        self.addonIcon = os.path.join(images, 'icon.png')
        self.addonFanart = os.path.join(images, 'fanart.jpg')
        self.region = region if regions.valid(region) else regions.current(self.addon)
        self.regionName = self.localLang(regions.REGIONS[self.region]['name'])
        self.router = routing.MediaRouter(self.addon, prefix=self.region)
        self.api = JoynApi(self.region, self.profile,
                           routing.request_kwargs(self.addon, self.region), log=self.debug)

    # ------------------------------------------------------------ helpers

    def localLang(self, stringId):
        return self.addon.getLocalizedString(stringId) or fallbackString(stringId)

    def note(self, txt, level=None):
        xbmc.log(msg=''.join([ADDON_ID, ' : ', str(txt)]),
                 level=xbmc.LOGINFO if level is None else level)

    def debug(self, txt):
        xbmc.log(msg=''.join([ADDON_ID, ' : ', str(txt)]), level=xbmc.LOGDEBUG)

    def mediaUrl(self, url):
        """Route an HTTP(S) asset through the region's relay in custom mode."""
        return self.router.route(url)

    def url(self, mode, **query):
        query = dict((key, value) for key, value in query.items() if value not in (None, ''))
        query.update({'mode': mode, 'region': self.region})
        return ROOT + '?' + urllib.parse.urlencode(sorted(query.items()))

    def page(self, path):
        """A landing page's blocks, from a short-lived per-region cache.

        Plugin calls are separate processes; without the cache, opening a
        row as a folder would fetch its whole page again.
        """
        name = 'page-%s.json' % hashlib.sha1(path.encode('utf-8')).hexdigest()[:16]
        cache = regions.folder(self.profile, self.region, 'cache')
        if not os.path.isdir(cache):
            os.makedirs(cache)
        cached = os.path.join(cache, name)
        try:
            if time.time() - os.path.getmtime(cached) < PAGE_TTL:
                with open(cached, 'r') as handle:
                    return json.load(handle)
        except (IOError, OSError, ValueError):
            pass
        blocks = self.api.page(path)
        try:
            with open(cached + '.tmp', 'w') as handle:
                json.dump(blocks, handle)
            os.replace(cached + '.tmp', cached)
        except (IOError, OSError):
            pass
        return blocks

    # -------------------------------------------------------------- items

    def describe(self, asset, series=None):
        """A Joyn asset as the flat dict the pages and list items use."""
        kind = KINDS.get(asset.get('__typename'))
        portrait = ((asset.get('heroPortrait') or asset.get('heroPortraitImage') or {}).get('url') or
                    (asset.get('heroPortraitImage') or {}).get('urlCard'))
        primary = (asset.get('primaryImage') or {}).get('url') or (asset.get('image') or {}).get('url')
        landscape = asset.get('heroLandscapeImage') or {}
        hero = (asset.get('heroImageDesktop') or {}).get('url') or landscape.get('urlCard')
        if kind == EPISODE:
            poster = profiled(primary, STILL)
        else:
            poster = portrait or profiled(primary, POSTER)
        backdrop = landscape.get('urlLandscape1920x') or hero or profiled(primary, BACKDROP)
        video = asset.get('video') or {}
        genres = [genre.get('name') for genre in asset.get('genres') or [] if genre.get('name')]
        brands = [brand.get('title') for brand in asset.get('brands') or [] if brand.get('title')]
        season = asset.get('season') or {}
        logo = asset.get('artLogoImage') or {}
        return {'id': asset.get('id'), 'kind': kind, 'title': asset.get('title') or '',
                'path': asset.get('path') or '', 'plot': asset.get('description') or '',
                'poster': poster or '', 'fanart': backdrop or '', 'hero': hero or backdrop or '',
                # Rows give the logo one url, detail pages one per size.
                'logo': next((logo[key] for key in ('url', 'l', 'original') if logo.get(key)), ''),
                'year': asset.get('productionYear'), 'genres': genres, 'brand': ', '.join(brands),
                'age': (asset.get('ageRating') or {}).get('minAge'),
                'duration': video.get('duration'), 'videoId': video.get('id'),
                'season': season.get('seasonNumber') or season.get('number'),
                'episode': asset.get('number'),
                'series': (series or (asset.get('series') or {}).get('title') or ''),
                'plus': isPlus(asset)}

    def listItem(self, info):
        """(url, ListItem, isFolder) for a described asset."""
        label = info['title']
        if info['plus']:
            # Joyn+ titles stay visible, marked as possibly not playable.
            label = '%s [COLOR FFFFC400][Joyn+][/COLOR]' % label
        item = xbmcgui.ListItem(label, offscreen=True)
        art = {'poster': self.mediaUrl(info['poster']), 'thumb': self.mediaUrl(info['poster']),
               'fanart': self.mediaUrl(info['fanart']), 'landscape': self.mediaUrl(info['hero'])}
        if info['logo']:
            art['clearlogo'] = self.mediaUrl(info['logo'])
        item.setArt(art)
        tag = item.getVideoInfoTag()
        tag.setTitle(info['title'])
        if info['plot']:
            tag.setPlot(info['plot'])
        if info['genres']:
            tag.setGenres(info['genres'])
        if info['brand']:
            tag.setStudios([info['brand']])
        if info['year']:
            tag.setYear(int(info['year']))
        if info['age'] is not None:
            tag.setMpaa('FSK %s' % info['age'])
            # InfoTagVideo has no getter for it; the series page reads this.
            item.setProperty('joyn.age', 'FSK %s' % info['age'])
        if info['duration']:
            tag.setDuration(int(info['duration']))
        item.setProperty('joyn.plus', 'true' if info['plus'] else '')
        item.setProperty(PROPERTY, json.dumps({'id': info['id'], 'kind': info['kind'],
                                               'path': info['path'], 'title': info['title']}))
        if info['kind'] == SERIES:
            tag.setMediaType('tvshow')
            tag.setTvShowTitle(info['title'])
            return self.url('series', path=info['path']), item, True
        if info['kind'] == EPISODE:
            tag.setMediaType('episode')
            if info['series']:
                tag.setTvShowTitle(info['series'])
            if info['season']:
                tag.setSeason(int(info['season']))
            if info['episode']:
                tag.setEpisode(int(info['episode']))
        else:
            tag.setMediaType('movie')
        item.setProperty('IsPlayable', 'true')
        return self.url('play', id=info['id'], video=info['videoId']), item, False

    def addAsset(self, asset, items, series=None):
        """Append a poster-row asset; anything that cannot open is skipped."""
        info = self.describe(asset, series)
        if info['kind'] not in POSTER_KINDS + (EPISODE,) or not info['id']:
            return None
        if info['kind'] != EPISODE and not info['poster']:
            return None
        items.append(self.listItem(info))
        return info

    def rows(self, blocks, kinds=POSTER_KINDS, heroTitle=''):
        """(title, block id, [items]) for every block that holds posters.

        Joyn's hero row has no headline of its own; it is the page's lead
        and is shown under the page's name.
        """
        rows = []
        for block in blocks:
            items = []
            for asset in block.get('assets') or []:
                if KINDS.get(asset.get('__typename')) in kinds:
                    self.addAsset(asset, items)
            if items:
                title = block.get('headline') or (heroTitle if block.get('__typename') == 'HeroLane' else '')
                rows.append((title, block.get('id'), items))
        return rows

    # ------------------------------------------------------------- series

    def seasonList(self, path):
        """The series and its seasons: [{'id', 'number', 'count', 'name'}]."""
        series = self.api.series(path)
        seasons = []
        for season in sorted(series.get('allSeasons') or [], key=lambda s: s.get('number') or 9999):
            seasons.append({'id': season.get('id'), 'number': season.get('number'),
                            'count': season.get('numberOfEpisodes') or len(season.get('episodes') or []),
                            'plus': isPlus(season)})
        return series, seasons

    def episodeItems(self, season, title):
        items = []
        # Joyn lists some seasons newest first; the episode list counts up.
        episodes = sorted(self.api.episodes(season['id']), key=lambda episode: episode.get('number') or 0)
        for episode in episodes:
            info = self.addAsset(episode, items, series=title)
            if info is not None and not info['season']:
                items[-1][1].getVideoInfoTag().setSeason(int(season['number'] or 0))
        return items
