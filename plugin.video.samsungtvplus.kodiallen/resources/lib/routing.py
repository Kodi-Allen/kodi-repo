# -*- coding: utf-8 -*-
"""Add-on-local media-relay routing (shared with the Kodi Allen Joyn add-on).

Kodi's global network settings are intentionally not touched. In custom mode
every URL handed to Kodi is changed into a short-lived capability URL for the
configured relay, which fetches it, and everything the playlists name, from
its own network exit. Samsung TV Plus needs no proxy for the add-on's own
requests (the channel data is public), so only route_mode and relay_* apply.
"""

import base64
import hashlib
import hmac
import time
import urllib.parse


MODE_DIRECT = '0'
MODE_CUSTOM = '1'
DEFAULT_PROXY_PORT = 8883
DEFAULT_RELAY_PORT = 8893
DEFAULT_URL_TTL = 86400
BLOCKED_PROXY = 'http://127.0.0.1:1'
BLOCKED_MEDIA = 'http://127.0.0.1:1/geotv-routing-not-configured'


def _setting(addon, setting_id, default=''):
    try:
        value = addon.getSetting(setting_id)
        return value if value not in (None, '') else default
    except Exception:
        return default


def _port(value, default):
    try:
        port = int(value)
        return port if 1 <= port <= 65535 else default
    except (TypeError, ValueError):
        return default


def _host_for_url(host):
    host = str(host or '').strip()
    if ':' in host and not host.startswith('['):
        return '[%s]' % host
    return host


def _key(prefix, setting_id):
    return '%s.%s' % (prefix, setting_id) if prefix else setting_id


def custom_enabled(addon, prefix=''):
    return _setting(addon, _key(prefix, 'route_mode'), MODE_DIRECT) == MODE_CUSTOM


def addon_http_proxy(addon, prefix=''):
    """Configured HTTP CONNECT proxy URL, None in direct mode.

    A custom route with a missing host deliberately points at a closed local
    port. Misconfiguration must fail closed instead of leaking a request
    through the normal internet connection.
    """
    if not custom_enabled(addon, prefix):
        return None
    host = _host_for_url(_setting(addon, _key(prefix, 'proxy_host')))
    if not host:
        return BLOCKED_PROXY
    port = _port(_setting(addon, _key(prefix, 'proxy_port')), DEFAULT_PROXY_PORT)
    username = _setting(addon, _key(prefix, 'proxy_username'))
    password = _setting(addon, _key(prefix, 'proxy_password'))
    credentials = ''
    if username:
        credentials = urllib.parse.quote(str(username), safe='')
        if password:
            credentials += ':' + urllib.parse.quote(str(password), safe='')
        credentials += '@'
    return 'http://%s%s:%s' % (credentials, host, port)


def request_kwargs(addon, prefix=''):
    proxy = addon_http_proxy(addon, prefix)
    if proxy is None:
        return {}
    return {'proxies': {'http': proxy, 'https': proxy}}


class MediaRouter(object):
    """Wrap upstream URLs for the relay selected in the add-on settings."""

    def __init__(self, addon, now=None, prefix=''):
        self.addon = addon
        self.now = now
        self.prefix = prefix

    @property
    def enabled(self):
        return custom_enabled(self.addon, self.prefix)

    @property
    def base(self):
        host = _host_for_url(_setting(self.addon, _key(self.prefix, 'relay_host')))
        if not host:
            return None
        port = _port(_setting(self.addon, _key(self.prefix, 'relay_port')), DEFAULT_RELAY_PORT)
        return 'http://%s:%s' % (host, port)

    @property
    def key(self):
        return _setting(self.addon, _key(self.prefix, 'relay_signing_key')).encode('utf-8')

    def route(self, url):
        if not self.enabled or not isinstance(url, str):
            return url
        if not url.startswith(('http://', 'https://')):
            return url
        base = self.base
        key = self.key
        if base is None or len(key) < 32:
            return BLOCKED_MEDIA
        if url.startswith(base + '/v1/relay?'):
            return url

        encoded = base64.urlsafe_b64encode(url.encode('utf-8')).decode('ascii').rstrip('=')
        now = int(time.time() if self.now is None else self.now)
        expires = ((now // DEFAULT_URL_TTL) + 2) * DEFAULT_URL_TTL
        payload = '%s\n%s' % (expires, encoded)
        signature = hmac.new(key, payload.encode('ascii'), hashlib.sha256).hexdigest()
        return '%s/v1/relay?u=%s&exp=%s&sig=%s' % (
            base, urllib.parse.quote(encoded, safe=''), expires, signature)
