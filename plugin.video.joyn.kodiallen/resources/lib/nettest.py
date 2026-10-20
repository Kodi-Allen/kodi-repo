# -*- coding: utf-8 -*-
"""The connection test behind each region's network settings.

It walks the path playback takes, step by step, over the region's own route:
API sign-in and catalogue, the playback right for one free channel, and in
custom mode the relay with a signed manifest request. Each step reports what
Joyn or the relay answered; nothing is retried over another connection.
"""
import time

import requests
import xbmcgui

from resources.lib import lineup
from resources.lib import routing
from resources.lib.joyn_api import LIVE, USER_AGENT, JoynError


def step(lines, label, call):
    started = time.monotonic()
    try:
        result = call()
        lines.append('[COLOR FF00E1C1]OK[/COLOR]  %s: %s  (%.1f s)' % (label, result, time.monotonic() - started))
        return True
    except JoynError as err:
        lines.append('[COLOR FFFF5050]--[/COLOR]  %s: %s %s' % (label, err.code or err.status or '', err))
    except Exception as err:
        lines.append('[COLOR FFFF5050]--[/COLOR]  %s: %s' % (label, type(err).__name__))
    return False


def run(addon):
    region = addon.region
    custom = routing.custom_enabled(addon.addon, region)
    lines = ['%s (%s)' % (addon.regionName, region.upper()),
             '%s: %s' % (addon.localLang(30501), addon.localLang(30503 if custom else 30502)), '']
    lines.append('%s: %s' % (addon.localLang(30228), addon.api.account or addon.localLang(30229)))
    if custom:
        proxy = routing.addon_http_proxy(addon.addon, region)
        lines.append('%s: %s' % (addon.localLang(30504), 'missing' if proxy == routing.BLOCKED_PROXY
                                 else proxy.split('@')[-1]))
    found = {}

    def catalogue():
        streams = addon.api.live(hours=1)
        found['channels'] = lineup.channels(streams)
        return '%d channels' % len(found['channels'])

    if not step(lines, 'Joyn API', catalogue):
        return show(addon, lines)
    free = [channelId for channelId, channel in found['channels'].items()
            if channel['type'] == lineup.LINEAR and not channel['plus']]
    if not free:
        lines.append('no free channel to test playback with')
        return show(addon, lines)

    def playback():
        found['playlist'] = addon.api.playlist(free[0], LIVE)
        return '%s allowed' % free[0]

    if step(lines, addon.localLang(30505), playback) and custom:
        relay = addon.router.base

        def health():
            if relay is None:
                raise RuntimeError('relay host missing')
            response = requests.get(relay + '/healthz', timeout=5)
            return 'HTTP %d' % response.status_code

        def manifest():
            url = addon.mediaUrl(found['playlist']['manifestUrl'])
            if url == routing.BLOCKED_MEDIA:
                raise RuntimeError('relay key or host missing')
            response = requests.get(url, timeout=15, headers={'User-Agent': USER_AGENT})
            if response.status_code != 200:
                raise RuntimeError('HTTP %d' % response.status_code)
            return 'HTTP 200, %s' % ('segments routed' if '/v1/relay' in response.text else 'not rewritten')

        if step(lines, addon.localLang(30506), health):
            step(lines, addon.localLang(30507), manifest)
    show(addon, lines)


def show(addon, lines):
    xbmcgui.Dialog().textviewer('%s - %s' % (addon.addonName, addon.localLang(30508)), '\n'.join(lines))
