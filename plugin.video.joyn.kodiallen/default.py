# -*- coding: utf-8 -*-
# Plugin entry: classic folders, playback, settings actions, IPTV Manager.
#
import sys
import time
import urllib.parse

import xbmc
import xbmcgui

ADDON_ID = 'plugin.video.joyn.kodiallen'

# A root plugin run can begin before the service sees the Videos window.
# Request the cover before the slower imports; the service remains the sole
# owner of opening Home, including cached entries where this file is not run.
if (len(sys.argv) > 2 and not sys.argv[2][1:] and
        not xbmcgui.Window(10000).getProperty('joyn.return.home') and
        xbmc.getCondVisibility(
            'Window.IsActive(videos) + '
            '[String.IsEqual(Container.FolderPath,addons://sources/video) | '
            'String.StartsWith(Container.FolderPath,plugin://%s/)]' % ADDON_ID)):
    xbmcgui.Window(10000).setProperty('joyn.return.home', 'loading')
    xbmc.log(msg='%s : loading requested' % ADDON_ID, level=xbmc.LOGINFO)

import xbmcplugin  # noqa: E402

from resources.lib import iptv  # noqa: E402
from resources.lib import nav  # noqa: E402
from resources.lib import nettest  # noqa: E402
from resources.lib import player  # noqa: E402
from resources.lib import regions  # noqa: E402
from resources.lib.catalog import JoynAddon  # noqa: E402
from resources.lib.joyn_api import LIVE, VOD, JoynError  # noqa: E402

route = sys.argv[0]
handle = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].lstrip('-').isdigit() else -1
query = dict((key, values[0]) for key, values in
             urllib.parse.parse_qs(sys.argv[2][1:] if len(sys.argv) > 2 else '').items())
mode = query.get('mode', '')


def folder(addon, items, content='videos'):
    xbmcplugin.setContent(handle, content)
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    xbmcplugin.endOfDirectory(handle)


def entry(addon, label, url, isFolder=True, icon=None):
    item = xbmcgui.ListItem(label, offscreen=True)
    item.setArt({'icon': icon or addon.addonIcon, 'thumb': icon or addon.addonIcon,
                 'fanart': addon.addonFanart})
    return url, item, isFolder


def failed(addon, err):
    addon.note('request failed: %s code=%s status=%s' % (type(err).__name__, getattr(err, 'code', None),
                                                       getattr(err, 'status', None)), xbmc.LOGERROR)
    xbmcgui.Dialog().notification(addon.addonName, addon.localLang(30074), xbmcgui.NOTIFICATION_ERROR)
    xbmcplugin.endOfDirectory(handle, succeeded=False)


def root(addon):
    items = [entry(addon, addon.localLang(30211), addon.url('livelist'))]
    for target in (nav.SERIES, nav.MOVIES, nav.SHOWS):
        path, heading = nav.PAGES[target]
        items.append(entry(addon, addon.localLang(heading), addon.url('page', path=path)))
    items.append(entry(addon, addon.localLang(30215), addon.url('search')))
    items.append(entry(addon, '%s: %s' % (addon.localLang(30216), addon.regionName),
                       addon.url('region'), isFolder=False))
    folder(addon, items, 'files')


def page(addon, path):
    items = []
    for title, blockId, rowItems in addon.rows(addon.page(path)):
        items.append(entry(addon, title, addon.url('row', path=path, block=blockId)))
    folder(addon, items, 'files')


def row(addon, path, blockId):
    for title, rowId, items in addon.rows(addon.page(path)):
        if rowId == blockId:
            return folder(addon, items, 'movies')
    folder(addon, [])


def seriesFolder(addon, path):
    series, seasons = addon.seasonList(path)
    title = series.get('title') or ''
    if len(seasons) == 1:
        return folder(addon, addon.episodeItems(seasons[0], title), 'episodes')
    items = []
    for season in seasons:
        label = '%s %s' % (xbmc.getLocalizedString(20373), season['number'])
        if season['plus']:
            label = '%s [COLOR FFFFC400][Joyn+][/COLOR]' % label
        items.append(entry(addon, label, addon.url('season', id=season['id'], number=season['number'],
                                                   title=title)))
    folder(addon, items, 'seasons')


