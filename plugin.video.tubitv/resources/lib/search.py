# -*- coding: utf-8 -*-
"""Tubi search window above Home, using the add-on's own search API."""
import threading
import time

import xbmc
import xbmcgui

from resources.lib import context
from resources.lib import series

FIELD = 400
GRID = 500
# Films and series with a poster, as in Home's rows; Live TV has its own place.
RESULT_TYPES = ('v', 's')
MAX_RESULTS = 120


class TubiSearch(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        super(TubiSearch, self).__init__(*args, **kwargs)
        self.addon = None
        self.items = []
        self.query = ''
        self.navbar = None
        self.seriesRequested = None
        self.relatedRequested = None
        self.related = None
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
        self.setProperty('tubi.fallback', self.addon.addonIcon)
        self.setProperty('tubi.search.status', '')
        self.setProperty('tubi.search.field', self.query or self.addon.localLang(30010) or 'Search')
        self.setFocusId(FIELD)
        if self.related:
            # Related titles of one title, shown as this page's results.
            self.setProperty('tubi.search.field', '%s: %s' % (
                self.addon.localLang(30034) or 'Related titles', self.related.get('title') or ''))
            self.setProperty('tubi.search.status', self.addon.localLang(30072) or 'Loading…')
            self.searches += 1
            threading.Thread(target=self.search, daemon=True,
                             args=(self.related['id'], self.searches, self.addon.api.related)).start()

    def onClick(self, controlId):
        if controlId == FIELD:
            query = xbmcgui.Dialog().input(self.addon.localLang(30010) or 'Search', self.query).strip()
            # Cancel and an empty OK both leave the window as it was.
            if not query:
                return
            self.query = query
            self.setProperty('tubi.search.field', query)
            self.setProperty('tubi.search.status', self.addon.localLang(30072) or 'Loading…')
            self.searches += 1
            threading.Thread(target=self.search, args=(query, self.searches), daemon=True).start()
        elif controlId == GRID:
            position = self.getControl(GRID).getSelectedPosition()
            if not 0 <= position < len(self.items):
                return
            url, item, isFolder = self.items[position][:3]
            if isFolder:
                # The series opens above the results, which stay as they are.
                self.seriesRequested = (url, item)
            else:
                context.play(url, item)
        elif controlId == 301:
            if self.related:
                # A related page sits above another page; Home means Home.
                self.navbar = controlId
            self.leave()
        elif controlId in (302, 303, 304):
            self.navbar = controlId
            self.leave()
        elif controlId == 305:
            self.setFocusId(FIELD)

    def onAction(self, action):
        if action.getId() in (10, 92):  # Previous menu / back
            self.leave()
        elif action.getId() == context.CONTEXT_MENU:
            try:
                if self.getFocusId() != GRID:
                    return
            except RuntimeError:
                return
            position = self.getControl(GRID).getSelectedPosition()
            if 0 <= position < len(self.items):
                self.relatedRequested = context.show(self.addon, self.items[position][1])

    def leave(self):
        with self.lock:
            if not self.closed:
                self.closed = True
                self.close()

    def search(self, query, number, fetch=None):
        started = time.monotonic()
        items, status = [], ''
        try:
            for content in (fetch or self.addon.api.search)(query):
                if len(items) >= MAX_RESULTS:
                    break
                if content.get('type') in RESULT_TYPES and content.get('posterarts'):
                    context.addContent(self.addon, content, items)
            if not items:
                status = self.addon.localLang(30073) or 'No titles available.'
        except Exception as err:
            # API exception messages may contain URLs; log only the type.
            self.addon.note('TUBI-UI search failed: ' + type(err).__name__, xbmc.LOGERROR)
            status = self.addon.localLang(30074) or 'Could not load titles.'
        with self.lock:
            # A later search replaces this one; a closed window is left alone.
            if self.closed or number != self.searches:
                return
            self.items = items
            grid = self.getControl(GRID)
            grid.reset()
            grid.addItems([item for _, item, _ in items])
            self.setProperty('tubi.search.status', status)
            if items:
                self.setFocusId(GRID)
            self.addon.note('TUBI-UI search: %d results in %.2f s' % (len(items), time.monotonic() - started))


def showSearch(addon, idle=None, related=None):
    """Run the search window over Home; returns (navbar, abandoned).

    With related, the {'id', 'title'} of a title, the page lists that
    title's related titles instead of waiting for a query.
    """
    window = TubiSearch('TubiSearch.xml', addon.homeDir, 'Default', '1080i')
    window.addon = addon
    window.related = related
    abandoned = False
    try:
        window.show()
        monitor = xbmc.Monitor()
        while not window.closed:
            if idle is not None:
                idle()
            # Kodi's Home key leaves this window behind; let go of it then.
            current = xbmcgui.getCurrentWindowId()
            if window.windowId and current not in (window.windowId, 12005, 12006):
                addon.note('TUBI-UI search abandoned for window %d' % current)
                window.closed = abandoned = True
                break
            if window.seriesRequested:
                url, item = window.seriesRequested
                window.seriesRequested = None
                if series.showSeries(addon, url, item, idle):
                    window.closed = abandoned = True
                    break
                continue
            if window.relatedRequested:
                related, window.relatedRequested = window.relatedRequested, None
                navbar, abandoned = showSearch(addon, idle, related=related)
                if abandoned:
                    window.closed = True
                    break
                if navbar:
                    window.navbar = navbar
                    window.leave()
                continue
            if monitor.waitForAbort(0.25):
                break
    finally:
        window.leave()
        navbar = window.navbar
        del window
    return navbar, abandoned
