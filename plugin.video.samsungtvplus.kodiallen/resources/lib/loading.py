# -*- coding: utf-8 -*-
"""The loading cover around a page's first load."""
import threading
import time

import xbmc
import xbmcgui

from resources.lib import nav

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
    cover = Cover('StvLoading.xml', addon.homeDir, 'Default', '1080i')
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
        if time.monotonic() - started > deadline or nav.wait(monitor, 0.1):
            break
    if nav.stopping():
        return None
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
        message = addon.localLang(30022) or 'Could not reach Samsung TV Plus'
    xbmcgui.Dialog().notification(addon.addonName, message, xbmcgui.NOTIFICATION_ERROR)
    return None


