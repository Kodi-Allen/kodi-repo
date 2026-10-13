# -*- coding: utf-8 -*-
"""Tubi series window: the seasons beside the active season's episodes."""
import re
import threading
import time
import urllib.parse

import xbmc
import xbmcgui

from resources.lib import context

SEASONS = 500
EPISODES = 600
PLAIN_SEASON = re.compile(r'^Season \d+$')
# How long a custom page may sit behind the loading cover. Normal loads take
# a few seconds; a dead route would otherwise hold the cover for minutes.
LOAD_DEADLINE = 20.0


class Cover(xbmcgui.WindowXMLDialog):
    """The add-on's loading screen, above the page the series came from."""
    cancelled = False

    def onAction(self, action):
        # Back gives up on the load; nothing else reaches the page below.
        if action.getId() in (10, 92):
            self.cancelled = True


def coverLoad(addon, load, tag, deadline=LOAD_DEADLINE):
    """Run load() behind the loading cover for at most `deadline` seconds.

    Returns (cover, result) with the cover still up, so the caller can open
    its window under the cover's closing fade. A failure, the deadline or
    Back closes the cover and returns None; the page below stays as it was.
    """
    cover = Cover('TubiLoading.xml', addon.homeDir, 'Default', '1080i')
    cover.show()
    outcome = {}

    def work():
        try:
            outcome['result'] = load()
        except Exception as err:
            outcome['error'] = err

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    monitor = xbmc.Monitor()
    started = time.monotonic()
    while worker.is_alive() and not cover.cancelled:
        if time.monotonic() - started > deadline or monitor.waitForAbort(0.1):
            break
    if 'result' in outcome and not cover.cancelled:
        return cover, outcome['result']
    cover.close()
    if cover.cancelled:
        addon.note('%s load cancelled' % tag)
        return None
    if 'error' in outcome:
        # API exception messages may contain URLs; log only the type.
        addon.note('%s load failed: %s' % (tag, type(outcome['error']).__name__), xbmc.LOGERROR)
        message = addon.localLang(30074) or 'Could not load titles.'
    else:
        addon.note('%s load timed out after %.0f s' % (tag, deadline), xbmc.LOGERROR)
        message = addon.localLang(30022) or 'Could not reach Tubi'
    xbmcgui.Dialog().notification(addon.addonName, message, xbmcgui.NOTIFICATION_ERROR)
    return None


