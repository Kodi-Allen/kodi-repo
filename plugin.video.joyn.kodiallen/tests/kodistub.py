# -*- coding: utf-8 -*-
"""Just enough of Kodi's Python modules to run the add-on's logic outside Kodi."""
import atexit
import os
import re
import shutil
import sys
import tempfile
import types

ADDON_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ADDON_ROOT not in sys.path:
    sys.path.insert(0, ADDON_ROOT)

LOG = []
SETTINGS = {}
PROFILE = tempfile.mkdtemp(prefix='joyn-test-profile-')
# Sessions written during a run may hold tokens; never leave them behind.
atexit.register(shutil.rmtree, PROFILE, True)


def strings():
    """The add-on's English strings, as getLocalizedString returns them."""
    path = os.path.join(ADDON_ROOT, 'resources', 'language', 'resource.language.en_gb', 'strings.po')
    table = {}
    with open(path, 'r') as handle:
        text = handle.read()
    for stringId, value in re.findall(r'msgctxt "#(\d+)"\nmsgid "(.*)"', text):
        table[int(stringId)] = value.replace('\\"', '"')
    return table


STRINGS = strings()


class Addon(object):
    def __init__(self, addonId=None):
        self.addonId = addonId

    def getSetting(self, key):
        return SETTINGS.get(key, '')

    def setSetting(self, key, value):
        SETTINGS[key] = value

    def getLocalizedString(self, stringId):
        return STRINGS.get(stringId, '')

    def getAddonInfo(self, key):
        return {'name': 'Joyn', 'path': ADDON_ROOT, 'profile': PROFILE,
                'id': self.addonId, 'version': '21.5.18'}.get(key, '')


class InfoTag(object):
    """Kodi 21's InfoTagVideo: any setter, but only the getters it really has."""
    GETTERS = ('getTitle', 'getTVShowTitle', 'getPlot', 'getSeason', 'getEpisode', 'getDuration',
               'getYear', 'getMediaType', 'getGenres', 'getStudios', 'getResumeTime', 'getResumeTimeTotal')

    def __init__(self):
        self.values = {}

    def __getattr__(self, name):
        if name.startswith('set'):
            return lambda value: self.values.__setitem__(name[3:].lower(), value)
        if name in self.GETTERS:
            key = name[3:].lower()
            return lambda: self.values.get(key, 0 if key in ('season', 'episode', 'duration', 'year') else '')
        raise AttributeError(name)


class ListItem(object):
    def __init__(self, label='', label2='', path='', offscreen=False):
        self.label, self.label2, self.path = label, label2, path
        self.art, self.properties, self.tag = {}, {}, InfoTag()
        self.mime = None

    def getLabel(self):
        return self.label

    def setLabel(self, label):
        self.label = label

    def setArt(self, art):
        self.art.update(art)

    def getArt(self, key):
        return self.art.get(key, '')

    def setProperty(self, key, value):
        self.properties[key] = value

    def getProperty(self, key):
        return self.properties.get(key, '')

    def getVideoInfoTag(self):
        return self.tag

    def setMimeType(self, mime):
        self.mime = mime

    def setContentLookup(self, value):
        pass


RESOLVED = []
NOTIFIED = []


def install():
    xbmc = types.ModuleType('xbmc')
    xbmc.LOGDEBUG, xbmc.LOGINFO, xbmc.LOGWARNING, xbmc.LOGERROR = 0, 1, 2, 3
    xbmc.log = lambda msg='', level=0: LOG.append((level, msg))
    xbmc.executebuiltin = lambda command: LOG.append((1, 'builtin ' + command))
    xbmc.executeJSONRPC = lambda request: '{"result": {"channels": []}}'
    xbmc.getLocalizedString = lambda stringId: {20373: 'Season', 20360: 'Episodes'}.get(stringId, '')
    xbmc.getCondVisibility = lambda condition: False
    xbmc.getInfoLabel = lambda label: ''
    xbmc.Monitor = type('Monitor', (), {'abortRequested': lambda self: False,
                                        'waitForAbort': lambda self, seconds=0: False})
    xbmcaddon = types.ModuleType('xbmcaddon')
    xbmcaddon.Addon = Addon
    xbmcgui = types.ModuleType('xbmcgui')
    xbmcgui.ListItem = ListItem
    xbmcgui.NOTIFICATION_INFO, xbmcgui.NOTIFICATION_WARNING, xbmcgui.NOTIFICATION_ERROR = 'info', 'warning', 'error'
    xbmcgui.Dialog = type('Dialog', (), {'notification': lambda self, *args, **kwargs: NOTIFIED.append(args)})
    xbmcgui.Window = type('Window', (), {'__init__': lambda self, windowId=0: None,
                                         'getProperty': lambda self, key: '',
                                         'setProperty': lambda self, key, value: None,
                                         'clearProperty': lambda self, key: None})
    xbmcgui.WindowXML = type('WindowXML', (), {})
    xbmcgui.WindowXMLDialog = type('WindowXMLDialog', (), {})
    xbmcplugin = types.ModuleType('xbmcplugin')
    xbmcplugin.setResolvedUrl = lambda handle, ok, item: RESOLVED.append((ok, item))
    xbmcvfs = types.ModuleType('xbmcvfs')
    xbmcvfs.translatePath = lambda path: path
    for module in (xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs):
        sys.modules[module.__name__] = module


install()
