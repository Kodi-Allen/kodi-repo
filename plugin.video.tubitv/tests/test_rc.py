"""Release candidate checks for playback, sign-in state, title actions,
resume and the loading cover, run against stand-ins for Kodi's modules."""
import hashlib
import importlib
import json
import os
import shutil
import struct
import sys
import tempfile
import time
import types
import unittest
from unittest import mock


ADDON_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ADDON_ROOT not in sys.path:
    sys.path.insert(0, ADDON_ROOT)

from resources.lib import device  # noqa: E402  (no Kodi imports)
from resources.lib import tubi_api  # noqa: E402  (no Kodi imports)


# ---------------------------------------------------------------- Kodi stubs

class Settings(object):
    def __init__(self, values=None, profile='/tmp'):
        self.values = dict(values or {})
        self.profile = profile

    def getSetting(self, key):
        return self.values.get(key, '')

    def setSetting(self, key, value):
        self.values[key] = value

    def getAddonInfo(self, key):
        return {'name': 'TubiTV', 'profile': self.profile, 'path': '/addon',
                'version': '21.5.0', 'id': 'plugin.video.tubitv'}.get(key, '')

    def getLocalizedString(self, number):
        return 'L%d' % number


class Tag(object):
    def __init__(self):
        self.values = {}
        self.resume = (0.0, 0.0)

    def setResumePoint(self, position, total):
        self.resume = (position, total)

    def getResumeTime(self):
        return self.resume[0]

    def getResumeTimeTotal(self):
        return self.resume[1]

    def __getattr__(self, name):
        if name.startswith(('set', 'add')):
            return lambda *args, **kwargs: self.values.__setitem__(name, args)
        raise AttributeError(name)


class ListItem(object):
    def __init__(self, label='', label2='', path='', offscreen=False):
        self.label, self.path = label, path
        self.properties, self.tag, self.menu = {}, Tag(), None

    def setProperty(self, key, value):
        self.properties[key] = value

    def getProperty(self, key):
        return self.properties.get(key, '')

    def getVideoInfoTag(self):
        return self.tag

    def addContextMenuItems(self, items):
        self.menu = items

    def setLabel(self, label):
        self.label = label

    def getLabel(self):
        return self.label

    def __getattr__(self, name):
        if name.startswith('set'):
            return lambda *args, **kwargs: None
        raise AttributeError(name)


