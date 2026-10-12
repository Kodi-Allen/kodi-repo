# -*- coding: utf-8 -*-
"""Tubi Movies window with progressively loaded server-curated rows."""
import threading
import time

import xbmc
import xbmcgui

from resources.lib.tubi_api import HOME_GROUP_ALL

ROW_CONTROLS = tuple(range(100, 350, 10))
MOVIE = 'v'


class TubiMovies(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        super(TubiMovies, self).__init__(*args, **kwargs)
        self.addon = None
        self.rowItems = {}
        self.navbar = None
        self.closed = False
        self.started = False
        self.windowId = None
        self.startedAt = None
        self.lock = threading.RLock()

    def onInit(self):
        self.windowId = xbmcgui.getCurrentWindowId()
        if self.started:
            return
        self.started = True
        self.startedAt = time.monotonic()
        self.setProperty('tubi.movies.fallback', self.addon.addonIcon)
        self.setProperty('tubi.movies.status', self.addon.localLang(30072) or 'Loading…')
        self.addon.note('TUBI-MOVIES window visible')
        # Keep the navbar responsive while one worker loads rows in server
        # order. No fan-out: the API route is already the slow part.
        threading.Thread(target=self.loadRows, daemon=True).start()

    def loadRows(self):
        try:
            rows, cursor = self.addon.api.homescreen(contentMode='movie')
        except Exception as err:
            self.failed('homescreen', err)
            return

        used = self.loadGroup(rows, 0)
        if self.closed:
            return
        self.addon.note('TUBI-MOVIES initial %d rows in %.2f s' % (
            used, time.monotonic() - self.startedAt))

        more = []
        if cursor:
            try:
                more, _ = self.addon.api.homescreen(cursor, HOME_GROUP_ALL, 'movie')
            except Exception as err:
                self.failed('remaining rows', err, keep=True)
                return
        total = min(len(ROW_CONTROLS), len(rows) + len(more))
        used = self.loadGroup(more, used, total)
        with self.lock:
            if self.closed:
                return
            self.setProperty('tubi.movies.status', '%d movie categories' % used)
        self.addon.note('TUBI-MOVIES complete %d rows in %.2f s' % (
            used, time.monotonic() - self.startedAt))

    def loadGroup(self, rows, used, total=None):
        for row in rows:
            if self.closed or used >= len(ROW_CONTROLS):
                return used
            rowId = row.get('id') or row.get('slug')
            items = []
            try:
                contents, _ = self.addon.api.container(rowId, contentMode='movie')
                for content in contents:
                    if self.closed:
                        return used
                    if content.get('type') == MOVIE and content.get('posterarts'):
                        self.addon.addContent(content, items)
            except Exception as err:
                self.addon.note('TUBI-MOVIES row %s failed: %s' % (
                    rowId, type(err).__name__), xbmc.LOGERROR)
            if not items:
                continue
            controlId = ROW_CONTROLS[used]
            with self.lock:
                if self.closed:
                    return used
                self.rowItems[controlId] = items
                self.getControl(controlId).addItems([item for _, item, _ in items])
                self.setProperty('tubi.movies.row%d' % controlId, row.get('title') or '')
                used += 1
                suffix = str(total) if total else '…'
                self.setProperty('tubi.movies.status', '%d / %s categories' % (used, suffix))
            self.addon.note('TUBI-MOVIES row %d: %s, %d movies at %.2f s' % (
                controlId, rowId, len(items), time.monotonic() - self.startedAt))
        return used

    def failed(self, stage, err, keep=False):
        self.addon.note('TUBI-MOVIES %s failed: %s' % (
            stage, type(err).__name__), xbmc.LOGERROR)
        with self.lock:
            if not self.closed:
                self.setProperty(
                    'tubi.movies.status',
                    ('Some categories could not be loaded.' if keep else
                     (self.addon.localLang(30074) or 'Could not load titles.')))

    def onClick(self, controlId):
        if controlId in self.rowItems:
            position = self.getControl(controlId).getSelectedPosition()
            items = self.rowItems[controlId]
            if not 0 <= position < len(items):
                return
            url, _, isFolder = items[position][:3]
            if not isFolder:
                self.addon.note('TUBI-MOVIES play row=%d position=%d' % (
                    controlId, position))
                xbmc.executebuiltin('PlayMedia("%s")' % url)
        elif controlId == 302:
            if ROW_CONTROLS[0] in self.rowItems:
                self.setFocusId(ROW_CONTROLS[0])
        elif controlId in (301, 303, 304, 305):
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


def showMovies(addon, idle=None):
    """Show Movies over Home; return (navbar target, abandoned)."""
    window = TubiMovies('TubiMovies.xml', addon.homeDir, 'Default', '1080i')
    window.addon = addon
    abandoned = False
    try:
        window.show()
        monitor = xbmc.Monitor()
        while not window.closed:
            if idle is not None:
                idle()
            current = xbmcgui.getCurrentWindowId()
            if window.windowId and current not in (window.windowId, 12005, 12006):
                addon.note('TUBI-MOVIES abandoned for window %d' % current)
                window.closed = abandoned = True
                break
            if monitor.waitForAbort(0.1):
                break
    finally:
        window.leave()
        navbar = window.navbar
        del window
    return navbar, abandoned
