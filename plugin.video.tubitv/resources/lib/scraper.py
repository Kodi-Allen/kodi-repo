# -*- coding: utf-8 -*-
# KodiAddon (tubitv)
#
import concurrent.futures
import json
import os
import platform
import sys
import urllib.parse
import xml.etree.ElementTree as ET

import requests
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from t1mlib import t1mAddon

from resources.lib.device import deviceModel, widevineCompatibility
from resources.lib.tubi_api import (CLEAR_TYPES, WIDEVINE_TYPES, TubiApi,
                                    TubiApiError, chooseResource,
                                    describeResource, offeredTypes, pickResource)
from resources.lib.tubi_api import EPISODE as HISTORY_EPISODE
from resources.lib.tubi_api import MOVIE as HISTORY_MOVIE
from resources.lib.tubi_api import SERIES as QUEUE_SERIES
from resources.lib.tubi_api import (DISLIKE, LIKE, RATING_DISLIKED, RATING_LIKED,
                                    UNDISLIKE, UNLIKE)
from resources.lib.routing import MediaRouter

uqp = urllib.parse.unquote_plus
qp = urllib.parse.quote_plus

# Tubi's own letter for a series in a content payload. Its watch history calls
# the same thing "series", hence the aliased import above for the other one.
SERIES = 's'
# The window property the service reads to know what is playing
PLAYING = 'tubitv.playing'
PLAYBACK_DIAGNOSTIC = 'tubitv.playback.diagnostic'

WIDEVINE_KEYSYSTEM = 'com.widevine.alpha'
# Tubi's licence URL is issued to its web-client context. Keep Origin,
# Referer and User-Agent consistent with the API request while passing the raw
# challenge and raw licence unchanged.
LICENSE_HEADERS = [('Content-Type', 'application/octet-stream'),
                   ('Origin', 'https://tubitv.com'),
                   ('Referer', 'https://tubitv.com/')]
# inputstream.adaptive 21 introduced drm_legacy. Older builds only understand
# the classic license_type/license_key pair.
DRM_PROPERTIES_SINCE = 21
# The same release works the manifest type out for itself and warns about
# being told; 22 has dropped the property altogether.
MANIFEST_TYPE_UNTIL = 21
CDM_PATH = 'special://home/cdm/libwidevinecdm.so'
# Widevine revoked older CDM generations in 2025. Tubi now rejects the final
# ARM32 CDM (4.10.2662.3) with 401 / error code 403. Refuse the known-dead
# licence attempt before Kodi shows only the clear lead and then stalls.
TUBI_MINIMUM_CDM = '4.10.2891.0'


# InfoTagVideo's own setters, and the stream detail classes, arrived in Kodi
# 20. Kodi 19 only has ListItem.setInfo()/addStreamInfo(), which everything
# after it warns about on every single list item.
INFOTAG_SETTERS = hasattr(xbmc, 'VideoStreamDetail')


def asInt(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def inputstreamMajor():
    """Major version of the installed inputstream.adaptive, 0 if unknown."""
    try:
        version = xbmcaddon.Addon('inputstream.adaptive').getAddonInfo('version')
        return int(version.split('.')[0])
    except Exception:
        return 0


def manifestKind(manifest):
    """Return the InputStream manifest kind for a resolved URL."""
    path = urllib.parse.urlsplit(manifest or '').path.lower()
    return 'mpd' if path.endswith('.mpd') else 'hls'


def manifestMime(manifest):
    return ('application/dash+xml' if manifestKind(manifest) == 'mpd'
            else 'application/x-mpegURL')


def manifestProperties(manifest):
    """Tell inputstream.adaptive the manifest type, on builds that want it.

    Everything Tubi serves is HLS. inputstream.adaptive 21 detects that by
    itself and logs a deprecation warning on every playback for being told
    anyway, and 22 has removed the property; older builds still need it.
    An unreadable version keeps the property rather than dropping it.
    """
    if inputstreamMajor() >= MANIFEST_TYPE_UNTIL:
        return []
    return [('inputstream.adaptive.manifest_type', manifestKind(manifest))]


def safeUrl(url):
    """Mask query values in a URL while retaining useful endpoint detail."""
    if not url:
        return 'none'
    try:
        parsed = urllib.parse.urlsplit(url)
        keys = sorted(set(key for key, _ in urllib.parse.parse_qsl(
            parsed.query, keep_blank_values=True)))
        query = '&'.join('%s=MASKED' % urllib.parse.quote(key, safe='[]')
                         for key in keys)
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc,
                                       parsed.path, query, ''))
    except Exception:
        return 'unparseable-url'


def osRelease(path='/etc/os-release'):
    """Return the distribution's display name without importing distro."""
    try:
        values = {}
        with open(path, 'r') as release:
            for line in release:
                key, separator, value = line.rstrip().partition('=')
                if separator:
                    values[key] = value.strip().strip('"')
        return values.get('PRETTY_NAME') or values.get('NAME') or platform.system()
    except (IOError, OSError):
        return platform.system()


