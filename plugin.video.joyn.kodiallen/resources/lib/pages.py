# -*- coding: utf-8 -*-
"""Joyn's Series, Movies and Shows pages: their own rows, in their order.

Each page is one of Joyn's landing pages (/serien, /filme, /shows) with
the rows Joyn curates there. Rows load in a worker so the navbar stays
responsive; a row without posters is skipped, not shown empty.
"""
import threading
import time

import xbmc
import xbmcgui

from resources.lib import context
from resources.lib import nav
from resources.lib import series

ROW_CONTROLS = tuple(range(100, 420, 10))


class JoynPage(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        super(JoynPage, self).__init__(*args, **kwargs)
        self.addon = None
        self.entry = None
        self.rowItems = {}
        self.navbar = None
        self.seriesRequested = None
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
        path, heading = nav.PAGES[self.entry]
        self.setProperty('joyn.page.entry', str(self.entry))
        self.setProperty('joyn.page.heading', (self.addon.localLang(heading) or '').upper())
        self.setProperty('joyn.page.region', self.addon.regionName)
        self.setProperty('joyn.page.fallback', self.addon.addonIcon)
        self.setProperty('joyn.page.status', self.addon.localLang(30072) or 'Loading…')
        # The XML's default focus is Series; Movies and Shows start on their own entry.
        self.setFocusId(self.entry)
        self.addon.note('JOYN-PAGE %s visible' % path)
        threading.Thread(target=self.loadRows, args=(path, heading), daemon=True).start()

    def loadRows(self, path, heading):
        try:
            rows = self.addon.rows(self.addon.page(path), heroTitle=self.addon.localLang(heading))
        except Exception as err:
            # API exception messages may contain URLs; log only the type.
            self.addon.note('JOYN-PAGE %s failed: %s' % (path, type(err).__name__), xbmc.LOGERROR)
            with self.lock:
                if not self.closed:
                    self.setProperty('joyn.page.status', self.addon.localLang(30074) or 'Could not load titles.')
            return
        used = 0
        for title, _, items in rows:
            if self.closed or used >= len(ROW_CONTROLS):
                break
            controlId = ROW_CONTROLS[used]
            with self.lock:
                if self.closed:
                    return
                self.rowItems[controlId] = items
                self.getControl(controlId).addItems([item for _, item, _ in items])
                self.setProperty('joyn.page.row%d' % controlId, title)
                used += 1
        with self.lock:
            if self.closed:
                return
            self.setProperty('joyn.page.status', (self.addon.localLang(30076) % used) if used else
                             (self.addon.localLang(30073) or 'No titles available.'))
        self.addon.note('JOYN-PAGE %s: %d rows in %.2f s' % (path, used, time.monotonic() - self.startedAt))

    def onClick(self, controlId):
        if controlId in self.rowItems:
            position = self.getControl(controlId).getSelectedPosition()
            items = self.rowItems[controlId]
            if not 0 <= position < len(items):
                return
            url, item, isFolder = items[position]
            if isFolder:
                # The series opens above this page, which stays as it is.
                self.seriesRequested = (url, item)
            else:
                self.addon.note('JOYN-PAGE play row=%d position=%d' % (controlId, position))
                context.play(url, item)
        elif controlId == self.entry:
            if ROW_CONTROLS[0] in self.rowItems:
                self.setFocusId(ROW_CONTROLS[0])
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


def showPage(addon, entry, idle=None):
    """Show a catalogue page over Home; return (navbar target, abandoned)."""
    window = JoynPage('JoynPage.xml', addon.homeDir, 'Default', '1080i')
    window.addon = addon
    window.entry = entry
    abandoned = False
    try:
        window.show()
        monitor = xbmc.Monitor()
        while not window.closed:
            if nav.stopping():
                break
            if idle is not None:
                idle()
            current = xbmcgui.getCurrentWindowId()
            if window.windowId and current not in (window.windowId, 12005, 12006):
                addon.note('JOYN-PAGE abandoned for window %d' % current)
                window.closed = abandoned = True
                break
            if window.seriesRequested:
                url, item = window.seriesRequested
                window.seriesRequested = None
                if series.showSeries(addon, url, item, idle):
                    window.closed = abandoned = True
                    break
                continue
            if nav.wait(monitor, 0.1):
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