class Recorder(object):
    """Collects every call made to a stub module function."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append(args)


def kodiStubs(addonSettings, conditions=()):
    windowProps = {}
    xbmc = types.SimpleNamespace(
        LOGDEBUG=0, LOGINFO=1, LOGWARNING=2, LOGERROR=4,
        log=lambda *a, **k: None, getInfoLabel=lambda label: '',
        getCondVisibility=lambda cond: cond in conditions,
        executebuiltin=Recorder(),
        getLocalizedString=lambda n: {12021: 'Play from beginning',
                                      12022: 'Resume from {0:s}'}.get(n, ''),
        Actor=lambda *a, **k: None, VideoStreamDetail=lambda **k: None,
        AudioStreamDetail=lambda **k: None, SubtitleStreamDetail=lambda **k: None)
    played = []

    class Player(object):
        def play(self, item=None, listitem=None):
            played.append((item, listitem))

    class Monitor(object):
        def waitForAbort(self, seconds=0):
            time.sleep(seconds)
            return False

    xbmc.Player, xbmc.Monitor, xbmc.played = Player, Monitor, played

    class Window(object):
        def __init__(self, windowId=0):
            pass

        def setProperty(self, key, value):
            windowProps[key] = value

        def getProperty(self, key):
            return windowProps.get(key, '')

        def clearProperty(self, key):
            windowProps.pop(key, None)

    class Dialog(object):
        choice = -1
        notified = []
        offered = []

        def notification(self, *args, **kwargs):
            Dialog.notified.append(args)

        def contextmenu(self, labels):
            Dialog.offered.append(list(labels))
            return Dialog.choice

    class WindowXML(object):
        def __init__(self, *args, **kwargs):
            self.shown = self.closed = False

        def show(self):
            self.shown = True

        def close(self):
            self.closed = True

    xbmcgui = types.SimpleNamespace(
        ListItem=ListItem, Window=Window, Dialog=Dialog, WindowXML=WindowXML,
        WindowXMLDialog=WindowXML, NOTIFICATION_INFO='info',
        NOTIFICATION_WARNING='warning', NOTIFICATION_ERROR='error',
        getCurrentWindowId=lambda: 13000, getCurrentWindowDialogId=lambda: 9999)
    resolved = Recorder()
    xbmcplugin = types.SimpleNamespace(setResolvedUrl=resolved, setContent=Recorder())
    addons = {'inputstream.adaptive': Settings(),
              'script.module.inputstreamhelper': Settings()}
    xbmcaddon = types.SimpleNamespace(Addon=lambda addonId=None: addons.get(addonId, addonSettings))
    xbmcvfs = types.SimpleNamespace(translatePath=lambda value: value,
                                    exists=os.path.exists, mkdirs=os.makedirs)

    class t1mAddon(object):
        def __init__(self, aname):
            self.addon = addonSettings
            self.addonName = 'TubiTV'
            self.localLang = addonSettings.getLocalizedString
            self.homeDir = '/addon'
            self.defaultHeaders = {'User-Agent': 'test-agent'}
            self.defaultVidStream = {'codec': 'h264', 'width': 1280, 'height': 720, 'aspect': 1.78}
            self.defaultAudStream = {'codec': 'aac', 'language': 'en'}
            self.defaultSubStream = {'language': 'en'}

        def log(self, txt):
            pass

    t1mlib = types.SimpleNamespace(t1mAddon=t1mAddon)
    return {'xbmc': xbmc, 'xbmcgui': xbmcgui, 'xbmcplugin': xbmcplugin,
            'xbmcaddon': xbmcaddon, 'xbmcvfs': xbmcvfs, 't1mlib': t1mlib}


ISOLATED = ('scraper', 'context', 'series', 'tubi_auth')


def isolated(stubs, *names):
    """Import resources.lib modules against the stubs and leave nothing behind.

    The other test modules install their own Kodi stand-ins and reload
    tubi_auth/tubi_api by name, so neither sys.modules nor the package's
    attributes may keep these copies.
    """
    package = importlib.import_module('resources.lib')
    before = {name: getattr(package, name) for name in ISOLATED if hasattr(package, name)}
    modules = {}
    with mock.patch.dict(sys.modules, stubs):
        for name in ISOLATED:
            sys.modules.pop('resources.lib.' + name, None)
        for name in names:
            modules[name] = importlib.import_module('resources.lib.' + name)
    for name in ISOLATED:
        if name in before:
            setattr(package, name, before[name])
        elif hasattr(package, name):
            delattr(package, name)
    return [modules[name] for name in names]


# ------------------------------------------------------------------ H01 DRM

DRM_TITLE = {'id': '589292', 'title': 'An encrypted film', 'video_resources': [{
    'type': tubi_api.DASH_WIDEVINE, 'resolution': 'VIDEO_RESOLUTION_576P',
    'codec': 'VIDEO_CODEC_H264', 'manifest': {'url': 'https://cdn.example/t.mpd'},
    'license_server': {'url': 'https://license.example/l', 'hdcp_version': 'hdcp_disabled'}}]}
CLEAR_TITLE = {'id': '100', 'title': 'A clear film', 'video_resources': [{
    'type': tubi_api.CLEAR, 'resolution': 'VIDEO_RESOLUTION_720P',
    'codec': 'VIDEO_CODEC_H264', 'manifest': {'url': 'https://cdn.example/c.m3u8'}}]}


class DrmPathTest(unittest.TestCase):
    """The add-on hands DRM to inputstream.adaptive instead of refusing it."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home)
        self.argv = mock.patch.object(sys, 'argv', ['plugin://plugin.video.tubitv/', '7', ''])
        self.argv.start()
        self.addCleanup(self.argv.stop)

    def addon(self, conditions=(), cdmPath=None):
        stubs = kodiStubs(Settings({'route_mode': '0'}), conditions)
        default = os.path.join(self.home, 'cdm', 'libwidevinecdm.so')
        stubs['xbmcvfs'].translatePath = lambda value: (
            cdmPath or default) if value.endswith('libwidevinecdm.so') else value
        scraper, = isolated(stubs, 'scraper')
        addon = scraper.myAddon('tubitv')
        addon.api = mock.Mock()
        addon.api.content.return_value = DRM_TITLE
        return stubs, addon

    def resolved(self, stubs):
        self.assertEqual(1, len(stubs['xbmcplugin'].setResolvedUrl.calls))
        _, succeeded, item = stubs['xbmcplugin'].setResolvedUrl.calls[0]
        return succeeded, item

    def assertReachesInputStream(self, stubs, drm=True):
        succeeded, item = self.resolved(stubs)
        self.assertTrue(succeeded)
        self.assertEqual('inputstream.adaptive', item.properties.get('inputstream'))
        self.assertEqual(drm, 'inputstream.adaptive.drm_legacy' in item.properties)

    def writeCdm(self, path, payload):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as handle:
            handle.write(payload)

    def test_android_without_a_cdm_file_reaches_inputstream(self):
        stubs, addon = self.addon(conditions=('System.Platform.Android', 'System.Platform.Linux'))
        with mock.patch.object(device.platform, 'machine', return_value='aarch64'):
            addon.getAddonVideo('589292')
        self.assertReachesInputStream(stubs)

    def test_windows_with_its_own_cdm_name_reaches_inputstream(self):
        self.writeCdm(os.path.join(self.home, 'cdm', 'widevinecdm.dll'), b'MZ')
        stubs, addon = self.addon(conditions=('System.Platform.Windows',))
        with mock.patch.object(device.platform, 'machine', return_value='AMD64'):
            addon.getAddonVideo('589292')
        self.assertReachesInputStream(stubs)

    def test_macos_with_its_own_cdm_name_reaches_inputstream(self):
        self.writeCdm(os.path.join(self.home, 'cdm', 'libwidevinecdm.dylib'), b'\xcf\xfa\xed\xfe')
        stubs, addon = self.addon(conditions=('System.Platform.OSX',))
        with mock.patch.object(device.platform, 'machine', return_value='arm64'):
            addon.getAddonVideo('589292')
        self.assertReachesInputStream(stubs)

    def test_linux_cdm_outside_the_default_path_reaches_inputstream(self):
        self.writeCdm(os.path.join(self.home, 'custom', 'libwidevinecdm.so'), b'\x7fELF' + b'\x00' * 60)
        stubs, addon = self.addon(conditions=('System.Platform.Linux',))
        addon.getAddonVideo('589292')
        self.assertReachesInputStream(stubs)

    def test_an_old_linux_cdm_version_is_not_refused(self):
        cdm = os.path.join(self.home, 'cdm', 'libwidevinecdm.so')
        header = bytearray(64)
        header[:6] = b'\x7fELF\x01\x01'
        header[18:20] = struct.pack('<H', 40)
        self.writeCdm(cdm, bytes(header) + b'4.10.2662.3\x00')
        stubs, addon = self.addon(conditions=('System.Platform.Linux',), cdmPath=cdm)
        addon.getAddonVideo('589292')
        self.assertReachesInputStream(stubs)

    def test_a_cdm_that_would_crash_kodi_is_still_refused(self):
        cdm = os.path.join(self.home, 'cdm', 'libwidevinecdm.so')
        self.writeCdm(cdm, b'\x7fELF' + b'\x00' * 60 + b'.relr.dyn')
        stubs, addon = self.addon(conditions=('System.Platform.Linux',), cdmPath=cdm)
        with mock.patch.object(device, 'loaderSupportsRelr', return_value=False):
            addon.getAddonVideo('589292')
        succeeded, _ = self.resolved(stubs)
        self.assertFalse(succeeded)

    def test_clear_playback_is_unchanged(self):
        stubs, addon = self.addon(conditions=('System.Platform.Android',))
        addon.api.content.return_value = CLEAR_TITLE
        addon.getAddonVideo('100')
        self.assertReachesInputStream(stubs, drm=False)

    def test_live_playback_is_unchanged(self):
        stubs, addon = self.addon(conditions=('System.Platform.Android',))
        channel = {'id': 400000024, 'video_resources': [{
            'type': tubi_api.LIVE, 'manifest': {'url': 'https://live.example/c.m3u8'}}]}
        addon.api.liveChannels.return_value = ([channel], {})
        addon.getAddonLiveVideo('400000024')
        self.assertReachesInputStream(stubs, drm=False)


