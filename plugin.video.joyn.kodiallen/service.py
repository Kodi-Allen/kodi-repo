# -*- coding: utf-8 -*-
# Background service
#
# Notices the add-on's plugin root in the Videos window and starts the custom
# interface above it. A plugin process cannot do that itself; it is gone
# before Kodi has drawn the root folder. The root call in default.py only
# asks for the loading cover early.
#
# The interface runs as a script of its own (resources/lib/ui.py), never in
# this service: Kodi stops a service from its GUI side, and a service that
# owned windows would then wait on the GUI at the same time.
#
import time

import xbmc
import xbmcgui

from resources.lib import cover as coverlib
from resources.lib import nav
from resources.lib.ui import COVER, isOpen

ADDON_ID = 'plugin.video.joyn.kodiallen'
VIDEO_POLL = 0.1
IDLE_POLL = 0.25
UI_START = 15.0
RETURN_HOME = 'joyn.return.home'
ROOT = 'plugin://%s/' % ADDON_ID
ROOT_READY = ('Window.IsActive(videos) + !Window.IsVisible(busydialog) + '
              '!Window.IsVisible(busydialognocancel) + '
              'String.IsEqual(Container.FolderPath,%s) + '
              'Integer.IsGreater(Container.NumItems,0)' % ROOT)
IN_JOYN = 'Window.IsActive(videos) + String.StartsWith(Container.FolderPath,%s)' % ROOT


def startUi(monitor, cover):
    """Start the interface script; it closes the cover as Home opens."""
    home = xbmcgui.Window(10000)
    home.setProperty(COVER, str(cover.dialogId))
    xbmc.executebuiltin('RunScript(%s,home)' % ADDON_ID)
    deadline = time.monotonic() + UI_START
    while not isOpen(home) and time.monotonic() < deadline:
        if nav.wait(monitor, 0.05):
            return
    if not isOpen(home):
        xbmc.log(msg='%s : interface did not start' % ADDON_ID, level=xbmc.LOGWARNING)
        home.clearProperty(COVER)
        home.setProperty(RETURN_HOME, 'exit')
        cover.close()


def run():
    xbmc.log(msg='%s : service started' % ADDON_ID, level=xbmc.LOGINFO)
    monitor = xbmc.Monitor()
    home = xbmcgui.Window(10000)
    cover = None
    while not nav.stopping():
        # Any finished visible Joyn root is an entry; an intentional Home
        # exit and an interface that is already open are the exclusions.
        state = home.getProperty(RETURN_HOME)
        if state == 'loading' and cover is None and not isOpen(home):
            cover = coverlib.show()
        allowedDialogs = (0, 9999) if cover is None else (0, 9999, cover.dialogId)
        rootAvailable = (xbmcgui.getCurrentWindowDialogId() in allowedDialogs and
                         xbmc.getCondVisibility(ROOT_READY))
        if rootAvailable and state != 'exit' and not isOpen(home):
            home.clearProperty(RETURN_HOME)
            if cover is None:
                cover = coverlib.show()
            xbmc.log(msg='%s : root ready (%s), opening home' % (ADDON_ID, state or 'entry'),
                     level=xbmc.LOGINFO)
            startUi(monitor, cover)
            cover = None
            continue
        if state == 'exit' and not xbmc.getCondVisibility(IN_JOYN):
            home.clearProperty(RETURN_HOME)
            xbmc.log(msg='%s : exit complete' % ADDON_ID, level=xbmc.LOGINFO)
        if cover is not None and time.monotonic() - cover.since > 20.0:
            xbmc.log(msg='%s : loading cover timeout' % ADDON_ID, level=xbmc.LOGWARNING)
            cover.close()
            cover = None
            if state == 'loading':
                home.clearProperty(RETURN_HOME)
        # Fast only while a Videos transition can expose the root. A quarter
        # second outside Videos keeps direct entries responsive without the
        # expensive permanent 0.1-second idle poll.
        delay = VIDEO_POLL if (state or cover is not None or
                               xbmc.getCondVisibility('Window.IsActive(videos)')) else IDLE_POLL
        if nav.wait(monitor, delay):
            break
    xbmc.log(msg='%s : service stopped' % ADDON_ID, level=xbmc.LOGINFO)


if __name__ == '__main__':
    run()
