# -*- coding: utf-8 -*-
"""Resolve a Joyn title or channel into a DASH + Widevine list item.

Joyn serves everything as MPEG-DASH, CENC-encrypted, with a Widevine licence
URL and a service certificate URL per playlist. Decryption is the
device's own Widevine CDM's job through inputstream.adaptive; the add-on
only hands over the manifest and licence URLs Joyn issued. In custom route
mode both go through the region's relay, which forwards the licence
exchange unchanged.
"""
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from resources.lib.joyn_api import MESSAGES, USER_AGENT, VOD, JoynError

WIDEVINE_KEYSYSTEM = 'com.widevine.alpha'
# inputstream.adaptive 21 introduced drm_legacy and works the manifest type
# out by itself; older builds want license_type/license_key and the type.
DRM_PROPERTIES_SINCE = 21


def inputstreamMajor():
    try:
        return int(xbmcaddon.Addon('inputstream.adaptive').getAddonInfo('version').split('.')[0])
    except Exception:
        return 0


def message(addon, err):
    """What to tell the viewer about a failed playback."""
    stringId = MESSAGES.get(err.code)
    if stringId:
        return addon.localLang(stringId)
    return addon.localLang(30306) % (err.code or err.status or type(err).__name__)


def headers(addon, extra=()):
    site = addon.api.site
    return urllib.parse.urlencode([('User-Agent', USER_AGENT), ('Origin', site),
                                   ('Referer', site + '/')] + list(extra))


def drmProperties(addon, licenseUrl):
    licence = headers(addon, [('Content-Type', 'application/octet-stream')])
    if inputstreamMajor() >= DRM_PROPERTIES_SINCE:
        return [('inputstream.adaptive.drm_legacy', '|'.join([WIDEVINE_KEYSYSTEM, licenseUrl, licence]))]
    # url | request headers | request data | response format
    return [('inputstream.adaptive.license_type', WIDEVINE_KEYSYSTEM),
            ('inputstream.adaptive.license_key', '|'.join([licenseUrl, licence, 'R{SSM}', ''])),
            ('inputstream.adaptive.manifest_type', 'mpd')]


def resolve(addon, handle, contentId, kind, videoId=None, title=None):
    """Answer Kodi's resolve call for a film/episode (VOD) or a channel (LIVE)."""
    failed = xbmcgui.ListItem(offscreen=True)
    try:
        if kind == VOD and not videoId:
            # A row without the video id: one lookup by the title's id.
            asset = addon.api.asset(contentId)
            videoId = (asset.get('video') or {}).get('id')
            title = title or asset.get('title')
            if not videoId:
                raise JoynError('no video for this title')
        playlist = addon.api.playlist(videoId if kind == VOD else contentId, kind)
    except JoynError as err:
        addon.note('playback refused for %s %s: code=%s status=%s' % (
            kind, contentId, err.code, err.status), xbmc.LOGWARNING)
        xbmcgui.Dialog().notification(addon.addonName, message(addon, err),
                                      xbmcgui.NOTIFICATION_WARNING, 8000)
        xbmcplugin.setResolvedUrl(handle, False, failed)
        return False

    manifest = addon.mediaUrl(playlist['manifestUrl'])
    item = xbmcgui.ListItem(path=manifest, offscreen=True)
    if title:
        item.getVideoInfoTag().setTitle(title)
    item.setMimeType('application/dash+xml')
    item.setContentLookup(False)
    item.setProperty('inputstream', 'inputstream.adaptive')
    # The CDN wants the browser's Origin; it rejects a bearer token.
    item.setProperty('inputstream.adaptive.manifest_headers', headers(addon))
    item.setProperty('inputstream.adaptive.stream_headers', headers(addon))
    if playlist.get('licenseUrl'):
        for key, value in drmProperties(addon, addon.mediaUrl(playlist['licenseUrl'])):
            item.setProperty(key, value)
    addon.note('playing %s %s via %s (%s, drm=%s)' % (
        kind, contentId, urllib.parse.urlsplit(playlist['manifestUrl']).hostname,
        'relay' if manifest != playlist['manifestUrl'] else 'direct', bool(playlist.get('licenseUrl'))))
    xbmcplugin.setResolvedUrl(handle, True, item)
    return True