class myAddon(t1mAddon):

    def __init__(self, aname):
        t1mAddon.__init__(self, aname)
        # t1mlib expects resources/icon.png and mis-joins the fanart path,
        # this addon keeps its artwork under resources/images/
        self.addonIcon = xbmcvfs.translatePath(os.path.join(self.homeDir, 'resources', 'images', 'icon.png'))
        self.addonFanart = xbmcvfs.translatePath(os.path.join(self.homeDir, 'resources', 'images', 'fanart.jpg'))
        # default.py fills these in once the tokens are sorted out
        self.auth = None
        self.api = None
        self.router = MediaRouter(self.addon)
        # The saved list and the part-watched list, each read once per
        # listing rather than once per item
        self._saved = None
        self._watching = None

    def mediaUrl(self, url):
        """Route an HTTP(S) asset through GeoTV when custom mode is active."""
        return self.router.route(url)

    def addMenuItem(self, name, mode, ilist=None, url=None, thumb=None, fanart=None,
                    videoInfo=None, videoStream=None, audioStream=None,
                    subtitleStream=None, cm=None, isFolder=True):
        """As t1mlib's, but filling the info tag through its own setters.

        t1mlib still builds list items with ListItem.setInfo() and
        addStreamInfo(), which Kodi deprecated and warns about once per item -
        several lines of log for every directory. Overriding it here leaves
        the shared module alone for whatever else depends on it.
        """
        if not INFOTAG_SETTERS:
            return t1mAddon.addMenuItem(self, name, mode, ilist, url, thumb, fanart,
                                        videoInfo, videoStream, audioStream,
                                        subtitleStream, cm, isFolder)
        liz = xbmcgui.ListItem(name, offscreen=True)
        thumb = self.mediaUrl(thumb)
        fanart = self.mediaUrl(fanart)
        liz.setArt({'thumb': thumb, 'fanart': fanart, 'poster': thumb})
        self.fillInfoTag(liz, videoInfo or {})
        if cm is not None:
            liz.addContextMenuItems(cm)
        if not isFolder:
            liz.setProperty('IsPlayable', 'true')
        u = ''.join([sys.argv[0], '?mode=', str(mode), '&url='])
        if url is not None:
            u = ''.join([u, qp(url)])
        ilist.append((u, liz, isFolder))
        return ilist

    def fillInfoTag(self, liz, info):
        """Put an addMenuItem info dict onto a list item's video tag."""
        tag = liz.getVideoInfoTag()
        if info.get('mediatype'):
            tag.setMediaType(info['mediatype'])
        if info.get('Title'):
            tag.setTitle(info['Title'])
        if info.get('TVShowTitle'):
            tag.setTvShowTitle(info['TVShowTitle'])
        if info.get('Plot'):
            tag.setPlot(info['Plot'])
        if info.get('MPAA'):
            tag.setMpaa(info['MPAA'])
        if info.get('director'):
            tag.setDirectors([info['director']])
        if info.get('genre'):
            # The dict carries them joined for the old setInfo, split them back
            tag.setGenres([g.strip() for g in str(info['genre']).split('/') if g.strip()])
        if info.get('cast'):
            tag.setCast([xbmc.Actor(str(person)) for person in info['cast']])
        for key, setter in (('Year', tag.setYear),
                            ('duration', tag.setDuration),
                            ('Season', tag.setSeason),
                            ('Episode', tag.setEpisode)):
            value = asInt(info.get(key))
            if value is not None:
                setter(value)
        # t1mlib attaches the same nominal stream details to every item
        tag.addVideoStream(xbmc.VideoStreamDetail(
            width=self.defaultVidStream['width'],
            height=self.defaultVidStream['height'],
            aspect=self.defaultVidStream['aspect'],
            codec=self.defaultVidStream['codec']))
        tag.addAudioStream(xbmc.AudioStreamDetail(
            codec=self.defaultAudStream['codec'],
            language=self.defaultAudStream['language']))
        tag.addSubtitleStream(xbmc.SubtitleStreamDetail(
            language=self.defaultSubStream['language']))

    def note(self, txt, level=None):
        """Log at a level a normal Kodi log will actually show.

        t1mlib's log() is fixed at debug, which is fine for the routine
        chatter but hides anything worth knowing about from anyone not
        already running a debug log.
        """
        xbmc.log(msg=''.join([self.addonName, ' : ', str(txt)]),
                 level=xbmc.LOGINFO if level is None else level)

    def debug(self, txt):
        """Log the routine chatter, which a normal Kodi log leaves out.

        The counterpart to note(): useful when diagnosing something, noise
        in everyone else's log.
        """
        xbmc.log(msg=''.join([self.addonName, ' : ', str(txt)]), level=xbmc.LOGDEBUG)

    def diag(self, txt):
        """Emit opt-in diagnostics at a level visible in a normal Kodi log."""
        if self.addon.getSetting('diagnostic_logging') == 'true':
            self.note('DRM diagnostic : %s' % txt)

    @staticmethod
    def addonVersion(addonId):
        try:
            return xbmcaddon.Addon(addonId).getAddonInfo('version') or 'unknown'
        except Exception:
            return 'not installed'

    def widevineEnvironment(self):
        """Log platform, ISA and CDM capabilities without loading the CDM."""
        cdmPath = xbmcvfs.translatePath(CDM_PATH)
        safe, reason, details = widevineCompatibility(
            cdmPath, minimumVersion=TUBI_MINIMUM_CDM)
        self.diag('platform machine=%s userspace=%s-bit os=%s model=%s Kodi=%s' % (
            details['machine'], details['pointer_bits'], osRelease(),
            deviceModel() or 'unknown', xbmc.getInfoLabel('System.BuildVersion') or 'unknown'))
        self.diag('inputstream.adaptive version=%s enabled=%s; '
                  'inputstreamhelper version=%s' % (
                      self.addonVersion('inputstream.adaptive'),
                      xbmc.getCondVisibility('System.HasAddon(inputstream.adaptive)'),
                      self.addonVersion('script.module.inputstreamhelper')))
        self.diag('Widevine path=%s version=%s ELF=%s-bit/%s RELR=%s; '
                  'loader=%s RELR-support=%s result=%s' % (
                      details['path'], details['version'] or 'unknown',
                      details['elf_class'] or 'unknown', details['architecture'],
                      details['has_relr'], details['loader'] or 'unknown',
                      details['loader_relr'], reason))
        return safe, reason, details

    def prepareWidevine(self):
        """Reject fatal ABI mismatches without opening a second Kodi dialog.

        InputStream Helper remains the supported way to install Widevine, but
        ``check_inputstream()`` may open a progress/settings dialog. Calling it
        while Kodi already displays the plugin-resolution busy dialog can make
        older Kodi builds abort on two concurrent busy dialogs. Runtime checks
        therefore stay read-only and non-interactive.
        """
        safe, reason, _ = self.widevineEnvironment()
        return safe, reason

    def diagnoseResources(self, content, chosen):
        resources = content.get('video_resources') or []
        self.diag('Tubi title id=%s resources=%s selected=%s' % (
            content.get('id'), len(resources), describeResource(chosen)))
        for index, resource in enumerate(resources):
            if resource.get('type') not in CLEAR_TYPES + WIDEVINE_TYPES:
                continue
            manifest = (resource.get('manifest') or {}).get('url')
            licence = (resource.get('license_server') or {}).get('url')
            self.diag('resource[%s] %s manifest=%s license=%s' % (
                index, describeResource(resource), safeUrl(manifest), safeUrl(licence)))

    def diagnoseManifest(self, manifest):
        """Log DASH tracks and ContentProtection without exposing PSSH or tokens."""
        if self.addon.getSetting('diagnostic_logging') != 'true':
            return
        if manifestKind(manifest) != 'mpd':
            self.diag('manifest type=HLS url=%s' % safeUrl(manifest))
            return
        try:
            headers = {}
            for key in ('User-Agent', 'Accept-Language'):
                if self.defaultHeaders.get(key):
                    headers[key] = self.defaultHeaders[key]
            response = requests.get(manifest, headers=headers, timeout=15,
                                    **self.api.requestKwargs)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            protections = []
            representations = []
            for element in root.iter():
                kind = element.tag.rsplit('}', 1)[-1]
                if kind == 'ContentProtection':
                    scheme = element.get('schemeIdUri') or 'unknown'
                    hasPssh = any(child.tag.rsplit('}', 1)[-1].lower() == 'pssh'
                                  and bool((child.text or '').strip()) for child in element)
                    entry = '%s pssh=%s' % (scheme, hasPssh)
                    if entry not in protections:
                        protections.append(entry)
                elif kind == 'Representation':
                    representations.append('%sx%s bw=%s codec=%s fps=%s' % (
                        element.get('width') or '?', element.get('height') or '?',
                        element.get('bandwidth') or '?', element.get('codecs') or '?',
                        element.get('frameRate') or '?'))
            self.diag('manifest type=DASH url=%s ContentProtection=[%s]' % (
                safeUrl(manifest), '; '.join(protections) or 'none'))
            self.diag('DASH representations=[%s]' %
                      ('; '.join(representations) if representations else 'none'))
        except Exception as err:
            # Exception strings from requests may contain the tokenized URL.
            self.diag('manifest inspection failed: %s' % err.__class__.__name__)

    def report(self, err):
        """Surface an API failure without taking the whole directory down."""
        self.note(''.join(['api call failed : ', str(err)]), level=xbmc.LOGWARNING)
        xbmcgui.Dialog().notification(self.addonName, self.localLang(30022),
                                      xbmcgui.NOTIFICATION_ERROR)

    def makeLibraryPath(self, ftype, name=None):
        """Where "Add to Library" writes its .strm files.

        t1mlib puts them under script.module.t1mlib's profile - a folder
        belonging to a dependency, which nobody would think to add as a
        video source and which Kodi therefore never scans. The export
        appears to do nothing at all. They go under this addon's own
        profile instead, and the path is logged so it can be found.
        """
        if name is None:
            name = self.cleanFilename(
                xbmc.getInfoLabel('ListItem.Title').replace('(Series)', '', 1).strip())
        profile = xbmcvfs.translatePath(self.addon.getAddonInfo('profile'))
        target = os.path.join(profile, str(ftype), name)
        if not os.path.isdir(target):
            os.makedirs(target)
        self.debug('library export : %s' % target)
        return target

    def addMovieToLibrary(self, url):
        """Write a film's .strm, titled from Tubi rather than from the GUI.

        t1mlib names both the folder and the file from
        ListItem.Title. A context menu entry runs through RunPlugin, in a
        process of its own, and that infolabel is read from whatever the
        GUI happens to have focused by then - so it comes back empty often
        enough, and the export becomes a nameless ".strm" in the root of
        the movies folder. The content id is in hand either way, so the
        title is asked for instead of guessed at.
        """
        contentId = uqp(url)
        try:
            title = self.api.content(contentId).get('title')
        except TubiApiError as err:
            self.report(err)
            return
        title = self.cleanFilename(title or '') or contentId
        target = self.makeLibraryPath('movies', name=title)
        strm = os.path.join(target, ''.join([title, '.strm']))
        with open(strm, 'w') as out:
            out.write(''.join([sys.argv[0], '?mode=GV&url=', qp(contentId)]))
        self.debug('library export : wrote %s' % strm)
        self.doScan(target)

    # ------------------------------------------------------------- listings

    @staticmethod
    def firstOf(content, *keys):
        for key in keys:
            values = content.get(key)
            if values:
                return values[0]
        return None

    def infoOf(self, content):
        infoList = {'Title': content.get('title'),
                    'Plot': content.get('description'),
                    'Year': content.get('year'),
                    'duration': content.get('duration'),
                    'cast': content.get('actors') or [],
                    'genre': ' / '.join(content.get('tags') or [])}
        directors = content.get('directors') or []
        if len(directors) > 0:
            infoList['director'] = directors[0]
        ratings = content.get('ratings') or []
        if len(ratings) > 0:
            infoList['MPAA'] = ratings[0].get('value')
        return infoList

    def addContent(self, content, ilist, inList=False):
        """Add one film or series from the API to a directory listing."""
        contentId = str(content.get('id'))
        infoList = self.infoOf(content)
        img = self.firstOf(content, 'posterarts', 'thumbnails') or self.addonIcon
        fanart = self.firstOf(content, 'backgrounds', 'hero_images', 'landscape_images') or self.addonFanart

        if content.get('type') == SERIES:
            name = ''.join([content.get('title') or '', self.localLang(30019)])
            infoList['Title'] = name
            infoList['TVShowTitle'] = content.get('title')
            infoList['mediatype'] = 'tvshow'
            contextMenu = [(self.localLang(30024),
                            'RunPlugin(%s?mode=AS&url=%s)' % (sys.argv[0], qp(contentId)))]
            contextMenu.extend(self.extrasFor(contentId, content, inList))
            return self.addMenuItem(name, 'GE', ilist, contentId, img, fanart, infoList,
                                    isFolder=True, cm=contextMenu)

        infoList['mediatype'] = 'movie'
        contextMenu = [(self.localLang(30025),
                        'RunPlugin(%s?mode=AM&url=%s)' % (sys.argv[0], qp(contentId)))]
        contextMenu.extend(self.extrasFor(contentId, content, inList))
        ilist = self.addMenuItem(content.get('title'), 'GV', ilist, contentId, img, fanart,
                                 infoList, isFolder=False, cm=contextMenu)
        return self.applyResume(ilist, contentId)

    @property
    def saved(self):
        """Content ids on the viewer's saved list.

        Read once per directory so each title can be offered the right
        action, rather than asking about every item or guessing. Signed out
        there is no list to read.
        """
        if self._saved is None:
            self._saved = set()
            if self.auth is not None and self.auth.signedIn:
                try:
                    self._saved = set(str(e['content_id']) for e in self.api.queue())
                except TubiApiError as err:
                    self.log(''.join(['could not read the saved list : ', str(err)]))
        return self._saved

    @property
    def watching(self):
        """What the account has part-watched, keyed by content id.

        Each value carries the position to resume from and, for a title
        Tubi tracks in its own right, the history entry id that removing it
        from Continue Watching needs. A series is tracked as itself with its
        episodes nested, so both are indexed.
        """
        if self._watching is None:
            entries = []
            if self.auth is not None and self.auth.signedIn:
                try:
                    entries = self.api.history()
                except TubiApiError as err:
                    self.log(''.join(['could not read the watch history : ', str(err)]))
            self._watching = self.watchMap(entries)
        return self._watching

    @staticmethod
    def watchMap(entries):
        """Index a watch history by content id, episodes included."""
        watching = {}
        for entry in entries:
            watching[str(entry.get('content_id'))] = {
                'history_id': entry.get('id'),
                'position': entry.get('position'),
                'length': entry.get('content_length')}
            for episode in entry.get('episodes') or []:
                watching[str(episode.get('content_id'))] = {
                    'history_id': None,
                    'position': episode.get('position'),
                    'length': episode.get('content_length')}
        return watching

    def applyResume(self, ilist, contentId):
        """Let Kodi offer to resume where Tubi says the viewer stopped.

        The ResumeTime and TotalTime properties are deprecated - they log a
        warning apiece on every list item that carries a resume point - so
        Kodi 20 and later get setResumePoint() instead. Kodi 19 has no such
        setter and keeps the properties.
        """
        entry = self.watching.get(str(contentId)) or {}
        position, length = entry.get('position'), entry.get('length')
        if not (ilist and position and length):
            return ilist
        liz = ilist[-1][1]
        if INFOTAG_SETTERS:
            liz.getVideoInfoTag().setResumePoint(float(position), float(length))
        else:
            liz.setProperty('ResumeTime', str(position))
            liz.setProperty('TotalTime', str(length))
        return ilist

    def extrasFor(self, contentId, content, inList=False):
        """The context menu entries every title carries."""
        kind = QUEUE_SERIES if content.get('type') == SERIES else HISTORY_MOVIE
        inList = inList or contentId in self.saved
        listing = ['queue', 'remove' if inList else 'add', contentId, kind]
        extras = [(self.localLang(30042 if inList else 30041),
                   'RunPlugin(%s?mode=DF&url=%s)' % (sys.argv[0], qp('|'.join(listing)))),
                  (self.localLang(30034),
                   'Container.Update(%s?mode=SE&url=%s)' % (sys.argv[0], qp('|'.join(['related', contentId]))))]
        if content.get('has_trailer') or content.get('trailers'):
            extras.append((self.localLang(30035),
                           'PlayMedia(%s?mode=GV&url=%s)' % (sys.argv[0], qp('|'.join(['trailer', contentId])))))
        historyId = (self.watching.get(contentId) or {}).get('history_id')
        if historyId:
            extras.append((self.localLang(30054),
                           'RunPlugin(%s?mode=DF&url=%s)' % (
                               sys.argv[0], qp('|'.join(['unwatch', historyId])))))
        series = '1' if content.get('type') == SERIES else '0'
        for label, action in ((30045, LIKE), (30046, DISLIKE)):
            extras.append((self.localLang(label),
                           'RunPlugin(%s?mode=DF&url=%s)' % (
                               sys.argv[0], qp('|'.join(['rate', action, contentId, series])))))
        return extras

    def getAddonMenu(self, url, ilist):
        try:
            containers = self.api.browseList()
        except TubiApiError as err:
            self.report(err)
            return ilist

        # Home is Tubi's own screen and carries its Continue Watching and My
        # List rows already, so neither gets a second entry here.
        infoList = {'Title': self.localLang(30036)}
        ilist = self.addMenuItem(self.localLang(30036), 'SE', ilist, 'home',
                                 self.addonIcon, self.addonFanart, infoList, isFolder=True)
        prototypeRow = next((row for row in containers
                             if row.get('id') == 'most_popular' or
                             row.get('slug') == 'most_popular'), None)
        if prototypeRow is not None:
            ilist = self.addMenuItem(self.localLang(30071) or 'Tubi Home', 'DF', ilist,
                                     'ui|' + json.dumps({
                                         'id': prototypeRow.get('id') or prototypeRow['slug'],
                                         'title': prototypeRow.get('title')}),
                                     self.addonIcon, self.addonFanart, isFolder=False)
            ilist[-1][1].setProperty('IsPlayable', 'false')
        for container in containers:
            infoList = {'Title': container.get('title'),
                        'Plot': container.get('description')}
            thumb = container.get('thumbnail') or self.addonIcon
            ilist = self.addMenuItem(container.get('title'), 'GS', ilist,
                                     container.get('id') or container.get('slug'),
                                     thumb, self.addonFanart, infoList, isFolder=True)
        infoList = {'Title': self.localLang(30031)}
        ilist = self.addMenuItem(self.localLang(30031), 'GC', ilist, 'live',
                                 self.addonIcon, self.addonFanart, infoList, isFolder=True)
        infoList = {'Title': self.localLang(30010)}
        # Never hand out an empty url - Kodi trims the '=' off an empty query
        # value and t1mlib's parameter parser cannot read the result back.
        ilist = self.addMenuItem(self.localLang(30010), 'GM', ilist, 'search',
                                 self.addonIcon, self.addonFanart, infoList, isFolder=True)
        return(ilist)

    def getAddonCats(self, url, ilist):
        """Tubi's linear channels, browsable without IPTV Manager."""
        try:
            lineUp, groups = self.api.liveChannels()
        except TubiApiError as err:
            self.report(err)
            return ilist
        for channel in lineUp:
            channelId = str(channel.get('id'))
            infoList = {'Title': channel.get('title'),
                        'Plot': channel.get('description'),
                        'genre': groups.get(channelId),
                        'mediatype': 'video'}
            images = channel.get('images') or {}
            img = self.firstOf(images, 'thumbnail', 'poster', 'landscape') or self.addonIcon
            fanart = self.firstOf(images, 'background', 'landscape') or self.addonFanart
            ilist = self.addMenuItem(channel.get('title'), 'LV', ilist, channelId, img, fanart,
                                     infoList, isFolder=False)
        return(ilist)

    def getAddonLiveVideo(self, url):
        """Resolve a linear channel by id - its manifest carries a token."""
        channelId = uqp(url)
        try:
            lineUp, _ = self.api.liveChannels()
        except TubiApiError as err:
            self.report(err)
            xbmcplugin.setResolvedUrl(int(sys.argv[1]), False, xbmcgui.ListItem(offscreen=True))
            return
        manifest = None
        for channel in lineUp:
            if str(channel.get('id')) == channelId:
                manifest, _ = pickResource(channel)
                break
        if manifest is None:
            xbmcgui.Dialog().notification(self.addonName, self.localLang(30028),
                                          xbmcgui.NOTIFICATION_WARNING)
            xbmcplugin.setResolvedUrl(int(sys.argv[1]), False, xbmcgui.ListItem(offscreen=True))
            return
        liz = xbmcgui.ListItem(path=self.mediaUrl(manifest), offscreen=True)
        liz.setMimeType('application/x-mpegURL')
        liz.setContentLookup(False)
        liz.setProperty('inputstream', 'inputstream.adaptive')
        for key, value in manifestProperties(manifest):
            liz.setProperty(key, value)
        xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, liz)

    def getAddonShows(self, url, ilist):
        containerId, cursor, contentMode = (url.split('|') + [None, None])[:3]
        try:
            contents, nextCursor = self.api.container(containerId, cursor=int(cursor or 0),
                                                      contentMode=contentMode)
        except TubiApiError as err:
            self.report(err)
            return ilist
        kinds = {content.get('type') for content in contents}
        if kinds:
            directoryContent = ('tvshows' if kinds == {SERIES} else
                                'movies' if SERIES not in kinds else 'videos')
            xbmcplugin.setContent(int(sys.argv[1]), directoryContent)
        for content in contents:
            ilist = self.addContent(content, ilist)
        if nextCursor is not None:
            infoList = {'Title': self.localLang(30026)}
            ilist = self.addMenuItem(self.localLang(30026), 'GS', ilist,
                                     '|'.join([containerId, str(nextCursor)] +
                                              ([contentMode] if contentMode else [])),
                                     self.addonIcon, self.addonFanart, infoList, isFolder=True)
        return(ilist)

    def getAddonSearch(self, url, ilist):
        """The listings that are not a plain category: home, list, related."""
        parts = url.split('|')
        inList = False
        try:
            if parts[0] == 'home':
                # home|movie and home|tv are Tubi's Movies and TV Shows pages
                return self.homeRows(ilist, parts[1] if len(parts) > 1 else None)
            if parts[0] == 'mylist':
                contents = self.api.contents([str(e['content_id']) for e in self.api.queue()])
                inList = True
            elif parts[0] == 'related' and len(parts) > 1:
                contents = self.api.related(parts[1])
            else:
                return ilist
        except TubiApiError as err:
            self.report(err)
            return ilist
        for content in contents:
            ilist = self.addContent(content, ilist, inList=inList)
        return(ilist)

    def homeRows(self, ilist, contentMode=None):
        """Tubi's own home screen, its rows as folders.

        With a contentMode each row keeps it, so the row lists only films or
        only series as on Tubi's own Movies and TV Shows pages.
        """
        for row in self.api.homescreenAll(contentMode):
            infoList = {'Title': row.get('title'),
                        'Plot': row.get('description')}
            thumb = row.get('thumbnail') or self.addonIcon
            rowId = row.get('id') or row.get('slug')
            ilist = self.addMenuItem(row.get('title'), 'GS', ilist,
                                     '|'.join([rowId, '0', contentMode]) if contentMode else rowId,
                                     thumb, self.addonFanart, infoList, isFolder=True)
        return(ilist)

    def getAddonMovies(self, url, ilist):
        query = xbmcgui.Dialog().input(self.localLang(30010))
        if len(query) == 0:
            # Cancelled: fail the listing so Kodi keeps the folder it came from.
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            sys.exit()
        try:
            contents = self.api.search(query)
        except TubiApiError as err:
            self.report(err)
            return ilist
        for content in contents:
            ilist = self.addContent(content, ilist)
        return(ilist)

    # -------------------------------------------------------------- series

    def seasonList(self, seriesId):
        """Seasons of a series, newest API shape, or None when it has none."""
        seasons = self.api.seasons(seriesId)
        return [s for s in seasons if s.get('episodes')]

    @staticmethod
    def showOf(pending):
        """The series payload fetched alongside its seasons, {} without one."""
        try:
            return pending.result() if pending is not None else {}
        except TubiApiError:
            return {}

    def episodeItems(self, seriesId, season, ilist, showTitle=None, show=None):
        try:
            episodes = self.api.episodes(seriesId, season.get('season'),
                                         expected=len(season.get('episodes') or []))
        except TubiApiError as err:
            self.report(err)
            return ilist
        series = self.showOf(show)
        if showTitle is None:
            showTitle = series.get('title') or xbmc.getInfoLabel('ListItem.TVShowTitle') or ''
        poster = self.firstOf(series, 'posterarts')
        for episode in episodes:
            infoList = self.infoOf(episode)
            title = episode.get('title') or ''
            # Titles arrive as "S01:E01 - Day One", the numbers are separate
            # fields so the prefix is only noise in the episode list.
            if ' - ' in title and title.startswith('S'):
                title = title.split(' - ', 1)[1]
            infoList['Title'] = title
            infoList['TVShowTitle'] = showTitle
            infoList['Season'] = season.get('season')
            infoList['Episode'] = episode.get('episode_number')
            infoList['mediatype'] = 'episode'
            img = self.firstOf(episode, 'thumbnails', 'posterarts') or self.addonIcon
            fanart = self.firstOf(episode, 'backgrounds', 'hero_images') or self.addonFanart
            # Episodes resolve back through their season rather than by id -
            # the season payload is where Tubi publishes their streams, and
            # the manifest urls themselves carry a token that expires.
            playUrl = '|'.join([str(episode.get('id')), str(seriesId), str(season.get('season'))])
            ilist = self.addMenuItem(title, 'GV', ilist, playUrl, img, fanart,
                                     infoList, isFolder=False)
            if poster:
                # The episode image is a landscape still; the poster is the show's.
                ilist[-1][1].setArt({'poster': self.mediaUrl(poster)})
            ilist = self.applyResume(ilist, episode.get('id'))
        return ilist

    def getAddonEpisodes(self, url, ilist):
        """A series' seasons, or one season's episodes for `seriesId|season`."""
        seriesId, season = (url.split('|', 1) + [None])[:2]
        # The show's title and artwork come from the series itself: the folder
        # is often opened without its list item in focus. Fetch it beside the
        # season index rather than after it.
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        show = pool.submit(self.api.content, seriesId)
        pool.shutdown(wait=False)
        try:
            seasons = self.seasonList(seriesId)
        except TubiApiError as err:
            self.report(err)
            return ilist

        if season is not None:
            wanted = [s for s in seasons if str(s.get('season')) == str(season)]
            if len(wanted) == 0:
                return ilist
            return self.episodeItems(seriesId, wanted[0], ilist, show=show)

        if len(seasons) == 1:
            return self.episodeItems(seriesId, seasons[0], ilist, show=show)

        xbmcplugin.setContent(int(sys.argv[1]), 'seasons')
        series = self.showOf(show)
        showTitle = (series.get('title') or
                     xbmc.getInfoLabel('ListItem.Title').replace(self.localLang(30019), ''))
        # Tubi has no season artwork; the show's own stands in for it.
        poster = self.firstOf(series, 'posterarts') or self.addonIcon
        fanart = self.firstOf(series, 'backgrounds', 'hero_images') or self.addonFanart
        for entry in seasons:
            name = entry.get('name') or ' '.join([self.localLang(30027), str(entry.get('season'))])
            infoList = {'Title': name,
                        'TVShowTitle': showTitle,
                        'Season': entry.get('season'),
                        'mediatype': 'season'}
            ilist = self.addMenuItem(name, 'GE', ilist,
                                     '|'.join([seriesId, str(entry.get('season'))]),
                                     poster, fanart, infoList, isFolder=True)
            ilist[-1][1].setProperty('TotalEpisodes', str(len(entry.get('episodes') or [])))
        return(ilist)

    def addShowToLibrary(self, url):
        """Export every episode of a series, across all of its seasons."""
        seriesId = uqp(url)
        try:
            content = self.api.content(seriesId)
            seasons = self.seasonList(seriesId)
        except TubiApiError as err:
            self.report(err)
            return
        ilist = []
        showTitle = content.get('title') or xbmc.getInfoLabel('ListItem.Title')
        for entry in seasons:
            ilist = self.episodeItems(seriesId, entry, ilist, showTitle=showTitle)
        movieDir = self.makeLibraryPath('shows', name=self.cleanFilename(showTitle))
        for itemUrl, liz, isFolder in ilist:
            tag = liz.getVideoInfoTag()
            name = ''.join(['S', str(tag.getSeason()), 'E', str(tag.getEpisode()), '  ',
                            self.cleanFilename(str(tag.getTitle())), '.strm'])
            with open(xbmcvfs.translatePath(os.path.join(movieDir, name)), 'w') as outfile:
                outfile.write(itemUrl)
        self.doScan(movieDir)

    # ------------------------------------------------------------ playback

    def doFunction(self, url):
        if url.startswith('ui|'):
            from resources.lib.home import showHome
            showHome(self, json.loads(url[3:]))
            return
        if url == 'logout' and self.auth is not None:
            self.auth.signOut()
            xbmcgui.Dialog().notification(self.addonName, self.localLang(30023))
            return
        parts = uqp(url).split('|')
        if parts[0] == 'queue' and len(parts) > 2:
            self.toggleQueue(parts[1], parts[2], parts[3] if len(parts) > 3 else HISTORY_MOVIE)
        elif parts[0] == 'rate' and len(parts) > 3:
            self.toggleRating(parts[1], parts[2], parts[3] == '1')
        elif parts[0] == 'unwatch' and len(parts) > 1:
            self.forget(parts[1])

    def forget(self, historyId):
        """Take a title out of Continue Watching."""
        try:
            self.api.removeFromHistory(historyId)
        except TubiApiError as err:
            self.report(err)
            return
        self._watching = None
        self.debug('forgot %s from continue watching' % historyId)
        xbmcgui.Dialog().notification(self.addonName, self.localLang(30055))
        xbmc.executebuiltin('Container.Refresh')

    def toggleQueue(self, action, contentId, kind):
        """Put a title on the saved list, or take it off.

        Removing needs the list entry's own id rather than the title's, so
        the list is looked up first either way - which also keeps a second
        Add from stacking a duplicate entry.
        """
        try:
            entry = self.api.queueEntry(contentId)
            if action == 'remove':
                if entry is not None:
                    self.api.removeFromQueue(entry['id'])
                message = 30044
            else:
                if entry is None:
                    self.api.addToQueue(contentId, kind)
                message = 30043
        except TubiApiError as err:
            self.report(err)
            return
        self._saved = None
        self.debug('%s my list : %s' % (action, contentId))
        xbmcgui.Dialog().notification(self.addonName, self.localLang(message))
        xbmc.executebuiltin('Container.Refresh')

    def toggleRating(self, wanted, contentId, isSeries):
        """Like or dislike a title, or take back the one already given."""
        try:
            current = self.api.rating(contentId, isSeries)
            if wanted == LIKE:
                action, message = (UNLIKE, 30049) if current == RATING_LIKED else (LIKE, 30047)
            else:
                action, message = (UNDISLIKE, 30049) if current == RATING_DISLIKED else (DISLIKE, 30048)
            self.api.rate(contentId, isSeries, action)
        except TubiApiError as err:
            self.report(err)
            return
        self.debug('%s : %s' % (action, contentId))
        xbmcgui.Dialog().notification(self.addonName, self.localLang(message))

    def resolve(self, url):
        """Look up a playable title.

        A film is fetched by its own id. An episode arrives as
        `episodeId|seriesId|season` and is picked out of its season, because
        that is where Tubi publishes episode streams. `trailer|id` asks for a
        title's trailer rather than the title itself.
        """
        parts = uqp(url).split('|')
        if parts[0] == 'trailer' and len(parts) > 1:
            trailers = self.api.content(parts[1]).get('trailers') or []
            # A trailer is a plain manifest, never encrypted
            return {'title': self.localLang(30035),
                    'video_resources': [],
                    'url': trailers[0].get('url') if trailers else None}
        if len(parts) < 3:
            return self.api.content(parts[0])
        episodeId, seriesId, season = parts[:3]
        for episode in self.api.episodes(seriesId, season):
            if str(episode.get('id')) == episodeId:
                return episode
        return {}

    def rememberPlaying(self, url, content):
        """Leave the service what it needs to report progress on stop.

        A film reports as itself. An episode reports as itself too, with its
        series named as the parent. Trailers report nothing.
        """
        window = xbmcgui.Window(10000)
        window.clearProperty(PLAYING)
        parts = uqp(url).split('|')
        if parts[0] == 'trailer' or self.addon.getSetting('report_progress') != 'true':
            return
        contentId = asInt(content.get('id'))
        if contentId is None:
            return
        playing = {'content_id': contentId,
                   'content_type': HISTORY_MOVIE,
                   'duration': content.get('duration')}
        if len(parts) >= 3:
            playing['content_type'] = HISTORY_EPISODE
            playing['parent_id'] = parts[1]
        window.setProperty(PLAYING, json.dumps(playing))

    def getAddonVideo(self, url):
        xbmcgui.Window(10000).clearProperty(PLAYBACK_DIAGNOSTIC)
        try:
            content = self.resolve(url)
        except TubiApiError as err:
            self.report(err)
            xbmcplugin.setResolvedUrl(int(sys.argv[1]), False, xbmcgui.ListItem(offscreen=True))
            return

        allowHdcp = self.addon.getSetting('allow_hdcp') == 'true'
        chosen = chooseResource(content, allowHdcp=allowHdcp)
        manifest, licenseUrl = pickResource(content, allowHdcp=allowHdcp)
        # Which rendition was taken is the whole of what allow_hdcp decides,
        # and nothing else in the log says. What was on offer matters too:
        # some titles' only unencrypted stream is an hlsv3, and whether Tubi
        # returns one is not something the payload announces anywhere else.
        self.debug('%s : offered %s, playing %s (allow_hdcp=%s)' % (
            content.get('title'), offeredTypes(content),
            describeResource(chosen), allowHdcp))
        self.diagnoseResources(content, chosen)
        if manifest is None:
            # Either the title needs an account or it is not playable here
            message = 30018 if content.get('needs_login') else 30028
            self.note('no playable stream for %s (needs_login=%s)' % (
                content.get('id'), content.get('needs_login')), level=xbmc.LOGWARNING)
            xbmcgui.Dialog().notification(self.addonName, self.localLang(message),
                                          xbmcgui.NOTIFICATION_WARNING)
            xbmcplugin.setResolvedUrl(int(sys.argv[1]), False, xbmcgui.ListItem(offscreen=True))
            return

        if licenseUrl is not None:
            compatible, reason = self.prepareWidevine()
            if not compatible:
                self.note('blocked unsafe Widevine start: %s' % reason,
                          level=xbmc.LOGWARNING)
                if 'DT_RELR' in reason:
                    message = 30067
                elif 'older than required' in reason:
                    message = 30070
                else:
                    message = 30069
                xbmcgui.Dialog().notification(self.addonName, self.localLang(message),
                                              xbmcgui.NOTIFICATION_ERROR, 10000)
                xbmcplugin.setResolvedUrl(int(sys.argv[1]), False,
                                          xbmcgui.ListItem(offscreen=True))
                return
            self.diagnoseManifest(manifest)

        self.rememberPlaying(url, content)
        xbmcgui.Window(10000).setProperty(PLAYBACK_DIAGNOSTIC, json.dumps({
            'content_id': content.get('id'),
            'stream': describeResource(chosen),
            'manifest_type': manifestKind(manifest),
            'drm': licenseUrl is not None,
        }))
        liz = xbmcgui.ListItem(path=self.mediaUrl(manifest), offscreen=True)
        liz.setSubtitles([self.mediaUrl(sub['url']) for sub in content.get('subtitles') or []
                          if sub.get('url')])
        # Use the adaptive reader for every HLS rendition, not only Widevine.
        # Kodi's generic FFmpeg reader probes an extensionless relay URL with
        # byte ranges and can exhaust its queues on multi-level Tubi HLS.
        liz.setMimeType(manifestMime(manifest))
        liz.setContentLookup(False)
        liz.setProperty('inputstream', 'inputstream.adaptive')
        manifestProps = manifestProperties(manifest)
        for key, value in manifestProps:
            liz.setProperty(key, value)
        if licenseUrl is not None:
            # Tubi encrypts some titles, which additionally need a working
            # Widevine CDM. The relay only transports the legitimate exchange.
            drmProps = self.drmProperties(self.mediaUrl(licenseUrl))
            for key, value in drmProps:
                liz.setProperty(key, value)
            self.diag('ISA properties inputstream=inputstream.adaptive mime=%s '
                      'manifest_properties=%s DRM=%s keysystem=%s license=%s '
                          'headers=Content-Type,Origin,Referer,User-Agent '
                          'challenge=raw response=raw' % (
                          manifestMime(manifest), [key for key, _ in manifestProps],
                          [key for key, _ in drmProps], WIDEVINE_KEYSYSTEM,
                          safeUrl(licenseUrl)))
        xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, liz)

    def drmProperties(self, licenseUrl):
        """Describe the Widevine licence request to inputstream.adaptive.

        Newer builds want drm_legacy and warn about the license_* properties;
        older ones only understand license_*, so pick by what is installed
        rather than dropping DRM playback on Kodi 19 and 20.
        """
        licenseHeaders = list(LICENSE_HEADERS)
        userAgent = self.defaultHeaders.get('User-Agent')
        if userAgent:
            licenseHeaders.append(('User-Agent', userAgent))
        if inputstreamMajor() >= DRM_PROPERTIES_SINCE:
            headers = urllib.parse.urlencode(licenseHeaders)
            return [('inputstream.adaptive.drm_legacy',
                     '|'.join([WIDEVINE_KEYSYSTEM, licenseUrl, headers]))]
        headers = urllib.parse.urlencode(licenseHeaders)
        # url | request headers | request data | response format
        return [('inputstream.adaptive.license_type', WIDEVINE_KEYSYSTEM),
                ('inputstream.adaptive.license_key',
                 '|'.join([licenseUrl, headers, 'R{SSM}', '']))]