def liveFolder(addon):
    from resources.lib import lineup
    items = []
    streams = addon.api.live()
    guide = lineup.programmes(streams)
    now = time.time()
    for channelId, channel in lineup.channels(streams).items():
        label = channel['title']
        current = [program for start, end, program in guide.get(channelId) or []
                   if start <= now < end]
        if current:
            label = '%s  [COLOR FFA0A0A0]%s[/COLOR]' % (label, current[0]['title'])
        if channel['plus']:
            label = '%s [COLOR FFFFC400][Joyn+][/COLOR]' % label
        item = xbmcgui.ListItem(label, offscreen=True)
        logo = addon.mediaUrl(channel['logo'])
        item.setArt({'icon': logo, 'thumb': logo, 'fanart': addon.addonFanart})
        item.setProperty('IsPlayable', 'true')
        item.getVideoInfoTag().setTitle(channel['title'])
        items.append((addon.url('live', id=channelId), item, False))
    folder(addon, items)


def searchFolder(addon):
    text = xbmcgui.Dialog().input(addon.localLang(30215)).strip()
    if not text:
        return xbmcplugin.endOfDirectory(handle, succeeded=False)
    items = []
    for asset in addon.api.search(text):
        addon.addAsset(asset, items)
    folder(addon, items, 'movies')


def chooseRegion(addon):
    names = [addon.localLang(regions.REGIONS[region]['name']) for region in regions.ORDER]
    choice = xbmcgui.Dialog().select(addon.localLang(30217), names,
                                     preselect=regions.ORDER.index(addon.region))
    if choice >= 0 and regions.ORDER[choice] != addon.region:
        addon.addon.setSetting(regions.CURRENT, regions.ORDER[choice])
        xbmc.executebuiltin('Container.Refresh')


def signIn(addon):
    email = xbmcgui.Dialog().input(addon.localLang(30221), addon.api.account or '').strip()
    if not email:
        return
    password = xbmcgui.Dialog().input(addon.localLang(30222), option=xbmcgui.ALPHANUM_HIDE_INPUT)
    if not password:
        return
    try:
        addon.api.login(email, password)
    except JoynError as err:
        # Never log the e-mail or the password; Joyn's answer is enough.
        addon.note('sign-in for %s failed: %s' % (addon.region, err.code or err.status), xbmc.LOGWARNING)
        message = {'LOGIN_REJECTED': addon.localLang(30225),
                   'ACCOUNT_INCOMPLETE': addon.localLang(30226) % addon.api.site.replace('https://', ''),
                   'MFA_REQUIRED': addon.localLang(30227)}.get(err.code, addon.localLang(30022))
        xbmcgui.Dialog().ok(addon.addonName, message)
        return
    xbmcgui.Dialog().notification(addon.addonName, addon.localLang(30223) % (addon.api.account, addon.regionName))


def signOut(addon):
    addon.api.logout()
    xbmcgui.Dialog().notification(addon.addonName, addon.localLang(30224) % addon.regionName)


def resetSession(addon):
    addon.api.session.clear()
    addon.note('session of %s reset' % addon.region)
    xbmcgui.Dialog().notification(addon.addonName, addon.localLang(30218) % addon.regionName)


def main():
    # The service starts the custom interface as RunScript(<id>,home).
    if len(sys.argv) > 1 and sys.argv[1] == 'home':
        from resources.lib import ui
        ui.run()
        return
    # IPTV Manager calls /iptv/channels and /iptv/epg and wants the answer on
    # the socket it names, not a Kodi directory listing.
    if iptv.handle(route, query.get('port')):
        return
    addon = JoynAddon(query.get('region'))
    try:
        if mode == 'play':
            player.resolve(addon, handle, query.get('id'), VOD, videoId=query.get('video'))
        elif mode == 'live':
            player.resolve(addon, handle, query.get('id'), LIVE)
        elif mode == 'page':
            page(addon, query.get('path') or '/')
        elif mode == 'row':
            row(addon, query.get('path') or '/', query.get('block'))
        elif mode == 'series':
            seriesFolder(addon, query.get('path'))
        elif mode == 'season':
            folder(addon, addon.episodeItems({'id': query.get('id'), 'number': query.get('number')},
                                             query.get('title') or ''), 'episodes')
        elif mode == 'livelist':
            liveFolder(addon)
        elif mode == 'search':
            searchFolder(addon)
        elif mode == 'region':
            chooseRegion(addon)
        elif mode == 'login':
            signIn(addon)
        elif mode == 'logout':
            signOut(addon)
        elif mode == 'reset':
            resetSession(addon)
        elif mode == 'nettest':
            nettest.run(addon)
        elif mode == 'overlaps':
            iptv.review(addon.addon)
        else:
            root(addon)
    except JoynError as err:
        failed(addon, err)


main()