# ------------------------------------------------------------- H03 sign-in

def fingerprint(username, password):
    return hashlib.sha256(':'.join([username, password]).encode('utf-8')).hexdigest()


class AccountStateTest(unittest.TestCase):
    """A cached sign-in only counts for the credentials it came from."""

    def setUp(self):
        self.profile = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.profile)
        with open(os.path.join(self.profile, 'session.json'), 'w') as handle:
            json.dump({'device_id': 'device', 'user': {
                'user_id': 111, 'access_token': 'token-a', 'connect_sid': 'sid-a',
                'expires_at': time.time() + 3600,
                'credentials': fingerprint('a@example.test', 'pass-a')}}, handle)

    def auth(self, username, password):
        settings = Settings({'login_name': username, 'login_pass': password}, self.profile)
        tubi_auth, = isolated(kodiStubs(settings), 'tubi_auth')
        auth = tubi_auth.TubiAuth(settings)
        auth.anonymousToken = lambda: 'anonymous'
        return tubi_auth, auth

    def stored(self):
        with open(os.path.join(self.profile, 'session.json')) as handle:
            return json.load(handle)

    def test_a_cleared_credentials_end_account_a(self):
        _, auth = self.auth('', '')
        self.assertFalse(auth.signedIn)
        self.assertIsNone(auth.userId)
        headers = auth.apply({})
        self.assertEqual('Bearer anonymous', headers['Authorization'])
        self.assertNotIn('connect.sid', headers['Cookie'])
        self.assertNotIn('user', self.stored())
        self.assertEqual('device', self.stored()['device_id'])

    def test_b_a_failed_switch_does_not_fall_back_to_account_a(self):
        tubi_auth, auth = self.auth('b@example.test', 'pass-b')
        with mock.patch.object(auth, '_login', side_effect=tubi_auth.TubiAuthError('rejected')):
            headers = {}
            with self.assertRaises(tubi_auth.TubiAuthError):
                auth.apply(headers)
        self.assertEqual('Bearer anonymous', headers['Authorization'])
        self.assertIsNone(auth.userId)
        self.assertFalse(auth.signedIn)
        self.assertNotIn('user', self.stored())

    def test_c_account_a_does_not_return_after_a_restart(self):
        tubi_auth, auth = self.auth('b@example.test', 'pass-b')
        with mock.patch.object(auth, '_login', side_effect=tubi_auth.TubiAuthError('rejected')):
            with self.assertRaises(tubi_auth.TubiAuthError):
                auth.apply({})
        _, restarted = self.auth('b@example.test', 'pass-b')
        self.assertIsNone(restarted.userId)
        self.assertEqual('anonymous', restarted.bearer())
        _, cleared = self.auth('', '')
        self.assertIsNone(cleared.userId)

    def test_d_unchanged_credentials_keep_the_cached_sign_in(self):
        _, auth = self.auth('a@example.test', 'pass-a')
        with mock.patch.object(auth, '_login') as login:
            headers = auth.apply({})
        login.assert_not_called()
        self.assertEqual('Bearer token-a', headers['Authorization'])
        self.assertIn('connect.sid=sid-a', headers['Cookie'])
        self.assertEqual(111, auth.userId)
        self.assertTrue(auth.signedIn)

    def test_an_expired_sign_in_is_renewed_for_the_same_credentials(self):
        data = self.stored()
        data['user']['expires_at'] = time.time() - 10
        with open(os.path.join(self.profile, 'session.json'), 'w') as handle:
            json.dump(data, handle)
        _, auth = self.auth('a@example.test', 'pass-a')
        self.assertIsNone(auth.userId)
        fresh = {'user_id': 111, 'access_token': 'token-a2', 'expires_in': 3600}
        with mock.patch.object(auth, '_login', return_value=fresh), \
                mock.patch.object(auth, '_webSession', return_value='sid-a2'):
            headers = auth.apply({})
        self.assertEqual('Bearer token-a2', headers['Authorization'])
        self.assertEqual(111, auth.userId)

    def test_signed_out_credentials_stay_anonymous(self):
        data = self.stored()
        data['signed_out'] = fingerprint('a@example.test', 'pass-a')
        with open(os.path.join(self.profile, 'session.json'), 'w') as handle:
            json.dump(data, handle)
        _, auth = self.auth('a@example.test', 'pass-a')
        self.assertEqual('anonymous', auth.bearer())
        self.assertIsNone(auth.userId)


