# -*- coding: utf-8 -*-
"""Tubi Live TV guide: server categories over a time-proportional grid."""
import calendar
import html
import re
import threading
import time

import xbmc
import xbmcgui

from resources.lib import tubi_api
from resources.lib.series import coverLoad
from resources.lib.tubi_api import TubiApiError

CATEGORIES = 400
GRID = 700
ROWS = 8
SLOTS = 14
ROW_Y0, ROW_H, ROW_GAP = 216, 84, 6
RULER_Y = 168
CH_X, CH_W = 100, 280
PROG_X, PROG_W = 392, 1428
STEP = 30 * 60                      # ruler step and scroll unit
PX_PER_SECOND = 160.0 / STEP        # 160 px per half hour
SPAN = PROG_W / PX_PER_SECOND       # seconds the grid shows
LEAD = 40 * 60                      # NOW sits 40-70 min (15-26 %) into the grid
EDGE = 15 * 60                      # a selection showing less than this steps the grid
CELL_GAP = 4
MIN_TIME_WIDTH = 150                # narrower cells show the title only
PLAY = 'plugin://plugin.video.tubitv/?mode=LV&url=%s'
TAG = re.compile(r'<[^>]*>')
LEFT, RIGHT, UP, DOWN, SELECT = 1, 2, 3, 4, 7


def epoch(stamp):
    """Tubi's ISO-8601 UTC time as a Unix time."""
    stamp = (stamp or '').split('.')[0].rstrip('Z')
    try:
        return calendar.timegm(time.strptime(stamp, '%Y-%m-%dT%H:%M:%S'))
    except ValueError:
        return None


def clock(seconds):
    return time.strftime('%H:%M', time.localtime(seconds))


def text(value):
    return html.unescape(TAG.sub('', str(value or ''))).strip()


