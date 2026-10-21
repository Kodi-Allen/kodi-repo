# -*- coding: utf-8 -*-
"""Resolve a Samsung TV Plus channel into an HLS list item.

jmp2.uk redirects to the stream Samsung serves for the channel right now.
inputstream.adaptive plays it. In relay mode the channel URL goes to the
Italian relay, which follows the redirect inside the Italian tunnel and
routes every playlist and segment through it.
"""
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from resources.lib.data import DataError

MANIFEST_TYPE_DETECTED_SINCE = 21


def inputstreamMajor():
    try:
        return int(xbmcaddon.Addon('inputstream.adaptive').getAddonInfo('version').split('.')[0])
    except Exception:
        return 0


def resolve(addon, handle, channelId):
    failed = xbmcgui.ListItem(offscreen=True)
    try:
        channel = addon.data.channels.get(channelId)
    except DataError as err:
        channel = None
        addon.note('channel data unavailable: %s' % err, xbmc.LOGWARNING)
    if channel is None:
        xbmcgui.Dialog().notification(addon.addonName, addon.localLang(30301), xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.setResolvedUrl(handle, False, failed)
        return False
    source = addon.data.playUrl(channelId)
    stream = addon.mediaUrl(source)
    item = xbmcgui.ListItem(path=stream, offscreen=True)
    item.getVideoInfoTag().setTitle(channel['name'])
    item.setArt({'icon': channel['logo'], 'thumb': channel['logo']})
    item.setMimeType('application/vnd.apple.mpegurl')
    item.setContentLookup(False)
    item.setProperty('inputstream', 'inputstream.adaptive')
    headers = urllib.parse.urlencode(addon.data.headers)
    if headers:
        item.setProperty('inputstream.adaptive.manifest_headers', headers)
        item.setProperty('inputstream.adaptive.stream_headers', headers)
    if inputstreamMajor() < MANIFEST_TYPE_DETECTED_SINCE:
        item.setProperty('inputstream.adaptive.manifest_type', 'hls')
    addon.note('playing %s (%s, %s)' % (channelId, channel['name'], 'relay' if stream != source else 'direct'))
    xbmcplugin.setResolvedUrl(handle, True, item)
    return True
