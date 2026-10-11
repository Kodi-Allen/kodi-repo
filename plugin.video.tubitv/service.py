# -*- coding: utf-8 -*-
# Background service
#
# Jobs which need to outlive a single plugin invocation:
#
#   * register the addon's folders with PseudoTV Live
#   * tell Tubi how far into a film the viewer got, so its own apps and this
#     addon's Continue Watching agree
#   * return navbar navigation to the custom Home at the outermost root
#
# The plugin cannot do the second itself: by the time playback stops, the
# process that resolved the stream is long gone. It leaves what is playing in
# a window property and this service watches the player.
#
import json
import sys
import time

import xbmc
import xbmcaddon
import xbmcgui

from resources.lib.pseudotv import regPseudoTV
from resources.lib.tubi_api import TubiApi, TubiApiError
from resources.lib.tubi_auth import TubiAuth, TubiAuthError

ADDON_ID = 'plugin.video.tubitv'
PLAYING = 'tubitv.playing'
PLAYBACK_DIAGNOSTIC = 'tubitv.playback.diagnostic'
# Below this Tubi is better off not hearing about it, and near the end the
# viewer has finished rather than paused.
MIN_POSITION = 30
VIDEO_POLL = 0.1
IDLE_POLL = 0.25
RETURN_HOME = 'tubitv.return.home'
ROOT = 'plugin://plugin.video.tubitv/'
ROOT_READY = ('Window.IsActive(videos) + !Window.IsVisible(busydialog) + '
              '!Window.IsVisible(busydialognocancel) + '
              'String.IsEqual(Container.FolderPath,%s) + '
              'Integer.IsGreater(Container.NumItems,0)' % ROOT)
IN_TUBI = 'Window.IsActive(videos) + String.StartsWith(Container.FolderPath,%s)' % ROOT
TUBI_WEB_USER_AGENT = ('Mozilla/5.0 (X11; Linux x86_64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/154.0.0.0 Safari/537.36')
LANGUAGES = ['en-US', 'es-MX', 'fr-CA']


def homeAddon():
    """Build the normal add-on object for a Home owned by this service."""
    from resources.lib.scraper import myAddon
    # Catalog items must retain the add-on's plugin URL, as in default.py.
    sys.argv = [ROOT, '-1', '']
    settings = xbmcaddon.Addon(ADDON_ID)
    addon = myAddon('tubitv')
    addon.defaultHeaders = dict(addon.defaultHeaders)
    addon.defaultHeaders['User-Agent'] = TUBI_WEB_USER_AGENT
    addon.auth = TubiAuth(settings)
    try:
        addon.auth.apply(addon.defaultHeaders)
    except TubiAuthError as err:
        xbmc.log(msg='%s : sign-in failed : %s' % (ADDON_ID, err), level=xbmc.LOGWARNING)
    addon.defaultHeaders['Accept-Language'] = LANGUAGES[int(settings.getSetting('language') or 0)]
    addon.api = TubiApi(addon.defaultHeaders, addon.auth.deviceId, userId=addon.auth.userId,
                        kids=settings.getSetting('kids_mode') == 'true', addon=settings)
    return addon


class Cover(xbmcgui.WindowXMLDialog):
    """Cover the caller and technical root while a Tubi start completes."""

    def onAction(self, action):
        # Do not send BACK into a running Kodi directory load.
        pass


def showCover():
    cover = Cover('TubiLoading.xml', xbmcaddon.Addon(ADDON_ID).getAddonInfo('path'),
                  'Default', '1080i')
    cover.show()
    cover.dialogId = xbmcgui.getCurrentWindowDialogId()
    cover.since = time.monotonic()
    xbmc.log(msg='%s : loading cover shown dlg=%s' % (ADDON_ID, cover.dialogId),
             level=xbmc.LOGINFO)
    return cover


def openHome(player, cover):
    try:
        from resources.lib.home import showHome
        showHome(homeAddon(), {'id': 'most_popular', 'title': 'Most Popular'},
                 idle=player.tick, cover=cover)
        return True
    except Exception as err:
        cover.close()
        xbmc.log(msg='%s : home failed : %s' % (ADDON_ID, type(err).__name__),
                 level=xbmc.LOGERROR)
        return False


