# -*- coding: utf-8 -*-
"""Title actions and resume for the custom windows.

The classic listings hand their title actions to Kodi as context menu
entries and let Kodi offer to resume; a WindowXML does neither by itself.
These helpers offer the same entries, built by the add-on's own extrasFor,
and the same resume choice, from the custom pages.
"""
import json
import sys
import urllib.parse

import xbmc
import xbmcgui

CONTEXT_MENU = 117
SERIES = 's'
PROPERTY = 'tubi.content'


def addContent(addon, content, items):
    """The add-on's addContent, keeping what the title's actions need."""
    items = addon.addContent(content, items)
    items[-1][1].setProperty(PROPERTY, json.dumps({
        'id': str(content.get('id')),
        'type': content.get('type'),
        'trailer': bool(content.get('has_trailer') or content.get('trailers')),
        'title': content.get('title') or ''}))
    return items


def entries(addon, item):
    """The classic context menu for a title: library export, then extrasFor.

    Signed out, the entries that need an account (My List, ratings,
    Continue Watching) are left out rather than failing when chosen.
    """
    try:
        info = json.loads(item.getProperty(PROPERTY) or '{}')
    except ValueError:
        return {}, []
    contentId = info.get('id')
    if not contentId:
        return {}, []
    series = info.get('type') == SERIES
    menu = [(addon.localLang(30024 if series else 30025),
             'RunPlugin(%s?mode=%s&url=%s)' % (sys.argv[0], 'AS' if series else 'AM',
                                                urllib.parse.quote_plus(contentId)))]
    signedIn = addon.auth is not None and addon.auth.signedIn
    for label, action in addon.extrasFor(contentId, {'type': info.get('type'),
                                                     'has_trailer': info.get('trailer')}):
        if signedIn or 'mode=DF&' not in action:
            menu.append((label, action))
    return info, menu


def show(addon, item):
    """Offer a title's actions. Returns the title's info when Related titles
    was chosen, which the calling window opens itself; None otherwise."""
    info, menu = entries(addon, item)
    if not menu:
        return None
    choice = xbmcgui.Dialog().contextmenu([label for label, _ in menu])
    if choice < 0:
        return None
    label, action = menu[choice]
    addon.note('TUBI-UI context: %s' % label)
    if 'mode=SE&' in action:
        # Related titles open as a custom page, never as a Kodi folder.
        return info
    # The action runs in a plugin process of its own; keep this window's
    # idea of the saved list in step so the next menu offers the right entry.
    contentId = info['id']
    if 'url=queue%7Cadd%7C' in action:
        addon.saved.add(contentId)
    elif 'url=queue%7Cremove%7C' in action:
        addon.saved.discard(contentId)
    elif 'url=unwatch%7C' in action:
        addon.watching.pop(contentId, None)
    xbmc.executebuiltin(action)
    return None


def resumePoint(item):
    """(position, total) seconds of the title's resume point, else None.

    The point is the one applyResume put on the item from Tubi's watch
    history. As in Kodi's own listings it counts only when it lies part
    way through a known length.
    """
    tag = item.getVideoInfoTag()
    try:
        position, total = tag.getResumeTime(), tag.getResumeTimeTotal()
    except AttributeError:
        # Kodi 19 keeps the point in the ResumeTime/TotalTime properties
        position, total = item.getProperty('ResumeTime'), item.getProperty('TotalTime')
    try:
        position, total = float(position or 0), float(total or 0)
    except (TypeError, ValueError):
        return None
    if 0 < position < total:
        return position, total
    return None


def clock(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return '%d:%02d:%02d' % (hours, minutes, seconds) if hours else '%02d:%02d' % (minutes, seconds)


def play(url, item):
    """Play a title, first offering Tubi's resume point as Kodi would."""
    point = resumePoint(item)
    if point is None:
        xbmc.executebuiltin('PlayMedia("%s")' % url)
        return
    choice = xbmcgui.Dialog().contextmenu([
        xbmc.getLocalizedString(12022).format(clock(point[0])),  # Resume from
        xbmc.getLocalizedString(12021)])                         # Play from beginning
    if choice < 0:
        return
    start = xbmcgui.ListItem(path=url, offscreen=True)
    start.setProperty('IsPlayable', 'true')
    if choice == 0:
        start.setProperty('StartOffset', '%.3f' % point[0])
    xbmc.Player().play(url, start)
