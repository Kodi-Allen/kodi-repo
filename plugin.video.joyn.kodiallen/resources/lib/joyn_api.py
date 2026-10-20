# -*- coding: utf-8 -*-
# Joyn content and playback API
#
# Joyn's web client talks to four hosts, shared by all three tenants:
#
#   auth.joyn.de           anonymous and account tokens
#   api.joyn.de/graphql    the catalogue, as persisted GraphQL queries
#   entitlements-service   a short-lived entitlement token per title/channel
#   api.vod-prd.s.joyn.de  the playlist: DASH manifest, licence and
#                          certificate URL for that entitlement
#
# The tenant is chosen by headers, not by host. Catalogue requests answer
# from anywhere; the entitlement service decides by the caller's address
# whether a title may play there (ENT_AssetNotAvailableInCountry,
# ENT_USER_VPN_DETECTED). Those decisions are Joyn's and are only reported.
#
# Query hashes, header names and the playlist signature follow what Joyn's
# own web client sends. They were cross-checked against the open Joyn Kodi
# projects plugin.video.joyn (Maven85) and script.service.ultimate
# (nirvana-7777) and verified live on 2026-10-20; no code was taken over.
import base64
import hashlib
import json
import os
import time
import urllib.parse
import uuid

import requests

from resources.lib import regions

AUTH_API = 'https://auth.joyn.de/auth'
SSO_ENDPOINTS = 'https://auth.joyn.de/sso/endpoints'
SEVENPASS = 'https://auth.7pass.de'
GRAPHQL_API = 'https://api.joyn.de/graphql'
ENTITLEMENT_API = 'https://entitlements-service-alb.prd.platform.s.joyn.de/api/user/entitlement-token'
PLAYBACK_API = 'https://api.vod-prd.s.joyn.de/v1'

# The web client's public gateway key and version, sent with every query.
API_KEY = '4f0fd9f18abbe3cf0e87fdb556bc39c8'
CLIENT_VERSION = '5.1592.3'
PLATFORM = 'web'
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36')

# Persisted queries: operation name and the sha256 the server knows it by.
QUERIES = {
    'navigation': ('Navigation', '818622ff5afe143664241034ba0c537650ec9a2eeae4d568830b47d8de605b7e'),
    'landing': ('LandingPageClient', '5838ac6b328cda91a70da264d5be09d4735cf95de8d9ee00cec60e77fcc3df08'),
    'blocks': ('LandingBlocks', '1655591f83b0dc1508ad4d52c5f37f72d410f48ad08c3e5f2de8622f86a21c68'),
    'series': ('SeriesDetailNewPageStatic', 'e867452d17ef36e5c077db5cdcad7563a9aebede497c24ac8fae779723bc462d'),
    'season': ('Season', 'ee2396bb1b7c9f800e5cefd0b341271b7213fceb4ebe18d5a30dab41d703009f'),
    'movie': ('PageMovieDetailStatic', '9ae6bcd8c45a5e350438d1cc415a022fe053e938c93438509f60ae3abb425fa7'),
    'asset': ('PlayableAssetWithToken', 'e2db6e6f9090f14848d3989920a1342f6813099c65ee7faef1e334f23e390970'),
    'search': ('SearchQ', 'bb2bab6cbe17321d7eddd5006e7f40765faedd79790b193a59d83f4640694856'),
    'live': ('LiveChannelsAndEpg', 'b7703103ddd0516be6b49ed66186092a6c6f6d815ccc502a9f50800a8cc18dd2'),
}

# The playlist request is signed: sha1 over "<body>,<entitlement token><secret>".
# The secret is the web client's, stored base64-encoded as there. The body
# must be sent byte for byte as signed, so it is built once, here.
SIGNATURE_SECRET = base64.b64decode(
    'MzU0MzM3MzgzMzM4MzMzNjM1NDMzNzM4MzYzNDM2MzYzNTQzMzczODM2MzYzMzM4MzIzNjM1NDMz'
    'NzM4MzMzMDM2MzQzNTM5MzU0MzM3MzgzMzM5MzMzNTMyMzQzNTQzMzczODM2MzUzMzM5MzU0MzM3'
    'MzgzMzM4MzMzMjMzNDYzNTQzMzczODM2MzYzMzMzMzM0NDMzNDIzNTQzMzczODMzMzgzNjM2MzMzNQ==').decode('ascii')