class TubiSeries(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        super(TubiSeries, self).__init__(*args, **kwargs)
        self.addon = None
        self.seriesId = None
        self.title = ''
        self.art = {}
        self.year = 0
        self.plot = ''
        self.seasons = []
        self.episodes = {}
        self.active = 0
        self.loading = None
        self.closed = False
        self.started = False
        self.windowId = None
        self.lock = threading.RLock()

    def onInit(self):
        self.windowId = xbmcgui.getCurrentWindowId()
        if self.started:
            return
        self.started = True
        self.setProperty('tubi.series.title', self.title)
        self.setProperty('tubi.series.year', str(self.year or ''))
        self.setProperty('tubi.series.plot', self.plot)
        self.setProperty('tubi.series.fanart', self.art.get('fanart') or '')
        self.setProperty('tubi.series.fallback', self.addon.addonIcon)
        seasonWord = xbmc.getLocalizedString(20373)  # Season
        episodesWord = xbmc.getLocalizedString(20360)  # Episodes
        items = []
        for season in self.seasons:
            name = season.get('name') or ''
            if not name or PLAIN_SEASON.match(name):
                name = '%s %s' % (seasonWord, season.get('season'))
            item = xbmcgui.ListItem(name, '%d %s' % (len(season.get('episodes') or []), episodesWord),
                                    offscreen=True)
            items.append(item)
        self.getControl(SEASONS).addItems(items)
        self.showEpisodes(self.active)
        # One season needs no choice; start where the titles are.
        self.setFocusId(EPISODES if len(self.seasons) == 1 else SEASONS)

    def showEpisodes(self, index):
        """Make a loaded season the active one and list its episodes."""
        with self.lock:
            if self.closed:
                return
            self.active = index
            seasons = self.getControl(SEASONS)
            for position in range(seasons.size()):
                seasons.getListItem(position).setProperty('active', 'true' if position == index else '')
            episodes = self.getControl(EPISODES)
            episodes.reset()
            items = self.episodes.get(index) or []
            episodes.addItems([item for _, item, _ in items])
            self.setProperty('tubi.series.status', '' if items else (
                self.addon.localLang(30073) or 'No titles available.'))

    def loadSeason(self, index):
        items = episodeItems(self.addon, self.seriesId, self.seasons[index], self.title)
        with self.lock:
            if self.closed:
                return
            self.episodes[index] = items
            # A later SELECT of another season wins.
            if self.loading == index:
                self.loading = None
                self.showEpisodes(index)

    def onClick(self, controlId):
        if controlId == SEASONS:
            index = self.getControl(SEASONS).getSelectedPosition()
            if not 0 <= index < len(self.seasons):
                return
            if index in self.episodes:
                self.loading = None
                self.showEpisodes(index)
            elif self.loading != index:
                self.loading = index
                self.getControl(EPISODES).reset()
                self.setProperty('tubi.series.status', self.addon.localLang(30072) or 'Loading…')
                threading.Thread(target=self.loadSeason, args=(index,), daemon=True).start()
        elif controlId == EPISODES:
            position = self.getControl(EPISODES).getSelectedPosition()
            items = self.episodes.get(self.active) or []
            if 0 <= position < len(items):
                self.addon.note('TUBI-SERIES play season=%d episode=%d' % (self.active, position))
                context.play(items[position][0], items[position][1])

    def onAction(self, action):
        if action.getId() in (10, 92):  # Previous menu / back
            self.leave()

    def leave(self):
        with self.lock:
            if not self.closed:
                self.closed = True
                self.close()


def episodeItems(addon, seriesId, season, title):
    """The add-on's own episode items, with the line the episode list shows."""
    items = addon.episodeItems(seriesId, season, [], showTitle=title)
    for _, item, _ in items:
        tag = item.getVideoInfoTag()
        item.setProperty('code', 'S%02dE%02d' % (tag.getSeason(), tag.getEpisode()))
        details = []
        if tag.getDuration():
            details.append('%d min' % round(tag.getDuration() / 60.0))
        if tag.getYear():
            details.append(str(tag.getYear()))
        item.setProperty('details', '  ·  '.join(details))
    return items


def showSeries(addon, url, origin, idle=None):
    """Open a series from a custom page; return True when Kodi was left."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    seriesId = (query.get('url') or [''])[0]
    tag = origin.getVideoInfoTag()
    title = tag.getTVShowTitle() or origin.getLabel().replace(addon.localLang(30019), '')
    started = time.monotonic()
    addon.note('TUBI-SERIES loading %s (%s)' % (seriesId, title))

    def load():
        seasons = addon.seasonList(seriesId)
        return seasons, (episodeItems(addon, seriesId, seasons[0], title) if seasons else [])

    loaded = coverLoad(addon, load, 'TUBI-SERIES')
    if loaded is None:
        return False
    cover, (seasons, firstEpisodes) = loaded
    if not seasons:
        cover.close()
        xbmcgui.Dialog().notification(addon.addonName,
                                      addon.localLang(30074) or 'Could not load titles.')
        return False
    window = TubiSeries('TubiSeries.xml', addon.homeDir, 'Default', '1080i')
    window.addon = addon
    window.seriesId = seriesId
    window.title = title
    window.art = {'fanart': origin.getArt('fanart'), 'poster': origin.getArt('poster')}
    window.year = tag.getYear()
    window.plot = tag.getPlot()
    window.seasons = seasons
    window.episodes[0] = firstEpisodes
    addon.note('TUBI-SERIES ready: %d seasons, %d episodes in %.2f s' % (
        len(seasons), len(window.episodes[0]), time.monotonic() - started))
    abandoned = False
    # As for Home: the cover's closing fade lets the window activate under it.
    cover.close()
    try:
        window.show()
        monitor = xbmc.Monitor()
        while not window.closed:
            if idle is not None:
                idle()
            current = xbmcgui.getCurrentWindowId()
            if window.windowId and current not in (window.windowId, 12005, 12006):
                addon.note('TUBI-SERIES abandoned for window %d' % current)
                window.closed = abandoned = True
                break
            if monitor.waitForAbort(0.1):
                break
    finally:
        window.leave()
        del window
    return abandoned
