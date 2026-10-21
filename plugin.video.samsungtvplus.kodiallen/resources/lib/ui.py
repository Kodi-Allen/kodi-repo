# -*- coding: utf-8 -*-
"""The custom interface as a script of its own.

The service only notices the plugin root and starts this script. Windows
therefore never belong to the service: Kodi stops a service from its GUI
side (add-on update, disable, shutdown) and a service holding windows would
wait on the GUI at the same time.
"""
import time

import xbmc
import xbmcgui

from resources.lib import cover as coverlib
from resources.lib import nav

ADDON_ID = 'plugin.video.samsungtvplus.kodiallen'
# The dialog id of the service's loading cover, for this script to close.
COVER = 'stv.cover'
# A heartbeat while this script runs; the service starts no second one
# meanwhile, and a script Kodi had to kill stops counting after STALE seconds.
UI_OPEN = 'stv.ui'
STALE = 10


def isOpen(home):
    try:
        return time.time() - int(home.getProperty(UI_OPEN) or 0) < STALE
    except ValueError:
        return False


class ServiceCover(object):
    """The service's cover, closed from here as Home opens beneath it.

    Kodi lets Home activate only during a modal cover's closing fade, so
    the cover has to close in the same moment Home is shown.
    """

    def __init__(self, dialogId):
        self.dialogId = dialogId

    def close(self):
        if self.dialogId:
            xbmc.executebuiltin('Dialog.Close(%s)' % self.dialogId)


def run():
    home = xbmcgui.Window(10000)
    if isOpen(home):
        return
    cover = ServiceCover(home.getProperty(COVER))
    home.clearProperty(COVER)
    beat = [0]

    def heartbeat():
        if time.time() - beat[0] >= 2:
            beat[0] = time.time()
            home.setProperty(UI_OPEN, str(int(beat[0])))

    heartbeat()
    try:
        from resources.lib.catalog import StvAddon
        from resources.lib.home import showHome
        region = None
        while True:
            # Home in the selected region; a region change reopens it in the new one.
            region = showHome(StvAddon(region), idle=heartbeat, cover=cover)
            cover = None
            if not region or nav.stopping():
                break
            cover = coverlib.show()
    except Exception as err:
        if cover is not None and not nav.stopping():
            cover.close()
        xbmc.log(msg='%s : home failed : %s' % (ADDON_ID, type(err).__name__), level=xbmc.LOGERROR)
        # Leave the usable technical root in place after a Home failure.
        home.setProperty('stv.return.home', 'exit')
    finally:
        home.clearProperty(UI_OPEN)