PLAYLIST_BODY = json.dumps({
    'manufacturer': 'unknown', 'platform': 'browser', 'maxSecurityLevel': 1,
    'model': 'unknown', 'protectionSystem': 'widevine', 'streamingFormat': 'dash',
    'enableSubtitles': True, 'maxResolution': 1080, 'version': 'v1'}).replace(' ', '')

LIVE, VOD = 'LIVE', 'VOD'
SEASON_PAGE = 32          # the most Season returns per request
TIMEOUT = 20
# Anonymous tokens last 24 h; renew a little before that.
TOKEN_MARGIN = 600

# Entitlement codes worth telling the viewer about, by string id.
MESSAGES = {
    'ENT_AssetNotAvailableInCountry': 30301,
    'ENT_Geoblocked': 30301,
    'ENT_USER_VPN_DETECTED': 30302,
    'ENT_BUSINESS_MODEL_NOT_SUITABLE': 30303,
    'ENT_AgeVerificationSetupRequired': 30304,
    'ENT_PINRequired': 30304,
    'ENT_RVOD_Playback_Restricted': 30305,
}


class JoynError(Exception):
    """A failed Joyn request. `code` is Joyn's own error code when it sent one."""

    def __init__(self, message, code=None, status=None):
        Exception.__init__(self, message)
        self.code = code
        self.status = status


def _errorCode(response):
    """Joyn's error code from an error body: a list or an object of {code, msg}."""
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        body = body.get('errors') or [body]
    if isinstance(body, list) and body and isinstance(body[0], dict):
        return body[0].get('code') or body[0].get('error')
    return None


class Session(object):
    """One region's token, kept in that region's own folder.

    Only the token lives here. A fresh device id is made once per region and
    kept with it, so Joyn sees one stable device per region.
    """

    def __init__(self, profile, region):
        self.path = regions.folder(profile, region, 'session.json')
        self.data = {}
        try:
            with open(self.path, 'r') as handle:
                data = json.load(handle)
            self.data = data if isinstance(data, dict) else {}
        except (IOError, OSError, ValueError):
            self.data = {}
        if not self.data.get('device_id'):
            self.data['device_id'] = str(uuid.uuid4())

    @property
    def deviceId(self):
        return self.data['device_id']

    def valid(self, now=None):
        now = time.time() if now is None else now
        return bool(self.data.get('access_token')) and self.data.get('expires', 0) - TOKEN_MARGIN > now

    def store(self, token, now=None):
        now = time.time() if now is None else now
        self.data.update({'access_token': token.get('access_token'),
                          'refresh_token': token.get('refresh_token'),
                          'expires': int(now + int(token.get('expires_in') or 0))})
        self.save()

    def clear(self):
        """Forget the token, keep the device id."""
        self.data = {'device_id': self.deviceId}
        self.save()

    def save(self):
        temporary = self.path + '.tmp'
        with open(temporary, 'w') as handle:
            json.dump(self.data, handle)
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)