class TubiMonitor(xbmc.Player):
    """Keeps the last known position of whatever Tubi title is playing."""

    def __init__(self):
        xbmc.Player.__init__(self)
        self.item = None
        self.position = 0

    def onAVStarted(self):
        self.item = self.currentItem()
        self.position = 0

    def onPlayBackStopped(self):
        self.report()

    def onPlayBackEnded(self):
        self.report()

    def onPlayBackError(self):
        """Leave a useful boundary when Kodi reports a player failure.

        The detailed reason remains in the immediately preceding Kodi/ISA/CDM
        lines; the player callback itself does not expose an error code.
        """
        context = xbmcgui.Window(10000).getProperty(PLAYBACK_DIAGNOSTIC)
        xbmc.log(msg='%s : playback error context=%s; inspect preceding '
                 'inputstream.adaptive/Widevine lines for manifest, HTTP, '
                 'key/HDCP or decoder failure' % (ADDON_ID, context or 'unknown'),
                 level=xbmc.LOGERROR)
        self.item = None
        xbmcgui.Window(10000).clearProperty(PLAYING)
        xbmcgui.Window(10000).clearProperty(PLAYBACK_DIAGNOSTIC)

    @staticmethod
    def currentItem():
        try:
            playing = xbmcgui.Window(10000).getProperty(PLAYING)
            return json.loads(playing) if playing else None
        except ValueError:
            return None

    def tick(self):
        """Remember where we are - getTime() is gone once playback stops."""
        if self.item is None:
            return
        try:
            if self.isPlayingVideo():
                self.position = int(self.getTime())
        except RuntimeError:
            pass

    def report(self):
        item, position = self.item, self.position
        self.item = None
        xbmcgui.Window(10000).clearProperty(PLAYING)
        xbmcgui.Window(10000).clearProperty(PLAYBACK_DIAGNOSTIC)
        if item is None:
            return
        if position < MIN_POSITION:
            xbmc.log(msg='%s : only %ss watched, not reporting' % (ADDON_ID, position),
                     level=xbmc.LOGDEBUG)
            return
        try:
            addon = xbmcaddon.Addon(ADDON_ID)
            auth = TubiAuth(addon)
            headers = {}
            auth.apply(headers)
            api = TubiApi(headers, auth.deviceId, userId=auth.userId, addon=addon)
            api.reportProgress(item['content_id'], item['content_type'], position,
                               parentId=item.get('parent_id'))
            xbmc.log(msg='%s : reported %ss of %s %s' % (ADDON_ID, position,
                                                         item['content_type'], item['content_id']),
                     level=xbmc.LOGDEBUG)
        except (TubiApiError, TubiAuthError, KeyError) as err:
            xbmc.log(msg='%s : could not report progress : %s' % (ADDON_ID, err),
                     level=xbmc.LOGWARNING)


def run():
    xbmc.log(msg='%s : service started' % ADDON_ID, level=xbmc.LOGINFO)
    monitor = xbmc.Monitor()
    player = TubiMonitor()
    pseudotv = regPseudoTV()
    # Let entry handling become responsive before the first potentially slow
    # PseudoTV refresh. Later refreshes retain their normal returned interval.
    waited = 60.0
    transitioning = False
    transitionLeftRoot = False
    transitionStarted = 0.0
    cover = None
    while not monitor.abortRequested():
        player.tick()
        # Any finished visible Tubi root is an entry or an outer return. An
        # intentional Home exit and a new internal route are the two exclusions.
        state = xbmcgui.Window(10000).getProperty(RETURN_HOME)
        if state == 'requested' and not transitioning:
            transitioning = True
            transitionLeftRoot = False
            transitionStarted = time.monotonic()
        if state == 'loading' and cover is None:
            cover = showCover()
        allowedDialogs = (0, 9999) if cover is None else (0, 9999, cover.dialogId)
        rootAvailable = (xbmcgui.getCurrentWindowDialogId() in allowedDialogs and
                         xbmc.getCondVisibility(ROOT_READY))
        if transitioning and not rootAvailable:
            transitionLeftRoot = True
        if (rootAvailable and state != 'exit' and
                (not transitioning or transitionLeftRoot or
                 time.monotonic() - transitionStarted > 15.0)):
            transitioning = False
            xbmcgui.Window(10000).clearProperty(RETURN_HOME)
            if cover is None:
                cover = showCover()
            xbmc.log(msg='%s : root ready (%s), opening home' %
                     (ADDON_ID, state or 'entry'),
                     level=xbmc.LOGINFO)
            if not openHome(player, cover):
                # Leave the usable technical root in place after a Home failure.
                xbmcgui.Window(10000).setProperty(RETURN_HOME, 'exit')
            cover = None
            continue
        if state == 'exit' and not xbmc.getCondVisibility(IN_TUBI):
            transitioning = False
            xbmcgui.Window(10000).clearProperty(RETURN_HOME)
            xbmc.log(msg='%s : exit complete' % ADDON_ID, level=xbmc.LOGINFO)
        if cover is not None and time.monotonic() - cover.since > 20.0:
            xbmc.log(msg='%s : loading cover timeout' % ADDON_ID, level=xbmc.LOGWARNING)
            cover.close()
            cover = None
            if state == 'loading':
                xbmcgui.Window(10000).clearProperty(RETURN_HOME)
        # PseudoTV only needs looking at occasionally, the player does not
        if waited <= 0:
            waited = pseudotv.refresh()
        # Fast only while a Videos transition can expose the root. A quarter
        # second outside Videos keeps direct entries responsive without the
        # expensive permanent 0.1-second idle poll.
        delay = VIDEO_POLL if (state or cover is not None or
                               xbmc.getCondVisibility('Window.IsActive(videos)')) else IDLE_POLL
        waited -= delay
        if monitor.waitForAbort(delay):
            break


if __name__ == '__main__':
    run()