# ------------------------------------------------- H02 title actions, M01

MOVIE = {'id': 589292, 'type': 'v', 'title': 'A film', 'has_trailer': True}
SHOW = {'id': 300, 'type': 's', 'title': 'A show'}


class TitleActionTest(unittest.TestCase):
    """The custom pages offer the classic listings' title actions."""

    def setUp(self):
        self.argv = mock.patch.object(sys, 'argv', ['plugin://plugin.video.tubitv/', '-1', ''])
        self.argv.start()
        self.addCleanup(self.argv.stop)
        self.stubs = kodiStubs(Settings({'route_mode': '0'}))
        self.scraper, self.context = isolated(self.stubs, 'scraper', 'context')
        self.Dialog = self.stubs['xbmcgui'].Dialog
        self.Dialog.choice, self.Dialog.offered, self.Dialog.notified = -1, [], []

    def addon(self, signedIn, history=()):
        addon = self.scraper.myAddon('tubitv')
        addon.auth = types.SimpleNamespace(signedIn=signedIn)
        addon.api = mock.Mock()
        addon.api.queue.return_value = []
        addon.api.history.return_value = list(history)
        return addon

    def item(self, addon, content):
        return self.context.addContent(addon, content, [])[-1][1]

    def labels(self, addon, item):
        return [label for label, _ in self.context.entries(addon, item)[1]]

    def test_signed_in_movie_offers_every_action(self):
        addon = self.addon(True)
        self.assertEqual(['L30025', 'L30041', 'L30034', 'L30035', 'L30045', 'L30046'],
                         self.labels(addon, self.item(addon, MOVIE)))

    def test_series_offers_show_export_and_no_trailer_without_one(self):
        addon = self.addon(True)
        self.assertEqual(['L30024', 'L30041', 'L30034', 'L30045', 'L30046'],
                         self.labels(addon, self.item(addon, SHOW)))

    def test_signed_out_hides_account_actions(self):
        addon = self.addon(False)
        self.assertEqual(['L30025', 'L30034', 'L30035'],
                         self.labels(addon, self.item(addon, MOVIE)))

    def test_actions_run_the_existing_routes(self):
        addon = self.addon(True)
        item = self.item(addon, MOVIE)
        _, menu = self.context.entries(addon, item)
        actions = dict(menu)
        self.assertEqual('RunPlugin(plugin://plugin.video.tubitv/?mode=AM&url=589292)', actions['L30025'])
        self.assertIn('?mode=DF&url=queue%7Cadd%7C589292%7C', actions['L30041'])
        self.assertIn('PlayMedia(plugin://plugin.video.tubitv/?mode=GV&url=trailer%7C589292)', actions['L30035'])
        self.assertIn('?mode=DF&url=rate%7Clike%7C589292%7C0', actions['L30045'])

    def test_my_list_choice_runs_once_and_the_next_menu_offers_removal(self):
        addon = self.addon(True)
        item = self.item(addon, MOVIE)
        self.Dialog.choice = 1
        self.assertIsNone(self.context.show(addon, item))
        builtins = self.stubs['xbmc'].executebuiltin.calls
        self.assertEqual(1, len(builtins))
        self.assertIn('queue%7Cadd%7C589292', builtins[0][0])
        self.assertIn('L30042', self.labels(addon, item))

    def test_related_titles_open_as_a_custom_page(self):
        addon = self.addon(True)
        item = self.item(addon, MOVIE)
        self.Dialog.choice = 2
        info = self.context.show(addon, item)
        self.assertEqual({'id': '589292', 'title': 'A film'}, {k: info[k] for k in ('id', 'title')})
        self.assertEqual([], self.stubs['xbmc'].executebuiltin.calls)

    def test_back_in_the_menu_does_nothing(self):
        addon = self.addon(True)
        self.assertIsNone(self.context.show(addon, self.item(addon, MOVIE)))
        self.assertEqual([], self.stubs['xbmc'].executebuiltin.calls)

    # M01: the resume point comes from the same watch history as before
    def resumeItem(self, position, length):
        entry = {'content_id': 589292, 'id': 'h1', 'position': position, 'content_length': length}
        addon = self.addon(True, history=[entry])
        return self.item(addon, MOVIE)

    def test_resume_point_cases(self):
        resumePoint = self.context.resumePoint
        self.assertIsNone(resumePoint(self.item(self.addon(True), MOVIE)))          # none
        self.assertEqual((600.0, 5400.0), resumePoint(self.resumeItem(600, 5400)))  # partial
        self.assertEqual((5390.0, 5400.0), resumePoint(self.resumeItem(5390, 5400)))  # near end
        self.assertIsNone(resumePoint(self.resumeItem(600, None)))                  # no length
        self.assertIsNone(resumePoint(self.resumeItem(600, 0)))                     # zero length
        self.assertIsNone(resumePoint(self.resumeItem(6000, 5400)))                 # past the end
        broken = ListItem()
        broken.tag.resume = ('x', 'y')
        self.assertIsNone(resumePoint(broken))                                      # not numbers

    def test_play_without_resume_keeps_play_media(self):
        url = 'plugin://plugin.video.tubitv/?mode=GV&url=589292'
        self.context.play(url, self.item(self.addon(True), MOVIE))
        self.assertEqual([('PlayMedia("%s")' % url,)], self.stubs['xbmc'].executebuiltin.calls)
        self.assertEqual([], self.Dialog.offered)

    def test_play_resumes_at_tubis_position(self):
        url = 'plugin://plugin.video.tubitv/?mode=GV&url=589292'
        self.Dialog.choice = 0
        self.context.play(url, self.resumeItem(600, 5400))
        self.assertEqual(['Resume from 10:00', 'Play from beginning'], self.Dialog.offered[0])
        (played, item), = self.stubs['xbmc'].played
        self.assertEqual(url, played)
        self.assertEqual('600.000', item.properties['StartOffset'])
        self.assertEqual('true', item.properties['IsPlayable'])

    def test_play_from_the_beginning_and_back(self):
        url = 'plugin://plugin.video.tubitv/?mode=GV&url=589292'
        self.Dialog.choice = 1
        self.context.play(url, self.resumeItem(600, 5400))
        (_, item), = self.stubs['xbmc'].played
        self.assertNotIn('StartOffset', item.properties)
        self.Dialog.choice = -1
        self.context.play(url, self.resumeItem(600, 5400))
        self.assertEqual(1, len(self.stubs['xbmc'].played))


