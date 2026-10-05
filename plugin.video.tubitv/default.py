# -*- coding: utf-8 -*-
# KodiAddon
#
import os
import re
import sys
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui

from resources.lib import iptv
from resources.lib.scraper import myAddon
from resources.lib.tubi_api import TubiApi
from resources.lib.tubi_auth import TubiAuth, TubiAuthError

ADDON_ID = 'plugin.video.tubitv'
LIVE_PATH = ''.join(['plugin://', ADDON_ID, '/?mode=LV&url=%s'])
# The three Tubi has been seen serving. Order matches the setting's values.
LANGUAGES = ['en-US', 'es-MX', 'fr-CA']
# Keep Tubi's API and licence requests in one current web-client context.
# t1mlib's inherited default still identifies Chrome 41, released in 2015.
TUBI_WEB_USER_AGENT = ('Mozilla/5.0 (X11; Linux x86_64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/154.0.0.0 Safari/537.36')

__settings__ = xbmcaddon.Addon(ADDON_ID)

# Start of Module
addonName = re.search(r'plugin\://plugin\.video\.(.+?)/', str(sys.argv[0])).group(1)
ma = myAddon(addonName)
ma.defaultHeaders['User-Agent'] = TUBI_WEB_USER_AGENT

# Tubi is free to browse, so a missing or rejected sign-in is not fatal - the
# addon carries on with the anonymous device token and only the account
# features and the sign-in gated titles are lost.
ma.auth = TubiAuth(__settings__)
try:
    ma.auth.apply(ma.defaultHeaders)
except TubiAuthError as err:
    xbmc.log(msg='%s : sign-in failed : %s' % (ADDON_ID, err), level=xbmc.LOGWARNING)
    if err.fresh:
        xbmcgui.Dialog().notification(__settings__.getAddonInfo('name'),
                                      __settings__.getLocalizedString(30021) % err,
                                      xbmcgui.NOTIFICATION_WARNING)

# Tubi localises its categories and descriptions off the Accept-Language it
# is asked with - nothing else about a request changes.
ma.defaultHeaders['Accept-Language'] = LANGUAGES[int(__settings__.getSetting('language') or 0)]

ma.api = TubiApi(ma.defaultHeaders, ma.auth.deviceId, userId=ma.auth.userId,
                 kids=__settings__.getSetting('kids_mode') == 'true', addon=__settings__)

# Kodi hands back a query with the '=' trimmed off any empty value, e.g.
# "?mode=GM&url", which t1mlib splits on '=' and chokes on. Put it back.
if len(sys.argv) > 2 and sys.argv[2].startswith('?'):
    args = [arg if '=' in arg else ''.join([arg, '=']) for arg in sys.argv[2][1:].split('&') if arg]
    sys.argv[2] = ''.join(['?', '&'.join(args)])

# IPTV Manager calls /iptv/channels and /iptv/epg and wants the answer on the
# socket it names, not a Kodi directory listing.
query = urllib.parse.parse_qs(sys.argv[2][1:]) if len(sys.argv) > 2 else {}
port = (query.get('port') or [None])[0]
if not iptv.handle(sys.argv[0], port, ma.api, LIVE_PATH, log=ma.log,
                   store=os.path.join(ma.auth.profile, 'iptv.json')):
    ma.processAddonEvent()