class JoynApi(object):
    """The calls the add-on makes, for one region.

    `requestKwargs` carries the region's proxy (routing.request_kwargs) and
    is applied to every request, including sign-in and playback; a custom
    route therefore never falls back to the normal connection.
    """

    def __init__(self, region, profile, requestKwargs=None, log=None):
        self.region = region
        self.tenant = regions.REGIONS[region]['tenant']
        self.site = regions.REGIONS[region]['site']
        self.session = Session(profile, region)
        self.kwargs = dict(requestKwargs or {})
        self.log = log or (lambda message: None)
        self.http = requests.Session()
        # Never pick up a proxy from the environment: the route is explicit.
        self.http.trust_env = False

    # ---------------------------------------------------------- plumbing

    def _request(self, method, url, **kwargs):
        kwargs.setdefault('timeout', TIMEOUT)
        kwargs.update(self.kwargs)
        try:
            return self.http.request(method, url, **kwargs)
        except requests.RequestException as err:
            raise JoynError('%s: %s' % (type(err).__name__, err))

    def _joynHeaders(self):
        return {'User-Agent': USER_AGENT, 'Accept': 'application/json',
                'Origin': self.site, 'Referer': self.site + '/',
                'joyn-platform': PLATFORM, 'joyn-country': self.region.upper(),
                'joyn-distribution-tenant': self.tenant,
                'joyn-client-version': CLIENT_VERSION}

    def token(self, renew=False):
        """A bearer token for this region: the account's when signed in, else anonymous."""
        if not renew and self.session.valid():
            return self.session.data['access_token']
        if self.session.data.get('account'):
            return self.refresh()
        deviceId = self.session.deviceId
        response = self._request('POST', AUTH_API + '/anonymous', headers=self._joynHeaders(),
                                 json={'client_id': deviceId, 'client_name': PLATFORM,
                                       'anon_device_id': deviceId})
        if response.status_code != 200:
            raise JoynError('sign-in failed', _errorCode(response), response.status_code)
        token = response.json()
        if not token.get('access_token'):
            raise JoynError('sign-in returned no token')
        self.session.store(token)
        self.log('new anonymous session for %s' % self.region)
        return token['access_token']

    # ----------------------------------------------------------- account

    def login(self, email, password):
        """Sign in through Joyn's own 7pass web login and keep only the tokens.

        The same steps the joyn.at/.de/.ch website takes: Joyn names the
        login page and its client, 7pass takes the e-mail and password and
        answers with an authorization code, Joyn exchanges the code for its
        own tokens. The password is used for this one exchange and never
        stored or logged.
        """
        browser = {'User-Agent': USER_AGENT, 'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8'}
        response = self._request('GET', SSO_ENDPOINTS, headers=self._joynHeaders(),
                                 params={'client_id': self.session.deviceId, 'client_name': PLATFORM})
        if response.status_code != 200:
            raise JoynError('sign-in unavailable', _errorCode(response), response.status_code)
        endpoints = response.json()
        webLogin = endpoints.get('web-login') or ''
        login = urllib.parse.parse_qs(urllib.parse.urlsplit(webLogin).query)
        clientId = (login.get('client_id') or [''])[0]
        redirect = (login.get('redirect_uri') or [self.site + '/oauth'])[0]
        page = self._request('GET', webLogin, headers=browser)
        requestId = (urllib.parse.parse_qs(urllib.parse.urlsplit(page.url).query).get('requestId') or [''])[0]
        if not clientId or not requestId:
            raise JoynError('sign-in page changed', status=page.status_code)
        # The website asks these before the password; 7pass expects the order.
        self._request('GET', SEVENPASS + '/registration-setup-srv/public/list', headers=browser,
                      params={'acceptlanguage': 'undefined', 'requestId': requestId})
        self._request('POST', '%s/users-srv/user/checkexists/%s' % (SEVENPASS, requestId), headers=browser,
                      json={'email': email, 'requestId': requestId})
        self._request('POST', SEVENPASS + '/verification-srv/v2/setup/public/configured/list', headers=browser,
                      json={'email': email, 'request_id': requestId})
        answer = self._request('POST', SEVENPASS + '/login-srv/login', headers=browser,
                               data={'username': email, 'password': password, 'requestId': requestId})
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(answer.url).query)
        if '/mfa' in answer.url:
            raise JoynError('two-factor sign-in is not supported', 'MFA_REQUIRED')
        if '/register/additional' in answer.url:
            # The account lacks details or consents this region's tenant
            # requires; only the account holder can give those, on the website.
            raise JoynError('account needs completing on the website', 'ACCOUNT_INCOMPLETE')
        if not params.get('code') and params.get('sub') and params.get('track_id'):
            # First sign-in from this client: the consent the website shows.
            self._request('POST', SEVENPASS + '/consent-management-srv/consent/scope/accept', headers=browser,
                          json={'sub': params['sub'][0], 'client_id': clientId,
                                'scopes': [{'offline_access': 'denied'}]})
            answer = self._request('POST', '%s/login-srv/precheck/continue/%s' % (SEVENPASS, params['track_id'][0]),
                                   headers=browser, data=b'')
            params = urllib.parse.parse_qs(urllib.parse.urlsplit(answer.url).query)
        if not params.get('code'):
            raise JoynError('e-mail or password not accepted', 'LOGIN_REJECTED')
        response = self._request('POST', endpoints.get('redeem-token') or AUTH_API + '/7pass/token',
                                 headers=self._joynHeaders(),
                                 json={'client_id': clientId, 'code': params['code'][0], 'code_verifier': '',
                                       'redirect_uri': redirect,
                                       'tracking_id': (params.get('cd1') or [self.session.deviceId])[0],
                                       'tracking_name': PLATFORM})
        token = response.json() if 200 <= response.status_code < 300 else {}
        if not token.get('access_token'):
            raise JoynError('sign-in not completed', _errorCode(response), response.status_code)
        self.session.data['account'] = email
        self.session.store(token)
        self.log('signed in for %s' % self.region)
        return email

    def refresh(self):
        """Renew the account's token; a refused refresh ends the sign-in."""
        response = self._request('POST', AUTH_API + '/refresh', headers=self._joynHeaders(),
                                 json={'refresh_token': self.session.data.get('refresh_token'),
                                       'client_id': self.session.deviceId, 'client_name': PLATFORM})
        token = response.json() if 200 <= response.status_code < 300 else {}
        if not token.get('access_token'):
            self.session.clear()
            raise JoynError('sign-in expired', 'SIGNED_OUT', response.status_code)
        token.setdefault('refresh_token', self.session.data.get('refresh_token'))
        self.session.store(token)
        return token['access_token']

    def logout(self):
        """Forget the account's tokens; the region continues anonymously."""
        if self.session.data.get('account') and self.session.data.get('access_token'):
            try:
                self._request('POST', AUTH_API + '/logout', headers=dict(
                    self._joynHeaders(), Authorization='Bearer ' + self.session.data['access_token']), json={})
            except JoynError:
                pass
        self.session.clear()

    @property
    def account(self):
        return self.session.data.get('account')

    def query(self, name, variables=None, retry=True):
        """Run a persisted query and return its data object."""
        operation, digest = QUERIES[name]
        params = {'operationName': operation,
                  'enable_user_location': 'true',
                  'watch_assistant_variant': 'true',
                  'variables': json.dumps(variables or {}, separators=(',', ':')),
                  'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': digest}},
                                           separators=(',', ':'))}
        headers = self._joynHeaders()
        headers.update({'x-api-key': API_KEY, 'joyn-user-state': 'code=A_A',
                        'Authorization': 'Bearer ' + self.token()})
        response = self._request('GET', GRAPHQL_API, params=params, headers=headers)
        if response.status_code == 401 and retry:
            self.token(renew=True)
            return self.query(name, variables, retry=False)
        if response.status_code != 200:
            raise JoynError('%s failed' % operation, _errorCode(response), response.status_code)
        try:
            body = response.json()
        except ValueError:
            raise JoynError('%s returned no JSON' % operation)
        errors = body.get('errors') or []
        if not body.get('data'):
            code = ((errors[0].get('extensions') or {}).get('code') if errors else None)
            raise JoynError('%s returned no data' % operation, code)
        return body['data']

    # --------------------------------------------------------- catalogue

    def navigation(self):
        return self.query('navigation').get('navigation') or []

    def page(self, path):
        """A landing page's blocks: its first blocks in full, then the lazy rest.

        Lazy blocks arrive without assets; they are fetched in one more call.
        A page with no lazy blocks costs a single request.
        """
        page = self.query('landing', {'path': path}).get('page') or {}
        blocks = list(page.get('blocks') or [])
        lazy = [block.get('id') for block in page.get('lazyBlocks') or [] if block.get('id')]
        if lazy:
            loaded = dict((block.get('id'), block) for block in
                          self.query('blocks', {'ids': lazy}).get('blocks') or [])
            blocks.extend(loaded[blockId] for blockId in lazy if blockId in loaded)
        return blocks

    def series(self, path):
        """The series page: the series itself, with every season it lists."""
        return (self.query('series', {'path': path, 'licenseFilter': 'ALL'}).get('page') or {}).get('series') or {}

    def episodes(self, seasonId):
        """All episodes of a season, page by page."""
        episodes, offset = [], 0
        while True:
            season = self.query('season', {'id': seasonId, 'first': SEASON_PAGE, 'offset': offset,
                                           'licenseFilter': 'ALL'}).get('season') or {}
            batch = season.get('episodes') or []
            episodes.extend(batch)
            offset += len(batch)
            if len(batch) < SEASON_PAGE or offset >= (season.get('numberOfEpisodes') or 0):
                return episodes

    def asset(self, assetId):
        """A film or episode by its id, with the video id playback needs."""
        return self.query('asset', {'id': assetId}).get('asset') or {}

    def search(self, text, first=60):
        return (self.query('search', {'text': text, 'first': first, 'offset': 0}).get('search') or {}).get('results') or []

    def live(self, hours=12, now=None):
        """Every live stream with its programmes from an hour ago on.

        Joyn answers with about ten hours of guide however far ahead it is
        asked; a wider window costs nothing.
        """
        now = int(time.time() if now is None else now)
        return self.query('live', {'liveStreamGroupFilter': 'DEFAULT', 'first': 5000, 'offset': 0,
                                   'livestreamTypes': ['EVENT', 'LINEAR', 'ON_DEMAND'],
                                   'from': now - 3600, 'to': now + hours * 3600}).get('liveStreams') or []

    # ---------------------------------------------------------- playback

    def entitlement(self, contentId, kind):
        response = self._request('POST', ENTITLEMENT_API,
                                 json={'content_id': contentId, 'content_type': kind},
                                 headers={'Authorization': 'Bearer ' + self.token(),
                                          'Content-Type': 'application/json',
                                          'Accept': 'application/json',
                                          'User-Agent': 'Mozilla/5.0'})
        if response.status_code == 401:
            self.token(renew=True)
            return self.entitlement(contentId, kind)
        if response.status_code != 200:
            raise JoynError('no entitlement', _errorCode(response), response.status_code)
        token = response.json().get('entitlement_token')
        if not token:
            raise JoynError('entitlement without a token')
        return token

    def playlist(self, contentId, kind):
        """{'manifestUrl', 'licenseUrl', 'certificateUrl', ...} for a video or channel."""
        entitlement = self.entitlement(contentId, kind)
        signature = hashlib.sha1(('%s,%s%s' % (PLAYLIST_BODY, entitlement, SIGNATURE_SECRET))
                                 .encode('utf-8')).hexdigest()
        url = '%s/%s/%s/playlist' % (PLAYBACK_API, 'channel' if kind == LIVE else 'asset', contentId)
        response = self._request('POST', url, params={'signature': signature}, data=PLAYLIST_BODY,
                                 headers={'Authorization': 'Bearer ' + entitlement,
                                          'Content-Type': 'application/json',
                                          'User-Agent': USER_AGENT})
        if response.status_code != 200:
            raise JoynError('no playlist', _errorCode(response), response.status_code)
        playlist = response.json()
        if not playlist.get('manifestUrl'):
            raise JoynError('playlist without a manifest')
        return playlist
