# -*- coding: utf-8 -*-
"""Joyn's start page: two featured cards over its first poster rows."""
import os
import threading
import time

import xbmc
import xbmcgui

from resources.lib import catalog
from resources.lib import context
from resources.lib import live
from resources.lib import nav
from resources.lib import pages
from resources.lib import regions
from resources.lib import search
from resources.lib import series

CAROUSEL_INTERVAL = 15.0
FEATURED_INTERVAL = 10.0
ROOT = catalog.ROOT
START_PAGE = '/'
# Rows 2-4 below the first: the next poster rows of Joyn's start page, in
# its order.
MORE_ROWS = (110, 120, 130)
# Joyn's hero row: the editorial titles the start page leads with.
HERO = 'HeroLane'
RETURN_HOME = 'joyn.return.home'


class JoynHome(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        super(JoynHome, self).__init__(*args, **kwargs)
        self.addon = None
        self.items = []
        self.rowItems = {}
        self.leave = False
        # The navbar page the home loop opens next, and a region to change to.
        self.pageRequested = None
        self.seriesRequested = None
        self.switchTo = None
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
        xbmcgui.Window(10000).clearProperty(RETURN_HOME)
        self.started = True
        self.setProperty('joyn.row', '')
        self.setProperty('joyn.region', self.addon.regionName)
        self.setProperty('joyn.fallback', self.addon.addonIcon)
        self.setProperty('joyn.logo', os.path.join(self.addon.homeDir, 'resources', 'images', 'logo.png'))
        self.setProperty('joyn.status', self.addon.localLang(30072) or 'Loading…')
        self.addon.note('JOYN-UI window opened (%s)' % self.addon.region)
        # A single load, not a refresh loop; Back remains usable during I/O.
        threading.Thread(target=self.loadRow, daemon=True).start()

    def loadRow(self):
        rows, featured = [], []
        try:
            blocks = self.addon.page(START_PAGE)
            for block in blocks:
                if block.get('__typename') == HERO:
                    for asset in block.get('assets') or []:
                        info = self.addon.addAsset(asset, featured)
                        if info is not None:
                            featured[-1] += (self.addon.mediaUrl(info['hero']), str(info['year'] or ''),
                                             self.addon.mediaUrl(info['logo']))
            rows = self.addon.rows([block for block in blocks if block.get('__typename') != HERO])
            status = '' if rows else (self.addon.localLang(30073) or
                                      'No titles available. Press Back to return.')
        except Exception as err:
            # API exception messages may contain URLs; log only the type.
            self.addon.note('JOYN-UI load failed: ' + type(err).__name__, xbmc.LOGERROR)
            rows = []
            status = (self.addon.localLang(30074) or
                      'Could not load titles. Press Back and try again.')
        title, _, items = rows[0] if rows else ('', None, [])
        with self.lock:
            if self.closed:
                return
            self.items = items
            self.getControl(100).addItems([item for _, item, _ in items])
            self.setProperty('joyn.row', title)
            if items:
                self.setFocusId(100)
            self.nextAdvance = time.monotonic() + CAROUSEL_INTERVAL
            self.setProperty('joyn.status', status)
            self.addon.note('JOYN-UI loaded %d items' % len(items))
            for slot, (rowTitle, rowId, rowItems) in zip(MORE_ROWS, rows[1:]):
                self.rowItems[slot] = rowItems
                self.getControl(slot).addItems([item for _, item, _ in rowItems])
                self.setProperty('joyn.row%d' % slot, rowTitle)
                self.addon.note('JOYN-UI row %d: %s, %d items' % (slot, rowId, len(rowItems)))
            self.featured = featured
            self.nextFeatured = time.monotonic() + FEATURED_INTERVAL
            self.addon.note('JOYN-UI featured loaded: %d items' % len(featured))
            self.showFeatured()

    def showFeatured(self):
        titles = []
        for card in (0, 1):
            position = self.featuredIndex + card
            _, item, _, art, year, titleArt = (self.featured[position] if position < len(self.featured)
                                               else (None, None, None, '', '', ''))
            titles.append(item.getLabel() if item else '')
            self.setProperty('joyn.featured%d.title' % card, titles[-1])
            self.setProperty('joyn.featured%d.year' % card, year)
            self.setProperty('joyn.featured%d.art' % card, art)
            self.setProperty('joyn.featured%d.titleart' % card, titleArt)
        # Let Kodi cache the one hero the next step brings in (index + 2
        # forward, index - 1 backward), with the same turn as advanceFeatured.
        direction = self.featuredDirection
        if not 0 <= self.featuredIndex + direction <= len(self.featured) - 2:
            direction = -direction
        preload = self.featuredIndex + (2 if direction > 0 else -1)
        if len(self.featured) < 3 or not 0 <= preload < len(self.featured):
            preload = -1
        self.setProperty('joyn.featured.preload', self.featured[preload][3] if preload >= 0 else '')
        if self.featured:
            self.addon.note('JOYN-UI featured pair: %d, %s, %s, preload %d' % (
                self.featuredIndex, titles[0], titles[1], preload))

    def onClick(self, controlId):
        with self.lock:
            self.nextAdvance = time.monotonic() + CAROUSEL_INTERVAL
        items = self.items
        if controlId in (201, 202):
            # Featured cards show the current pair; reuse its row action.
            items = self.featured
            position = self.featuredIndex + controlId - 201
            self.addon.note('JOYN-UI featured select: card %d / item %d' % (controlId, position))
        elif controlId == 100:
            position = self.getControl(100).getSelectedPosition()
        elif controlId in self.rowItems:
            items = self.rowItems[controlId]
            position = self.getControl(controlId).getSelectedPosition()
        elif controlId == nav.HOME:  # stay here, back to the poster row
            self.setFocusId(100)
            return
        elif controlId == nav.REGION:
            self.chooseRegion()
            return
        elif controlId in nav.ALL:
            # The home loop opens it, so this callback returns at once.
            self.pageRequested = controlId
            return
        else:
            return
        if not 0 <= position < len(items):
            return
        url, item, isFolder = items[position][:3]
        self.addon.note('JOYN-UI select %d (%s)' % (
            position, 'folder' if isFolder else 'playback'))
        if isFolder:
            # A series opens above Home from the home loop; Home stays as it is.
            self.seriesRequested = (url, item)
        else:
            context.play(url, item)

    def chooseRegion(self):
        """Pick AT, DE or CH; Home reopens in the chosen region's catalogue."""
        names = [self.addon.localLang(regions.REGIONS[region]['name']) for region in regions.ORDER]
        choice = xbmcgui.Dialog().select(self.addon.localLang(30217), names,
                                         preselect=regions.ORDER.index(self.addon.region))
        if choice < 0 or regions.ORDER[choice] == self.addon.region:
            return
        self.addon.addon.setSetting(regions.CURRENT, regions.ORDER[choice])
        self.addon.note('JOYN-UI region %s -> %s' % (self.addon.region, regions.ORDER[choice]))
        with self.lock:
            self.switchTo = regions.ORDER[choice]
            self.closed = True
            self.close()

    def onAction(self, action):
        with self.lock:
            self.nextAdvance = time.monotonic() + CAROUSEL_INTERVAL
            if action.getId() in (10, 92):  # Parent directory / previous menu
                # The technical root revealed by this BACK is an intentional
                # exit, not another entry for the universal service owner.
                xbmcgui.Window(10000).setProperty(RETURN_HOME, 'exit')
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
        self.addon.note('JOYN-UI featured manual: direction=%+d index=%d' % (direction, index))
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
        onTop = focus in (201, 202) or focus in nav.ALL  # cards or navbar
        if (onTop or
                xbmcgui.getCurrentWindowId() != self.windowId or
                xbmcgui.getCurrentWindowDialogId() not in (0, 9999) or
                xbmc.Player().isPlaying()):
            if not self.featuredHeld:
                self.featuredHeld = True
                self.addon.note('JOYN-UI featured paused: ' + ('focus' if onTop else 'away'))
            self.nextFeatured = now + FEATURED_INTERVAL
            return
        if self.featuredHeld:
            self.featuredHeld = False
            self.nextFeatured = now + FEATURED_INTERVAL
            self.addon.note('JOYN-UI featured resumed')
            return
        if now < self.nextFeatured:
            return
        # Ping-pong: one item per step, turning only after the end pair stood.
        if not 0 <= self.featuredIndex + self.featuredDirection <= len(self.featured) - 2:
            self.featuredDirection = -self.featuredDirection
            self.addon.note('JOYN-UI featured direction: %+d' % self.featuredDirection)
        self.featuredIndex += self.featuredDirection
        self.nextFeatured = now + FEATURED_INTERVAL
        self.showFeatured()


def openPage(addon, target, idle):
    """Open a navbar page over Home; return (navbar target, abandoned)."""
    if target == nav.LIVE:
        navbar, abandoned = live.showLive(addon, idle)
        # False: the guide could not open; stay where the focus was.
        return (navbar if navbar is not False else None), abandoned
    if target == nav.SEARCH:
        return search.showSearch(addon, idle)
    return pages.showPage(addon, target, idle)


def showHome(addon, idle=None, cover=None):
    """Run Home until it is left; returns the region to reopen it in, if any."""
    window = JoynHome('JoynHome.xml', addon.homeDir, 'Default', '1080i')
    window.addon = addon
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
            if nav.stopping():
                break
            if idle is not None:
                idle()
            # HOME or a switch to another Kodi section abandons the custom
            # window. Playback windows are allowed because Home must survive
            # underneath them for focus restore.
            current = xbmcgui.getCurrentWindowId()
            if window.windowId and current not in (window.windowId, 12005, 12006):
                addon.note('JOYN-UI home abandoned for window %d' % current)
                window.closed = True
                break
            if window.pageRequested and window.windowId:
                target, window.pageRequested = window.pageRequested, None
                navbar, abandoned = openPage(addon, target, idle)
                if abandoned:
                    window.closed = True
                    break
                # Another navbar entry chains on; Home itself means Home.
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
            window.advanceIfIdle()
            delay = max(0.1, min(1.0, min(window.nextAdvance, window.nextFeatured) - time.monotonic()))
            if nav.wait(monitor, delay):
                break
    finally:
        with window.lock:
            if not window.closed:
                window.closed = True
                # Kodi stopping the service waits for it on the GUI thread, which
                # close() needs too; the windows go with Kodi then.
                if not nav.stopping():
                    window.close()
        leave, switchTo = window.leave, window.switchTo
        del window
    if nav.stopping():
        return None
    if switchTo:
        return switchTo
    # close() returns once Kodi shows the previous window again. BACK from
    # Home leaves Joyn: the plugin root it reveals is one step behind it.
    # The root reloads after close(); Back during that load cancels it and
    # goes a level too far. Read readiness atomically, as in the return shim.
    if leave:
        there = 'Window.IsActive(videos) + String.IsEqual(Container.FolderPath,%s)' % ROOT
        ready = there + (' + Integer.IsGreater(Container.NumItems,0) + '
                         '!Window.IsVisible(busydialog) + !Window.IsVisible(busydialognocancel)')
        monitor = xbmc.Monitor()
        deadline = time.monotonic() + 15.0
        while True:
            isReady = xbmc.getCondVisibility(ready)
            if nav.stopping():
                return None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                addon.note('JOYN-UI exit: root readiness timeout')
                return None
            if isReady:
                break
            if not xbmc.getCondVisibility(there) or nav.wait(monitor, min(0.1, remaining)):
                return None
        addon.note('JOYN-UI leave')
        xbmc.executebuiltin('Action(Back)')
    return None
