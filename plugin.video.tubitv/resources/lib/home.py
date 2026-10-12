# -*- coding: utf-8 -*-
"""One native poster row, using the existing catalog items and plugin routes."""
import os
import threading
import time

import xbmc
import xbmcgui

from resources.lib import movies
from resources.lib import search
from resources.lib import series
from resources.lib import tvshows

CAROUSEL_INTERVAL = 15.0
FEATURED_INTERVAL = 10.0
# Navbar 304 opens the add-on's own route through the folder path in
# onClick; 301 stays here, while 302, 303 and 305 open custom windows.
NAVBAR = {304: 'plugin://plugin.video.tubitv/?mode=GC&url=live'}
MOVIES = 302
TVSHOWS = 303
SEARCH = 305
ROOT = 'plugin://plugin.video.tubitv/'
# Rows 2-4 below Most Popular: the next poster rows of Tubi's own home, in
# its order. Only these container types hold plain films and series.
MORE_ROWS = (110, 120, 130)
POSTER_ROW_TYPES = ('regular', 'genesis')


class TubiHome(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        super(TubiHome, self).__init__(*args, **kwargs)
        self.addon = None
        self.row = None
        self.items = []
        self.rowItems = {}
        self.folder = None
        self.leave = False
        self.moviesRequested = False
        self.tvRequested = False
        self.searchRequested = False
        self.seriesRequested = None
        self.started = False
        self.closed = False
        self.lock = threading.RLock()
        self.windowId = None
        self.nextAdvance = time.monotonic() + CAROUSEL_INTERVAL
        # Featured pair: cards 201/202 show items [index] and [index + 1].
        self.featured = []
        self.featuredIndex = 0
        self.featuredDirection = 1
        self.featuredHeld = False
        self.nextFeatured = time.monotonic() + FEATURED_INTERVAL
        self.focusMoved = False

    def onInit(self):
        with self.lock:
            self.windowId = xbmcgui.getCurrentWindowId()
            self.focusMoved = False
            self.nextAdvance = time.monotonic() + CAROUSEL_INTERVAL
        if self.started:
            return
        # A regular Home start also discards an abandoned navbar return.
        xbmcgui.Window(10000).clearProperty('tubitv.return.home')
        self.started = True
        self.setProperty('tubi.row', self.row.get('title') or '')
        self.setProperty('tubi.fallback', self.addon.addonIcon)
        self.setProperty('tubi.logo', os.path.join(self.addon.homeDir, 'resources', 'images', 'logo.png'))
        self.setProperty('tubi.status', self.addon.localLang(30072) or 'Loading…')
        self.addon.note('TUBI-UI window opened')
        # A single load, not a refresh loop; Back remains usable during I/O.
        threading.Thread(target=self.loadRow, daemon=True).start()

    def loadRow(self):
        items = []
        try:
            contents, _ = self.addon.api.container(self.row.get('id') or self.row['slug'])
            for content in contents:
                if self.closed:
                    return
                self.addon.addContent(content, items)
            status = '' if items else (self.addon.localLang(30073) or
                                       'No titles available. Press Back to return.')
        except Exception as err:
            # API exception messages may contain URLs; log only the type.
            self.addon.note('TUBI-UI load failed: ' + type(err).__name__, xbmc.LOGERROR)
            items = []
            status = (self.addon.localLang(30074) or
                      'Could not load titles. Press Back and try again.')
        with self.lock:
            if self.closed:
                return
            self.items = items
            self.getControl(100).addItems([item for _, item, _ in items])
            if items:
                self.setFocusId(100)
            self.nextAdvance = time.monotonic() + CAROUSEL_INTERVAL
            self.setProperty('tubi.status', status)
            self.addon.note('TUBI-UI loaded %d items' % len(items))
        self.loadFeatured()
        self.loadMoreRows()

    def loadMoreRows(self):
        # One home request for the order, then each row as it arrives; a row
        # that fails or holds nothing usable leaves its slot to the next one.
        try:
            rows, _ = self.addon.api.homescreen()
        except Exception as err:
            self.addon.note('TUBI-UI home rows failed: ' + type(err).__name__, xbmc.LOGERROR)
            return
        slots = list(MORE_ROWS)
        skip = ('featured', self.row.get('id') or self.row.get('slug'))
        for row in rows:
            rowId = row.get('id') or row.get('slug')
            if not slots or self.closed:
                return
            if rowId in skip or row.get('type') not in POSTER_ROW_TYPES:
                continue
            items = []
            try:
                contents, _ = self.addon.api.container(rowId)
                for content in contents:
                    if self.closed:
                        return
                    # Films and series with a poster; anything else would not open.
                    if content.get('type') in ('v', 's') and content.get('posterarts'):
                        self.addon.addContent(content, items)
            except Exception as err:
                self.addon.note('TUBI-UI row %s failed: %s' % (rowId, type(err).__name__), xbmc.LOGERROR)
            if not items:
                continue
            with self.lock:
                if self.closed:
                    return
                slot = slots.pop(0)
                self.rowItems[slot] = items
                self.getControl(slot).addItems([item for _, item, _ in items])
                self.setProperty('tubi.row%d' % slot, row.get('title') or '')
                self.addon.note('TUBI-UI row %d: %s (%s), %d items' % (slot, rowId, row.get('type'), len(items)))

    def loadFeatured(self):
        # One request per window; a failure leaves the cards empty, not the row.
        featured = []
        try:
            # Title art comes in the same request; not every title has one.
            contents, _ = self.addon.api.container(
                'featured', extraImages=[('images[title_art]', 'w430h180_title')])
            for content in contents:
                if self.closed:
                    return
                self.addon.addContent(content, featured)
                art = (self.addon.firstOf(content.get('images') or {}, 'hero_16x9') or
                       self.addon.firstOf(content, 'hero_images', 'backgrounds') or '')
                titleArt = self.addon.firstOf(content.get('images') or {}, 'title_art') or ''
                featured[-1] += (art, str(content.get('year') or ''), titleArt)
        except Exception as err:
            self.addon.note('TUBI-UI featured failed: ' + type(err).__name__, xbmc.LOGERROR)
            featured = []
        with self.lock:
            if self.closed:
                return
            self.featured = featured
            self.nextFeatured = time.monotonic() + FEATURED_INTERVAL
            self.addon.note('TUBI-UI featured loaded: %d items' % len(featured))
            self.showFeatured()

    def showFeatured(self):
        titles = []
        for card in (0, 1):
            position = self.featuredIndex + card
            _, item, _, art, year, titleArt = (self.featured[position] if position < len(self.featured)
                                               else (None, None, None, '', '', ''))
            titles.append(item.getLabel() if item else '')
            self.setProperty('tubi.featured%d.title' % card, titles[-1])
            self.setProperty('tubi.featured%d.year' % card, year)
            self.setProperty('tubi.featured%d.art' % card, art)
            self.setProperty('tubi.featured%d.titleart' % card, titleArt)
        # Let Kodi cache the one hero the next step brings in (index + 2
        # forward, index - 1 backward), with the same turn as advanceFeatured.
        direction = self.featuredDirection
        if not 0 <= self.featuredIndex + direction <= len(self.featured) - 2:
            direction = -direction
        preload = self.featuredIndex + (2 if direction > 0 else -1)
        if len(self.featured) < 3 or not 0 <= preload < len(self.featured):
            preload = -1
        self.setProperty('tubi.featured.preload', self.featured[preload][3] if preload >= 0 else '')
        if self.featured:
            self.addon.note('TUBI-UI featured pair: %d, %s, %s, preload %d' % (
                self.featuredIndex, titles[0], titles[1], preload))

    def onClick(self, controlId):
        with self.lock:
            self.nextAdvance = time.monotonic() + CAROUSEL_INTERVAL
        items = self.items
        if controlId in (201, 202):
            # Featured cards show the current pair; reuse its row action.
            items = self.featured
            position = self.featuredIndex + controlId - 201
            self.addon.note('TUBI-UI featured select: card %d / item %d' % (controlId, position))
        elif controlId == 100:
            position = self.getControl(100).getSelectedPosition()
        elif controlId in self.rowItems:
            items = self.rowItems[controlId]
            position = self.getControl(controlId).getSelectedPosition()
        elif controlId == 301:  # Home: stay here, back to the poster row
            self.setFocusId(100)
            return
        elif controlId == MOVIES:
            self.moviesRequested = True
            return
        elif controlId == TVSHOWS:
            self.tvRequested = True
            return
        elif controlId == SEARCH:
            # The home loop opens it, so this callback returns at once.
            self.searchRequested = True
            return
        elif controlId in NAVBAR:
            # Arm only when default.py reaches the actual navbar target.
            xbmcgui.Window(10000).setProperty('tubitv.return.home', 'requested')
            items, position = [(NAVBAR[controlId], None, True)], 0
            self.addon.note('TUBI-UI navbar select: %d' % controlId)
            self.addon.note('RETURN requested')
        else:
            return
        if not 0 <= position < len(items):
            return
        url, item, isFolder = items[position][:3]
        self.addon.note('TUBI-UI select %d (%s)' % (
            position, 'folder' if isFolder else 'playback'))
        if isFolder and item is not None:
            # A series opens above Home from the home loop; Home stays as it is.
            self.seriesRequested = (url, item)
        elif isFolder:
            # Hand folders back to Kodi's existing video navigation after
            # closing this window; never leave an inactive modal UI behind.
            # BACK out of a series' outermost folder returns here, as from the navbar.
            xbmcgui.Window(10000).setProperty('tubitv.return.home', 'requested')
            with self.lock:
                self.folder = url
                self.closed = True
                self.close()
        else:
            xbmc.executebuiltin('PlayMedia("%s")' % url)

    def onAction(self, action):
        with self.lock:
            self.nextAdvance = time.monotonic() + CAROUSEL_INTERVAL
            if action.getId() in (10, 92):  # Parent directory / previous menu
                # The technical root revealed by this BACK is an intentional
                # exit, not another entry for the universal service owner.
                xbmcgui.Window(10000).setProperty('tubitv.return.home', 'exit')
                self.leave = True
                self.closed = True
                self.close()
            # Kodi moves focus between the cards itself and reports it through
            # onFocus first; a LEFT on 201 or RIGHT on 202 that moved nothing
            # pages the pair by one instead.
            elif action.getId() in (1, 2) and not self.focusMoved:  # Left / right
                try:
                    focus = self.getFocusId()
                except RuntimeError:
                    focus = 0
                if (focus, action.getId()) in ((201, 1), (202, 2)):
                    self.manualFeatured(-1 if focus == 201 else 1)
            self.focusMoved = False

    def onFocus(self, controlId):
        self.focusMoved = True

    def manualFeatured(self, direction):
        # One item per press, no wrap; automatic steps continue this way.
        index = self.featuredIndex + direction
        if not 0 <= index <= len(self.featured) - 2:
            return
        self.featuredIndex = index
        self.featuredDirection = direction
        self.addon.note('TUBI-UI featured manual: direction=%+d index=%d' % (direction, index))
        self.showFeatured()

    def advanceIfIdle(self):
        with self.lock:
            if self.closed:
                return
            now = time.monotonic()
            self.advanceFeatured(now)
            # Suspend during loading, dialogs, playback and other windows.
            # Returning always starts a fresh interval; never catch up steps.
            if (len(self.items) < 2 or
                    xbmcgui.getCurrentWindowId() != self.windowId or
                    xbmcgui.getCurrentWindowDialogId() not in (0, 9999) or
                    xbmc.Player().isPlaying() or self.getFocusId() != 100):
                self.nextAdvance = now + CAROUSEL_INTERVAL
                return
            if not self.closed and now >= self.nextAdvance:
                row = self.getControl(100)
                row.selectItem((row.getSelectedPosition() + 1) % len(self.items))
                self.nextAdvance = time.monotonic() + CAROUSEL_INTERVAL

    def advanceFeatured(self, now):
        # Two items are a single pair; there is nothing to move. Pushing the
        # deadline keeps the shared wait at its normal pace while idle.
        if len(self.featured) < 3:
            self.nextFeatured = now + FEATURED_INTERVAL
            return
        try:
            focus = self.getFocusId()
        except RuntimeError:
            focus = 0
        # Hold while a card or the navbar has focus or the window is not in front, then
        # start a full interval; never carry over the remaining time.
        onTop = focus in (201, 202) or 301 <= focus <= 305  # cards or navbar
        if (onTop or
                xbmcgui.getCurrentWindowId() != self.windowId or
                xbmcgui.getCurrentWindowDialogId() not in (0, 9999) or
                xbmc.Player().isPlaying()):
            if not self.featuredHeld:
                self.featuredHeld = True
                self.addon.note('TUBI-UI featured paused: ' + ('focus' if onTop else 'away'))
            self.nextFeatured = now + FEATURED_INTERVAL
            return
        if self.featuredHeld:
            self.featuredHeld = False
            self.nextFeatured = now + FEATURED_INTERVAL
            self.addon.note('TUBI-UI featured resumed')
            return
        if now < self.nextFeatured:
            return
        # Ping-pong: one item per step, turning only after the end pair stood.
        if not 0 <= self.featuredIndex + self.featuredDirection <= len(self.featured) - 2:
            self.featuredDirection = -self.featuredDirection
            self.addon.note('TUBI-UI featured direction: %+d' % self.featuredDirection)
        self.featuredIndex += self.featuredDirection
        self.nextFeatured = now + FEATURED_INTERVAL
        self.showFeatured()


def showHome(addon, row, idle=None, cover=None):
    window = TubiHome('TubiHome.xml', addon.homeDir, 'Default', '1080i')
    window.addon = addon
    window.row = row
    # A modal cover blocks Home activation. During its closing fade Kodi
    # permits Home underneath it, avoiding a visible technical-root frame.
    if cover is not None:
        cover.close()
    try:
        # This replaces doModal's wait, rather than starting timer threads.
        # Kodi dispatches input callbacks while waitForAbort releases Python.
        window.show()
        monitor = xbmc.Monitor()
        while not window.closed:
            if idle is not None:
                idle()
            # HOME or a switch to another Kodi section abandons the custom
            # window. Playback windows are allowed because Home must survive
            # underneath them for focus restore.
            current = xbmcgui.getCurrentWindowId()
            if window.windowId and current not in (window.windowId, 12005, 12006):
                addon.note('TUBI-UI home abandoned for window %d' % current)
                window.closed = True
                break
            if window.moviesRequested and window.windowId:
                window.moviesRequested = False
                navbar, abandoned = movies.showMovies(addon, idle)
                if abandoned:
                    window.closed = True
                    break
                if navbar:
                    window.onClick(navbar)
                else:
                    window.setFocusId(100)
                continue
            if window.seriesRequested and window.windowId:
                url, item = window.seriesRequested
                window.seriesRequested = None
                if series.showSeries(addon, url, item, idle):
                    window.closed = True
                    break
                continue
            if window.tvRequested and window.windowId:
                window.tvRequested = False
                navbar, abandoned = tvshows.showTVShows(addon, idle)
                if abandoned:
                    window.closed = True
                    break
                if navbar:
                    window.onClick(navbar)
                else:
                    window.setFocusId(100)
                continue
            # Only after onInit, which records this window's id.
            if window.searchRequested and window.windowId:
                window.searchRequested = False
                navbar, abandoned = search.showSearch(addon, idle)
                if abandoned:
                    window.closed = True
                    break
                if navbar:
                    window.onClick(navbar)
                continue
            window.advanceIfIdle()
            delay = max(0.1, min(1.0, min(window.nextAdvance, window.nextFeatured) - time.monotonic()))
            if monitor.waitForAbort(delay):
                break
    finally:
        with window.lock:
            if not window.closed:
                window.closed = True
                window.close()
        folder, leave = window.folder, window.leave
        del window
    if folder:
        xbmc.executebuiltin('Container.Update("%s")' % folder)
    # close() returns once Kodi shows the previous window again. BACK from
    # Home leaves Tubi: the plugin root it reveals is one step behind it.
    # The root reloads after close(); Back during that load cancels it and
    # goes a level too far. Read readiness atomically, as in the return shim.
    elif leave:
        there = 'Window.IsActive(videos) + String.IsEqual(Container.FolderPath,%s)' % ROOT
        ready = there + (' + Integer.IsGreater(Container.NumItems,0) + '
                         '!Window.IsVisible(busydialog) + !Window.IsVisible(busydialognocancel)')
        monitor = xbmc.Monitor()
        deadline = time.monotonic() + 15.0
        while True:
            isReady = xbmc.getCondVisibility(ready)
            if monitor.abortRequested():
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                addon.note('TUBI-UI exit: root readiness timeout')
                return
            if isReady:
                break
            if not xbmc.getCondVisibility(there) or monitor.waitForAbort(min(0.1, remaining)):
                return
        addon.note('TUBI-UI leave')
        xbmc.executebuiltin('Action(Back)')
