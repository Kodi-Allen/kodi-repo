# -*- coding: utf-8 -*-
"""Joyn search window above Home, searching the current region's catalogue."""
import threading
import time

import xbmc
import xbmcgui

from resources.lib import catalog
from resources.lib import context
from resources.lib import nav
from resources.lib import series

FIELD = 400
GRID = 500
MAX_RESULTS = 120


class JoynSearch(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        super(JoynSearch, self).__init__(*args, **kwargs)
        self.addon = None
        self.items = []
        self.query = ''
        self.navbar = None
        self.seriesRequested = None
        self.closed = False
        self.started = False
        self.windowId = None
        self.searches = 0
        self.lock = threading.RLock()

    def onInit(self):
        self.windowId = xbmcgui.getCurrentWindowId()
        if self.started:
            return
        self.started = True
        self.setProperty('joyn.fallback', self.addon.addonIcon)
        self.setProperty('joyn.search.status', '')
        self.setProperty('joyn.search.region', self.addon.regionName)
        self.setProperty('joyn.search.field', self.query or self.addon.localLang(30215) or 'Search')
        self.setFocusId(FIELD)

    def onClick(self, controlId):
        if controlId == FIELD:
            query = xbmcgui.Dialog().input(self.addon.localLang(30215) or 'Search', self.query).strip()
            # Cancel and an empty OK both leave the window as it was.
            if not query:
                return
            self.query = query
            self.setProperty('joyn.search.field', query)
            self.setProperty('joyn.search.status', self.addon.localLang(30072) or 'Loading…')
            self.searches += 1
            threading.Thread(target=self.search, args=(query, self.searches), daemon=True).start()
        elif controlId == GRID:
            position = self.getControl(GRID).getSelectedPosition()
            if not 0 <= position < len(self.items):
                return
            url, item, isFolder = self.items[position]
            if isFolder:
                # The series opens above the results, which stay as they are.
                self.seriesRequested = (url, item)
            else:
                context.play(url, item)
        elif controlId == nav.SEARCH:
            self.setFocusId(FIELD)
        elif controlId in nav.ALL:
            self.navbar = controlId
            self.leave()

    def onAction(self, action):
        if action.getId() in (10, 92):  # Previous menu / back
            self.leave()

    def leave(self):
        with self.lock:
            if not self.closed:
                self.closed = True
                self.close()

    def search(self, query, number):
        started = time.monotonic()
        items, status = [], ''
        try:
            for asset in self.addon.api.search(query, first=MAX_RESULTS):
                if catalog.KINDS.get(asset.get('__typename')) in catalog.POSTER_KINDS:
                    self.addon.addAsset(asset, items)
            if not items:
                status = self.addon.localLang(30073) or 'No titles available.'
        except Exception as err:
            # API exception messages may contain URLs; log only the type.
            self.addon.note('JOYN-UI search failed: ' + type(err).__name__, xbmc.LOGERROR)
            status = self.addon.localLang(30074) or 'Could not load titles.'
        with self.lock:
            # A later search replaces this one; a closed window is left alone.
            if self.closed or number != self.searches:
                return
            self.items = items
            grid = self.getControl(GRID)
            grid.reset()
            grid.addItems([item for _, item, _ in items])
            self.setProperty('joyn.search.status', status)
            if items:
                self.setFocusId(GRID)
            self.addon.note('JOYN-UI search: %d results in %.2f s' % (len(items), time.monotonic() - started))


def showSearch(addon, idle=None):
    """Run the search window over Home; returns (navbar, abandoned)."""
    window = JoynSearch('JoynSearch.xml', addon.homeDir, 'Default', '1080i')
    window.addon = addon
    abandoned = False
    try:
        window.show()
        monitor = xbmc.Monitor()
        while not window.closed:
            if nav.stopping():
                break
            if idle is not None:
                idle()
            # Kodi's Home key leaves this window behind; let go of it then.
            current = xbmcgui.getCurrentWindowId()
            if window.windowId and current not in (window.windowId, 12005, 12006):
                addon.note('JOYN-UI search abandoned for window %d' % current)
                window.closed = abandoned = True
                break
            if window.seriesRequested:
                url, item = window.seriesRequested
                window.seriesRequested = None
                if series.showSeries(addon, url, item, idle):
                    window.closed = abandoned = True
                    break
                continue
            if nav.wait(monitor, 0.25):
                break
    finally:
        # Kodi stopping the service waits for it on the GUI thread, which
        # close() needs too; the windows go with Kodi then.
        if nav.stopping():
            window.closed = True
        else:
            window.leave()
        navbar = window.navbar
        del window
    return navbar, abandoned
