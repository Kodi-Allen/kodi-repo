# -*- coding: utf-8 -*-
"""One native poster row, using the existing catalog items and plugin routes."""
import threading
import time

import xbmc
import xbmcgui

CAROUSEL_INTERVAL = 15.0


class TubiHome(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        super(TubiHome, self).__init__(*args, **kwargs)
        self.addon = None
        self.row = None
        self.items = []
        self.folder = None
        self.started = False
        self.closed = False
        self.lock = threading.Lock()
        self.windowId = None
        self.nextAdvance = time.monotonic() + CAROUSEL_INTERVAL

    def onInit(self):
        with self.lock:
            self.windowId = xbmcgui.getCurrentWindowId()
            self.nextAdvance = time.monotonic() + CAROUSEL_INTERVAL
        if self.started:
            return
        self.started = True
        self.setProperty('tubi.row', self.row.get('title') or '')
        self.setProperty('tubi.fallback', self.addon.addonIcon)
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

    def onClick(self, controlId):
        with self.lock:
            self.nextAdvance = time.monotonic() + CAROUSEL_INTERVAL
        if controlId != 100:
            return
        position = self.getControl(100).getSelectedPosition()
        if not 0 <= position < len(self.items):
            return
        url, _, isFolder = self.items[position]
        self.addon.note('TUBI-UI select %d (%s)' % (
            position, 'folder' if isFolder else 'playback'))
        if isFolder:
            # Hand folders back to Kodi's existing video navigation after
            # closing this window; never leave an inactive modal UI behind.
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
                self.closed = True
                self.close()

    def advanceIfIdle(self):
        with self.lock:
            if self.closed:
                return
            now = time.monotonic()
            # Suspend during loading, dialogs, playback and other windows.
            # Returning always starts a fresh interval; never catch up steps.
            if (len(self.items) < 2 or
                    xbmcgui.getCurrentWindowId() != self.windowId or
                    xbmcgui.getCurrentWindowDialogId() != 0 or
                    xbmc.Player().isPlaying() or self.getFocusId() != 100):
                self.nextAdvance = now + CAROUSEL_INTERVAL
                return
            if now >= self.nextAdvance:
                row = self.getControl(100)
                row.selectItem((row.getSelectedPosition() + 1) % len(self.items))
                self.nextAdvance = time.monotonic() + CAROUSEL_INTERVAL


def showHome(addon, row):
    window = TubiHome('TubiHome.xml', addon.homeDir, 'Default', '1080i')
    window.addon = addon
    window.row = row
    try:
        # This replaces doModal's wait, rather than starting timer threads.
        # Kodi dispatches input callbacks while waitForAbort releases Python.
        window.show()
        monitor = xbmc.Monitor()
        while not window.closed:
            window.advanceIfIdle()
            delay = max(0.1, min(1.0, window.nextAdvance - time.monotonic()))
            if monitor.waitForAbort(delay):
                break
    finally:
        with window.lock:
            window.closed = True
        window.close()
        folder = window.folder
        del window
    if folder:
        xbmc.executebuiltin('Container.Update("%s")' % folder)