# ------------------------------------------------------- M02 loading cover

class CoverLoadTest(unittest.TestCase):
    """A custom page gives up behind its loading cover after a deadline."""

    def setUp(self):
        self.stubs = kodiStubs(Settings())
        self.series, = isolated(self.stubs, 'series')
        self.Dialog = self.stubs['xbmcgui'].Dialog
        self.Dialog.notified = []
        self.addon = types.SimpleNamespace(homeDir='/addon', addonName='TubiTV',
                                           localLang=lambda n: 'L%d' % n, note=lambda *a: None)
        self.covers = []
        original = self.series.Cover

        def cover(*args, **kwargs):
            made = original(*args, **kwargs)
            self.covers.append(made)
            return made
        patcher = mock.patch.object(self.series, 'Cover', side_effect=cover)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_dead_connection_closes_the_cover_at_the_deadline(self):
        started = time.monotonic()
        result = self.series.coverLoad(self.addon, lambda: time.sleep(3), 'TEST', deadline=0.3)
        self.assertIsNone(result)
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertTrue(self.covers[0].closed)
        self.assertEqual('L30022', self.Dialog.notified[-1][1])

    def test_a_failed_load_closes_the_cover_once(self):
        def fail():
            raise tubi_api.TubiApiError('down')
        self.assertIsNone(self.series.coverLoad(self.addon, fail, 'TEST'))
        self.assertTrue(self.covers[0].closed)
        self.assertEqual(1, len(self.Dialog.notified))
        self.assertEqual('L30074', self.Dialog.notified[0][1])

    def test_a_loaded_page_keeps_the_cover_for_its_handover(self):
        cover, result = self.series.coverLoad(self.addon, lambda: 'rows', 'TEST')
        self.assertEqual('rows', result)
        self.assertFalse(cover.closed)

    def test_back_gives_up_quietly(self):
        def slow():
            self.covers[0].onAction(types.SimpleNamespace(getId=lambda: 92))
            time.sleep(3)
        started = time.monotonic()
        self.assertIsNone(self.series.coverLoad(self.addon, slow, 'TEST', deadline=10))
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertTrue(self.covers[0].closed)
        self.assertEqual([], self.Dialog.notified)


if __name__ == '__main__':
    unittest.main()
