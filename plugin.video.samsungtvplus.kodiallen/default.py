# -*- coding: utf-8 -*-
# Plugin entry: classic folders, playback, favourites, IPTV Manager.
#
import sys
import urllib.parse

import xbmc
import xbmcgui

ADDON_ID = 'plugin.video.samsungtvplus.kodiallen'

# A root plugin run can begin before the service sees the Videos window.
# Request the cover before the slower imports; the service owns opening Home.
if (len(sys.argv) > 2 and not sys.argv[2][1:] and
        not xbmcgui.Window(10000).getProperty('stv.return.home') and
        xbmc.getCondVisibility(
            'Window.IsActive(videos) + '
            '[String.IsEqual(Container.FolderPath,addons://sources/video) | '
            'String.StartsWith(Container.FolderPath,plugin://%s/)]' % ADDON_ID)):
    xbmcgui.Window(10000).setProperty('stv.return.home', 'loading')
    xbmc.log(msg='%s : loading requested' % ADDON_ID, level=xbmc.LOGINFO)

import xbmcplugin  # noqa: E402

from resources.lib import iptv  # noqa: E402
from resources.lib import player  # noqa: E402
from resources.lib.catalog import StvAddon  # noqa: E402
from resources.lib.data import DataError  # noqa: E402

route = sys.argv[0]
handle = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].lstrip('-').isdigit() else -1
query = dict((key, values[0]) for key, values in
             urllib.parse.parse_qs(sys.argv[2][1:] if len(sys.argv) > 2 else '').items())
mode = query.get('mode', '')


def folder(items, content='videos'):
    xbmcplugin.setContent(handle, content)
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    xbmcplugin.endOfDirectory(handle)


def entry(addon, label, url, isFolder=True):
    item = xbmcgui.ListItem(label, offscreen=True)
    item.setArt({'icon': addon.addonIcon, 'thumb': addon.addonIcon, 'fanart': addon.addonFanart})
    return url, item, isFolder


def withMenu(addon, items):
    """Channel items with Kodi's context menu entry for the add-on's favourites."""
    favourites = set(addon.favourites())
    for url, item, isFolder in items:
        channelId = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get('id', [''])[0]
        label = addon.localLang(30406 if channelId in favourites else 30405)
        item.addContextMenuItems([(label, 'RunPlugin(%s)' % addon.url('favourite', id=channelId))])
    return items


def root(addon):
    data = addon.data
    items = [entry(addon, addon.localLang(30401), addon.url('group'))]
    if addon.favourites():
        items.append(entry(addon, addon.localLang(30402), addon.url('favourites')))
    items += [entry(addon, group, addon.url('group', name=group)) for group in data.groups()]
    items.append(entry(addon, addon.localLang(30203), addon.url('search')))
    folder(items, 'files')


def channelFolder(addon, ids):
    data = addon.data
    folder(withMenu(addon, [addon.channelItem(data.channels[c]) for c in ids if c in data.channels]))


def search(addon):
    text = xbmcgui.Dialog().input(addon.localLang(30203)).strip().lower()
    if not text:
        return xbmcplugin.endOfDirectory(handle, succeeded=False)
    data = addon.data
    channelFolder(addon, [c for c, channel in data.channels.items()
                          if text in channel['name'].lower() or text in channel['group'].lower()])


def favourite(addon, channelId):
    added = addon.toggleFavourite(channelId)
    name = (addon.data.channels.get(channelId) or {}).get('name', channelId)
    xbmcgui.Dialog().notification(addon.addonName, addon.localLang(30403 if added else 30404) % name)
    xbmc.executebuiltin('Container.Refresh')


def main():
    # The service starts the custom interface as RunScript(<id>,home).
    if len(sys.argv) > 1 and sys.argv[1] == 'home':
        from resources.lib import ui
        ui.run()
        return
    # IPTV Manager wants its answer on the socket it names.
    if iptv.handle(route, query.get('port')):
        return
    addon = StvAddon()
    try:
        if mode == 'play':
            player.resolve(addon, handle, query.get('id'))
        elif mode == 'group':
            name = query.get('name')
            channelFolder(addon, [c for c, ch in addon.data.channels.items() if not name or ch['group'] == name])
        elif mode == 'favourites':
            channelFolder(addon, addon.favourites())
        elif mode == 'search':
            search(addon)
        elif mode == 'favourite':
            favourite(addon, query.get('id'))
        else:
            root(addon)
    except DataError as err:
        addon.note('channel data unavailable: %s' % err, xbmc.LOGERROR)
        xbmcgui.Dialog().notification(addon.addonName, addon.localLang(30074), xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(handle, succeeded=False)


main()
