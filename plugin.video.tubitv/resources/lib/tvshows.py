# -*- coding: utf-8 -*-
"""Tubi TV Shows window with progressively loaded server-curated rows."""
import threading
import time

import xbmc
import xbmcgui

from resources.lib import context
from resources.lib import search
from resources.lib import series
from resources.lib.tubi_api import HOME_GROUP_ALL

ROW_CONTROLS = tuple(range(100, 420, 10))
SERIES = 's'


class TubiTVShows(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        super(TubiTVShows, self).__init__(*args, **kwargs)
        self.addon = None
        self.rowItems = {}
        self.rowIds = {}
        self.seriesRequested = None
        self.navbar = None
        self.relatedRequested = None
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
        self.setProperty('tubi.tv.fallback', self.addon.addonIcon)
        self.addon.note('TUBI-TV window visible')
        self.setProperty('tubi.tv.status', self.addon.localLang(30072) or 'Loading…')
        # Keep the navbar responsive while one worker loads rows in server
        # order, as Movies does.
        threading.Thread(target=self.loadRows, daemon=True).start()

    def loadRows(self):
        try:
            rows, cursor = self.addon.api.homescreen(contentMode='tv')
        except Exception as err:
            self.failed('homescreen', err)
            return

        used = self.loadGroup(rows, 0)
        if self.closed:
            return
        self.addon.note('TUBI-TV initial %d rows in %.2f s' % (
            used, time.monotonic() - self.startedAt))

        more = []
        if cursor:
            try:
                more, _ = self.addon.api.homescreen(cursor, HOME_GROUP_ALL, 'tv')
            except Exception as err:
                self.failed('remaining rows', err, keep=True)
                return
        total = min(len(ROW_CONTROLS), len(rows) + len(more))
        used = self.loadGroup(more, used, total)
        with self.lock:
            if self.closed:
                return
            self.setProperty('tubi.tv.status', '%d TV categories' % used)
        self.addon.note('TUBI-TV complete %d rows in %.2f s' % (
            used, time.monotonic() - self.startedAt))

    def loadGroup(self, rows, used, total=None):
        for row in rows:
            if self.closed or used >= len(ROW_CONTROLS):
                return used
            rowId = row.get('id') or row.get('slug')
            # A row the server lists twice is shown once.
            if rowId in self.rowIds.values():
                continue
            items = []
            try:
                contents, _ = self.addon.api.container(rowId, contentMode='tv')
                for content in contents:
                    if self.closed:
                        return used
                    if content.get('type') == SERIES and content.get('posterarts'):
                        context.addContent(self.addon, content, items)
                        # Every title here is a series; show it without the suffix.
                        items[-1][1].setLabel(content.get('title') or '')
            except Exception as err:
                self.addon.note('TUBI-TV row %s failed: %s' % (
                    rowId, type(err).__name__), xbmc.LOGERROR)
            if not items:
                continue
            controlId = ROW_CONTROLS[used]
            with self.lock:
                if self.closed:
                    return used
                self.rowItems[controlId] = items
                self.rowIds[controlId] = rowId
                self.getControl(controlId).addItems([item for _, item, _ in items])
                self.setProperty('tubi.tv.row%d' % controlId, row.get('title') or '')
                used += 1
                suffix = str(total) if total else '…'
                self.setProperty('tubi.tv.status', '%d / %s categories' % (used, suffix))
            self.addon.note('TUBI-TV row %d: %s, %d series at %.2f s' % (
                controlId, rowId, len(items), time.monotonic() - self.startedAt))
        return used

    def failed(self, stage, err, keep=False):
        self.addon.note('TUBI-TV %s failed: %s' % (
            stage, type(err).__name__), xbmc.LOGERROR)
        with self.lock:
            if not self.closed:
                self.setProperty(
                    'tubi.tv.status',
                    ('Some categories could not be loaded.' if keep else
                     (self.addon.localLang(30074) or 'Could not load titles.')))

    def onClick(self, controlId):
        if controlId in self.rowItems:
            position = self.getControl(controlId).getSelectedPosition()
            items = self.rowItems[controlId]
            if not 0 <= position < len(items):
                return
            url, item, isFolder = items[position][:3]
            self.addon.note('TUBI-TV select row=%d position=%d' % (controlId, position))
            if isFolder:
                # The series opens above this window, which stays as it is.
                self.seriesRequested = (url, item)
            else:
                context.play(url, item)
        elif controlId == 303:
            if ROW_CONTROLS[0] in self.rowItems:
                self.setFocusId(ROW_CONTROLS[0])
        elif controlId in (301, 302, 304, 305):
            self.navbar = controlId
            self.leave()

    def onAction(self, action):
        if action.getId() in (10, 92):  # Previous menu / back
            self.leave()
        elif action.getId() == context.CONTEXT_MENU:
            try:
                focus = self.getFocusId()
            except RuntimeError:
                return
            items = self.rowItems.get(focus) or []
            position = self.getControl(focus).getSelectedPosition() if items else -1
            if 0 <= position < len(items):
                self.relatedRequested = context.show(self.addon, items[position][1])

    def leave(self):
        with self.lock:
            if not self.closed:
                self.closed = True
                self.close()


def showTVShows(addon, idle=None):
    """Show TV Shows over Home; return (navbar target, abandoned)."""
    window = TubiTVShows('TubiTVShows.xml', addon.homeDir, 'Default', '1080i')
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
                addon.note('TUBI-TV abandoned for window %d' % current)
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
                navbar, abandoned = search.showSearch(addon, idle, related=related)
                if abandoned:
                    window.closed = True
                    break
                # Another navbar page closes this one; its own entry stays here.
                if navbar and navbar != 303:
                    window.navbar = navbar
                    window.leave()
                continue
            if monitor.waitForAbort(0.1):
                break
    finally:
        window.leave()
        navbar = window.navbar
        del window
    return navbar, abandoned
