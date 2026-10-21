# -*- coding: utf-8 -*-
"""The loading cover shown while a Samsung TV Plus start completes."""
import time

import xbmc
import xbmcaddon
import xbmcgui

ADDON_ID = 'plugin.video.samsungtvplus.kodiallen'


class Cover(xbmcgui.WindowXMLDialog):
    """Cover the caller and technical root while a Samsung TV Plus start completes."""

    def onAction(self, action):
        # Do not send BACK into a running Kodi directory load.
        pass


def show():
    cover = Cover('StvLoading.xml', xbmcaddon.Addon(ADDON_ID).getAddonInfo('path'),
                  'Default', '1080i')
    cover.show()
    cover.dialogId = xbmcgui.getCurrentWindowDialogId()
    cover.since = time.monotonic()
    xbmc.log(msg='%s : loading cover shown dlg=%s' % (ADDON_ID, cover.dialogId),
             level=xbmc.LOGINFO)
    return cover
