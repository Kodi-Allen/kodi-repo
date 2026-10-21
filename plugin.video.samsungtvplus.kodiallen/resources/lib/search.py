# -*- coding: utf-8 -*-
"""Samsung TV Plus search window above Home: channel names, what they show now, their group."""
import threading
import time

import xbmc
import xbmcgui

from resources.lib import context
from resources.lib import nav

FIELD = 400
GRID = 500
MAX_RESULTS = 120


class StvSearch(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        super(StvSearch, self).__init__(*args, **kwargs)
        self.addon = None
        self.items = []
        self.query = ''
        self.navbar = None
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
        self.setProperty('stv.fallback', self.addon.addonIcon)
        self.setProperty('stv.search.status', '')
        self.setProperty('stv.search.region', self.addon.regionName)
        self.setProperty('stv.search.field', self.query or self.addon.localLang(30203) or 'Search')
        self.setFocusId(FIELD)

    def onClick(self, controlId):
        if controlId == FIELD:
            query = xbmcgui.Dialog().input(self.addon.localLang(30203) or 'Search', self.query).strip()
            # Cancel and an empty OK both leave the window as it was.
            if not query:
                return
            self.query = query
            self.setProperty('stv.search.field', query)
            self.setProperty('stv.search.status', self.addon.localLang(30072) or 'Loading…')
            self.searches += 1
            threading.Thread(target=self.search, args=(query, self.searches), daemon=True).start()
        elif controlId == GRID:
            position = self.getControl(GRID).getSelectedPosition()
            if not 0 <= position < len(self.items):
                return
            url, item, isFolder = self.items[position]
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
            needle = query.lower()
            data = self.addon.data
            for channel in data.channels.values():
                if len(items) >= MAX_RESULTS:
                    break
                current, _ = data.nowNext(channel['id'])
                fields = [channel['name'], channel['group'], current[2]['title'] if current else '']
                if any(needle in field.lower() for field in fields):
                    items.append(self.addon.channelItem(channel))
            if not items:
                status = self.addon.localLang(30073) or 'No titles available.'
        except Exception as err:
            # API exception messages may contain URLs; log only the type.
            self.addon.note('STV-UI search failed: ' + type(err).__name__, xbmc.LOGERROR)
            status = self.addon.localLang(30074) or 'Could not load titles.'
        with self.lock:
            # A later search replaces this one; a closed window is left alone.
            if self.closed or number != self.searches:
                return
            self.items = items
            grid = self.getControl(GRID)
            grid.reset()
            grid.addItems([item for _, item, _ in items])
            self.setProperty('stv.search.status', status)
            if items:
                self.setFocusId(GRID)
            self.addon.note('STV-UI search: %d results in %.2f s' % (len(items), time.monotonic() - started))


def showSearch(addon, idle=None):
    """Run the search window over Home; returns (navbar, abandoned)."""
    window = StvSearch('StvSearch.xml', addon.homeDir, 'Default', '1080i')
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
                addon.note('STV-UI search abandoned for window %d' % current)
                window.closed = abandoned = True
                break
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