def viewOrigin():
    """The half-hour mark the grid opens on, a little before NOW."""
    return int((time.time() - LEAD) // STEP) * STEP


def lineUp(api):
    """Tubi's categories in server order, each with its channel ids, and the channels."""
    params = [('mode', tubi_api.EPG_MODE), ('platform', tubi_api.PLATFORM),
              ('device_id', api.deviceId)]
    if api.userId is not None:
        params.append(('user_id', api.userId))
    data = api.get(''.join([tubi_api.BROWSE_API, '/api/v2/epg']), params,
                   attempts=tubi_api.LIVE_ATTEMPTS)
    channels = data.get('contents') or {}
    categories = []
    for container in data.get('containers') or []:
        ids = []
        for channelId in container.get('contents') or []:
            # A channel twice in the same category is a backend artifact.
            if channelId in channels and channelId not in ids:
                ids.append(channelId)
        if ids:
            categories.append((container.get('name') or '', ids))
    return categories, channels


def programmes(api, channelIds):
    """{channel id: [(start, end, programme)]} from Tubi's own guide."""
    guide = {}
    for row in api.liveProgramming(channelIds, tolerant=True):
        items = []
        for program in row.get('programs') or []:
            start, end = epoch(program.get('start_time')), epoch(program.get('end_time'))
            if start is not None and end is not None and end > start:
                items.append((start, end, program))
        items.sort(key=lambda item: item[0])
        guide[str(row.get('content_id'))] = items
    return guide


class TubiLive(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        super(TubiLive, self).__init__(*args, **kwargs)
        self.addon = None
        self.categories = []
        self.channels = {}
        self.guide = {}
        self.category = 0
        self.ids = []
        self.top = 0                    # first channel row shown
        self.row = 0                    # selected channel, absolute in the category
        self.cell = None                # selected programme index, None = channel logo
        self.cursor = 0                 # the time UP/DOWN keeps, as Kodi's guide does
        self.viewStart = 0
        self.minStart = 0
        self.shown = {}                 # control id -> last applied values
        self.navbar = None
        self.playing = None
        self.loading = None
        self.closed = False
        self.started = False
        self.windowId = None
        self.lock = threading.RLock()

    # ------------------------------------------------------------ setup

    def onInit(self):
        self.windowId = xbmcgui.getCurrentWindowId()
        if self.started:
            return
        self.started = True
        items = []
        for index, (name, _) in enumerate(self.categories):
            item = xbmcgui.ListItem(name, offscreen=True)
            item.setProperty('active', 'true' if index == self.category else '')
            items.append(item)
        self.getControl(CATEGORIES).addItems(items)
        self.viewStart = self.minStart = viewOrigin()
        self.selectNow(0)
        self.layout()
        self.setFocusId(GRID)

    def setCategory(self, index):
        self.category = index
        self.ids = [str(i) for i in self.categories[index][1]]
        self.top = self.row = 0
        listing = self.getControl(CATEGORIES)
        for position in range(listing.size()):
            listing.getListItem(position).setProperty('active', 'true' if position == index else '')

    # ---------------------------------------------------------- helpers

    def programmesOf(self, row):
        if not 0 <= row < len(self.ids):
            return []
        return self.guide.get(self.ids[row]) or []

    def covering(self, row, moment):
        """The programme on a channel at a time, else the next one, else the last."""
        items = self.programmesOf(row)
        for index, (start, end, _) in enumerate(items):
            if end > moment:
                return index
        return len(items) - 1 if items else None

    def selectNow(self, row):
        self.row = row
        self.cursor = max(time.time(), self.viewStart)
        self.cell = self.covering(row, self.cursor)

    def keepVisible(self):
        if self.row < self.top:
            self.top = self.row
        elif self.row >= self.top + ROWS:
            self.top = self.row - ROWS + 1

    def apply(self, controlId, **values):
        """Set only what changed; every call into Kodi takes its GUI lock."""
        last = self.shown.setdefault(controlId, {})
        control = None
        for key in ('label', 'pos', 'width', 'visible', 'color', 'image'):
            if key not in values or last.get(key) == values[key]:
                continue
            control = control or self.getControl(controlId)
            value = values[key]
            if key == 'label':
                control.setLabel(value)
            elif key == 'pos':
                control.setPosition(*value)
            elif key == 'width':
                control.setWidth(value)
            elif key == 'visible':
                control.setVisible(value)
            elif key == 'color':
                control.setColorDiffuse(value)
            elif key == 'image':
                control.setImage(value, False)
            last[key] = value

    def x(self, moment):
        return PROG_X + int(round((moment - self.viewStart) * PX_PER_SECOND))

    # ----------------------------------------------------------- layout

    def layout(self):
        with self.lock:
            now = time.time()
            viewEnd = self.viewStart + SPAN
            for mark in range(PROG_W // 160 + 1):
                self.apply(2500 + mark, label=clock(self.viewStart + mark * STEP))
            nowX = self.x(now)
            onGrid = PROG_X <= nowX <= PROG_X + PROG_W
            self.apply(2400, pos=(nowX - 1, RULER_Y), visible=onGrid)
            self.apply(2401, pos=(nowX - 70, RULER_Y - 26), label='[B]LIVE[/B] %s' % clock(now) if onGrid else '',
                       visible=onGrid)
            selected = None
            for r in range(ROWS):
                row = self.top + r
                y = ROW_Y0 + r * (ROW_H + ROW_GAP)
                channel = self.channels.get(self.ids[row]) if row < len(self.ids) else None
                self.apply(2000 + r, visible=channel is not None,
                           color='FF6E2DAA' if (row == self.row and self.cell is None) else 'FF1A1228')
                logo = ((channel or {}).get('images') or {}).get('thumbnail') or []
                self.apply(2100 + r, image=self.addon.mediaUrl(logo[0]) if logo else '',
                           visible=channel is not None)
                self.apply(2150 + r, label='' if logo else text((channel or {}).get('title')),
                           visible=channel is not None)
                slot = 0
                progress = False
                for index, (start, end, program) in enumerate(self.programmesOf(row)):
                    if end <= self.viewStart or start >= viewEnd or slot >= SLOTS:
                        continue
                    left = self.x(max(start, self.viewStart))
                    right = self.x(min(end, viewEnd))
                    width = max(4, right - left - CELL_GAP)
                    airing = start <= now < end
                    ids = (3000 + r * 20 + slot, 4000 + r * 20 + slot, 5000 + r * 20 + slot)
                    self.apply(ids[0], pos=(left, y), width=width, visible=True,
                               color='FF2C2142' if airing else 'FF1E1530')
                    roomy = width >= 40
                    self.apply(ids[1], pos=(left + 14, y + 6), width=max(1, width - 28),
                               label=text(program.get('title')), visible=roomy)
                    self.apply(ids[2], pos=(left + 14, y + 40), width=max(1, width - 28),
                               label='%s – %s' % (clock(start), clock(end)),
                               visible=width >= MIN_TIME_WIDTH)
                    if airing:
                        progress = True
                        self.apply(2200 + r, pos=(left, y + ROW_H - 6),
                                   width=max(2, min(width, self.x(now) - left)), visible=True)
                    if row == self.row and index == self.cell:
                        selected = (left, y, width)
                    slot += 1
                for rest in range(slot, SLOTS):
                    for base in (3000, 4000, 5000):
                        self.apply(base + r * 20 + rest, visible=False)
                if not progress:
                    self.apply(2200 + r, visible=False)
            if selected is None and self.cell is None and self.top <= self.row < self.top + ROWS:
                y = ROW_Y0 + (self.row - self.top) * (ROW_H + ROW_GAP)
                selected = (CH_X, y, CH_W)
            if selected is not None:
                left, y, width = selected
                self.apply(2300, pos=(left - 3, y - 3), width=width + 6, visible=True)
                self.apply(2301, pos=(left, y), width=width, visible=True)
            else:
                self.apply(2300, visible=False)
                self.apply(2301, visible=False)
            self.updateInfo()

    def updateInfo(self):
        channel = self.channels.get(self.ids[self.row]) if self.row < len(self.ids) else None
        items = self.programmesOf(self.row)
        name = text((channel or {}).get('title'))
        if self.cell is None or self.cell >= len(items):
            self.setProperty('tubi.live.title', name)
            self.setProperty('tubi.live.channel', '')
            self.setProperty('tubi.live.when', '')
            self.setProperty('tubi.live.plot', text((channel or {}).get('description')))
            return
        start, end, program = items[self.cell]
        details = ['%s – %s' % (clock(start), clock(end))]
        if start <= time.time() < end:
            details.insert(0, 'LIVE')
        episode = text(program.get('episode_title'))
        if episode and episode != text(program.get('title')):
            details.append(episode)
        self.setProperty('tubi.live.title', text(program.get('title')))
        self.setProperty('tubi.live.channel', name)
        self.setProperty('tubi.live.when', '  ·  '.join(details))
        self.setProperty('tubi.live.plot', text(program.get('description')))

    # ------------------------------------------------------- navigation

    def move(self, actionId):
        """Programme by programme; the grid itself only moves by one half hour."""
        items = self.programmesOf(self.row)
        if actionId in (UP, DOWN):
            target = self.row + (1 if actionId == DOWN else -1)
            if target < 0:
                self.setFocusId(CATEGORIES)
                return
            if target >= len(self.ids):
                return
            self.row = target
            if self.cell is not None:
                self.cell = self.covering(target, self.cursor)
        elif actionId == RIGHT:
            viewEnd = self.viewStart + SPAN
            if self.cell is None:
                self.selectNow(self.row)
            elif self.cell + 1 < len(items) and items[self.cell + 1][0] < viewEnd:
                self.cell += 1
                start, end, _ = items[self.cell]
                if start + min(end - start, EDGE) > viewEnd:
                    self.viewStart += STEP
            elif self.cell + 1 < len(items) or items[self.cell][1] > viewEnd:
                # The next programme starts beyond the edge: the grid steps on
                # and the selection stays, as in Kodi's own guide.
                self.viewStart += STEP
        elif actionId == LEFT:
            if self.cell is None:
                return
            start, end, _ = items[self.cell]
            back = self.viewStart > self.minStart
            if start < self.viewStart and back:
                self.viewStart -= STEP
            elif self.cell == 0 or start <= time.time():
                # The guide starts with what is on now; before it lies the channel.
                self.cell = None
            else:
                self.cell -= 1
                start, end, _ = items[self.cell]
                if end - min(end - start, EDGE) < self.viewStart and back:
                    self.viewStart -= STEP
        self.keepVisible()
        if self.cell is not None and actionId in (LEFT, RIGHT):
            self.cursor = max(self.programmesOf(self.row)[self.cell][0], self.viewStart)
        self.layout()

    def onAction(self, action):
        actionId = action.getId()
        if actionId in (10, 92):  # Previous menu / back
            self.leave()
            return
        try:
            focus = self.getFocusId()
        except RuntimeError:
            return
        if focus == GRID and actionId in (LEFT, RIGHT, UP, DOWN):
            self.move(actionId)

    def onClick(self, controlId):
        if controlId == GRID:
            self.play()
        elif controlId == CATEGORIES:
            index = self.getControl(CATEGORIES).getSelectedPosition()
            if 0 <= index < len(self.categories) and index != self.category:
                self.loadCategory(index)
            else:
                self.setFocusId(GRID)
        elif controlId == 304:
            self.setFocusId(GRID)
        elif controlId in (301, 302, 303, 305):
            self.navbar = controlId
            self.leave()

    def play(self):
        items = self.programmesOf(self.row)
        now = time.time()
        if self.cell is not None and self.cell < len(items):
            start, end, _ = items[self.cell]
            if not start <= now < end:
                return  # future programmes: information only
        channelId = self.ids[self.row]
        self.addon.note('TUBI-LIVE play channel %s row=%d cell=%s' % (channelId, self.row, self.cell))
        xbmc.executebuiltin('PlayMedia("%s")' % (PLAY % channelId))

    def loadCategory(self, index):
        started = time.monotonic()
        with self.lock:
            self.setCategory(index)
            # Programmes already fetched in this window are reused; only
            # channels not seen yet need Tubi, with the grid showing it.
            missing = [i for i in self.ids if i not in self.guide]
            if missing:
                self.cell = None
                self.setProperty('tubi.live.status', self.addon.localLang(30072) or 'Loading…')
                self.layout()
        if missing:
            try:
                self.guide.update(programmes(self.addon.api, missing))
            except TubiApiError as err:
                self.addon.note('TUBI-LIVE guide failed: ' + type(err).__name__, xbmc.LOGERROR)
        with self.lock:
            if self.closed:
                return
            self.setProperty('tubi.live.status', '')
            # A new category starts at the current time again.
            self.viewStart = self.minStart = viewOrigin()
            self.selectNow(0)
            self.keepVisible()
            self.layout()
            self.setFocusId(GRID)
        self.addon.note('TUBI-LIVE category %s: %d channels in %.2f s' % (
            self.categories[index][0], len(self.ids), time.monotonic() - started))

    def leave(self):
        with self.lock:
            if not self.closed:
                self.closed = True
                self.close()


def showLive(addon, idle=None):
    """Show the guide over Home; return (navbar target, abandoned).

    The navbar target is False when the guide could not open at all, so
    the caller leaves its focus where it was.
    """
    started = time.monotonic()

    def load():
        categories, channels = lineUp(addon.api)
        guide = programmes(addon.api, [str(i) for i in categories[0][1]]) if categories else {}
        return categories, channels, guide

    loaded = coverLoad(addon, load, 'TUBI-LIVE')
    if loaded is None:
        return False, False
    cover, (categories, channels, guide) = loaded
    if not categories:
        cover.close()
        xbmcgui.Dialog().notification(addon.addonName, addon.localLang(30074) or 'Could not load titles.')
        return False, False
    window = TubiLive('TubiLive.xml', addon.homeDir, 'Default', '1080i')
    window.addon = addon
    window.categories = categories
    window.channels = channels
    window.guide = guide
    window.ids = [str(i) for i in categories[0][1]]
    addon.note('TUBI-LIVE ready: %d categories, %d channels, %s first in %.2f s' % (
        len(categories), len(channels), categories[0][0], time.monotonic() - started))
    abandoned = False
    cover.close()
    try:
        window.show()
        monitor = xbmc.Monitor()
        minute = int(time.time() // 30)
        while not window.closed:
            if idle is not None:
                idle()
            current = xbmcgui.getCurrentWindowId()
            if window.windowId and current not in (window.windowId, 12005, 12006):
                addon.note('TUBI-LIVE abandoned for window %d' % current)
                window.closed = abandoned = True
                break
            # The NOW line and progress move every half minute.
            if window.started and int(time.time() // 30) != minute and current == window.windowId:
                minute = int(time.time() // 30)
                window.layout()
            if monitor.waitForAbort(0.2):
                break
    finally:
        window.leave()
        navbar = window.navbar
        del window
    return navbar, abandoned
