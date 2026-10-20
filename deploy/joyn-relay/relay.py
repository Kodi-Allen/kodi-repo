#!/usr/bin/env python3
"""Capability-URL relay for Joyn: DASH manifests, segments, subtitles and licences.

Derived from the GeoTV Tubi relay (1.1.2); the signed /v1/relay URLs, the SSRF
checks, the HLS rewriting and the licence pass-through are unchanged. Added
for Joyn:

* Joyn's MPDs carry no BaseURL; their SegmentTemplates name segments relative
  to the manifest. The relay inserts one signed *prefix* capability as the
  MPD's BaseURL (/v1/base/<exp>/<sig>/<prefix>/...), so every relative
  segment, init and subtitle request still comes back through the relay.
* Upstream hosts are limited to an allowlist (RELAY_ALLOWED_HOSTS), also
  after redirects.

The licence request and response pass through byte for byte; the relay never
reads keys, never decrypts and never changes the DRM exchange.
"""

import asyncio
import base64
import hashlib
import hmac
import html
import ipaddress
import logging
import os
import re
import socket
import time
from urllib.parse import quote, unquote, urljoin, urlsplit

from aiohttp import ClientConnectionError, ClientSession, ClientTimeout, TCPConnector, web


LISTEN_HOST = os.environ.get('RELAY_LISTEN_HOST', '0.0.0.0')
LISTEN_PORT = int(os.environ.get('RELAY_LISTEN_PORT', '8893'))
PUBLIC_BASE = os.environ.get('RELAY_PUBLIC_BASE', '').rstrip('/')
SIGNING_KEY = os.environ.get('RELAY_SIGNING_KEY', '').encode('utf-8')
URL_TTL = int(os.environ.get('RELAY_URL_TTL', '86400'))
# Host suffixes the relay may fetch from; empty means no restriction.
ALLOWED_HOSTS = tuple(host.strip().lower().lstrip('.') for host in os.environ.get(
    'RELAY_ALLOWED_HOSTS', 'joyn.de,joyn.at,joyn.ch,p7s1video.net,p7s1.io').split(',') if host.strip())
LICENSE_HOSTS = ('api.vod-prd.s.joyn.de',)
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_REDIRECTS = 5

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
REQUEST_HEADERS = {
    'accept', 'accept-language', 'content-type', 'if-modified-since',
    'if-none-match', 'if-range', 'origin', 'range', 'referer', 'user-agent',
}
RESPONSE_HEADERS = {
    'accept-ranges', 'cache-control', 'content-disposition', 'content-length',
    'content-range', 'content-type', 'etag', 'expires', 'last-modified',
}
QUOTED_URI = re.compile(r'(\bURI\s*=\s*)(["\'])(.*?)\2', re.IGNORECASE)
UNQUOTED_URI = re.compile(r'(\bURI\s*=\s*)(?!["\'])([^,\s]+)', re.IGNORECASE)
BASE_URL = re.compile(
    r'(<(?:[\w.-]+:)?BaseURL\b[^>]*>)(.*?)(</(?:[\w.-]+:)?BaseURL\s*>)',
    re.IGNORECASE | re.DOTALL)

logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'),
                    format='%(asctime)s %(levelname)s %(message)s')
LOG = logging.getLogger('joyn-relay')


def _b64encode(value):
    return base64.urlsafe_b64encode(value.encode('utf-8')).decode('ascii').rstrip('=')


def _b64decode(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4)).decode('utf-8')


def _signature(encoded_url, expires):
    payload = '%s\n%s' % (expires, encoded_url)
    return hmac.new(SIGNING_KEY, payload.encode('ascii'), hashlib.sha256).hexdigest()


def signed_url(target, now=None):
    """Return a stable-for-one-window capability URL for an upstream URL."""
    now = int(time.time() if now is None else now)
    expires = ((now // URL_TTL) + 2) * URL_TTL
    encoded = _b64encode(target)
    return '%s/v1/relay?u=%s&exp=%s&sig=%s' % (
        PUBLIC_BASE, quote(encoded), expires, _signature(encoded, expires))


def prefix_url(prefix, now=None):
    """A capability for every URL below one directory, e.g. a manifest's folder."""
    now = int(time.time() if now is None else now)
    expires = ((now // URL_TTL) + 2) * URL_TTL
    encoded = _b64encode(prefix)
    return '%s/v1/base/%s/%s/%s/' % (PUBLIC_BASE, expires, _signature('P:' + encoded, expires), encoded)


def target_from_prefix(request):
    expires = request.match_info['exp']
    supplied = request.match_info['sig']
    encoded = request.match_info['prefix']
    tail = request.match_info['tail']
    if int(expires) < int(time.time()):
        raise web.HTTPUnauthorized(text='expired relay capability')
    if not hmac.compare_digest(_signature('P:' + encoded, expires), supplied):
        raise web.HTTPUnauthorized(text='invalid relay capability')
    # Only plain relative paths below the prefix; nothing that climbs out of it.
    if '..' in tail.split('/') or tail.startswith('/') or '//' in tail or '\\' in tail:
        raise web.HTTPBadRequest(text='invalid relative path')
    try:
        target = _b64decode(encoded) + tail
    except Exception as err:
        raise web.HTTPBadRequest(text='invalid relay URL') from err
    return target + ('?' + request.query_string if request.query_string else '')


def target_from_request(request):
    encoded = request.query.get('u', '')
    expires = request.query.get('exp', '')
    supplied = request.query.get('sig', '')
    if not encoded or not expires.isdigit() or not supplied:
        raise web.HTTPUnauthorized(text='missing relay capability')
    if int(expires) < int(time.time()):
        raise web.HTTPUnauthorized(text='expired relay capability')
    expected = _signature(encoded, expires)
    if not hmac.compare_digest(expected, supplied):
        raise web.HTTPUnauthorized(text='invalid relay capability')
    try:
        return _b64decode(unquote(encoded))
    except Exception as err:
        raise web.HTTPBadRequest(text='invalid relay URL') from err


async def validate_public_url(url):
    """Reject local/private targets even if a signing key is disclosed."""
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise web.HTTPBadRequest(text='only public HTTP(S) targets are allowed')
    if parsed.username is not None or parsed.password is not None:
        raise web.HTTPBadRequest(text='upstream credentials are not allowed')
    host = parsed.hostname.lower()
    if ALLOWED_HOSTS and not any(host == allowed or host.endswith('.' + allowed) for allowed in ALLOWED_HOSTS):
        raise web.HTTPForbidden(text='upstream host is not allowed')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    if port not in (80, 443):
        raise web.HTTPBadRequest(text='non-standard upstream ports are not allowed')
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as err:
        raise web.HTTPBadGateway(text='upstream name could not be resolved') from err
    if not addresses:
        raise web.HTTPBadGateway(text='upstream name has no address')
    for address in addresses:
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise web.HTTPForbidden(text='private upstream addresses are blocked')


def rewrite_playlist(body, source_url):
    text = body.decode('utf-8-sig')

    def wrapped(value):
        if not value or value.startswith(('data:', 'skd:')):
            return value
        return signed_url(urljoin(source_url, value))

    lines = []
    for line in text.splitlines():
        if line and not line.startswith('#'):
            line = wrapped(line.strip())
        elif 'URI' in line.upper():
            line = QUOTED_URI.sub(
                lambda match: '%s%s%s%s' % (
                    match.group(1), match.group(2), wrapped(match.group(3)), match.group(2)),
                line)
            line = UNQUOTED_URI.sub(
                lambda match: '%s%s' % (match.group(1), wrapped(match.group(2))), line)
        lines.append(line)
    return ('\n'.join(lines) + '\n').encode('utf-8')


MPD_OPEN = re.compile(r'(<(?:[\w.-]+:)?MPD\b[^>]*>)', re.IGNORECASE)


def rewrite_dash_manifest(body, source_url):
    """Route every file a DASH manifest names through the relay.

    A BaseURL naming a file becomes a signed URL; one naming a directory
    becomes a signed prefix, so SegmentTemplate paths below it still resolve
    to the relay. An MPD without any BaseURL - Joyn's live and on-demand
    manifests - gets one: the manifest's own directory as a signed prefix.
    Timing, ContentProtection and PSSH data are left exactly as they are.
    """
    text = body.decode('utf-8-sig')

    def routed(value):
        absolute = urljoin(source_url, value)
        return prefix_url(absolute) if absolute.endswith('/') else signed_url(absolute)

    def wrapped(match):
        value = html.unescape(match.group(2).strip())
        if not value:
            return match.group(0)
        return '%s%s%s' % (match.group(1), html.escape(routed(value), quote=False), match.group(3))

    if BASE_URL.search(text):
        return BASE_URL.sub(wrapped, text).encode('utf-8')
    base = html.escape(prefix_url(urljoin(source_url, '.')), quote=False)
    return MPD_OPEN.sub(lambda match: '%s<BaseURL>%s</BaseURL>' % (match.group(1), base),
                        text, count=1).encode('utf-8')


def manifest_kind(content_type, final_url, prefix=b''):
    media_type = (content_type or '').split(';', 1)[0].lower()
    path = urlsplit(final_url).path.lower()
    if (media_type in ('application/dash+xml', 'video/vnd.mpeg.dash.mpd')
            or path.endswith('.mpd')
            or re.match(br'\s*(?:<\?xml[^>]*>\s*)?<MPD\b', prefix,
                        re.IGNORECASE)):
        return 'dash'
    if (media_type in ('application/vnd.apple.mpegurl',
                       'application/x-mpegurl',
                       'audio/mpegurl',
                       'audio/x-mpegurl')
            or path.endswith(('.m3u8', '.m3u'))
            or prefix.startswith(b'#EXTM3U')):
        return 'hls'
    return None


def manifest_url(url):
    """Whether a URL itself identifies an HLS playlist."""
    return urlsplit(url).path.lower().endswith(('.m3u8', '.m3u', '.mpd'))


def forwarded_request_headers(request, target):
    manifest = manifest_url(target)
    headers = {name: value for name, value in request.headers.items()
               if name.lower() in REQUEST_HEADERS
               and not (manifest and name.lower() in ('range', 'if-range'))}
    # Kodi's generic HTTP reader probes unknown URLs with byte ranges. A
    # playlist changes length when its child URLs are replaced by signed relay
    # URLs, so forwarding that range would produce a 206 whose Content-Range
    # describes the old body. Always obtain the complete manifest instead.
    headers.setdefault('User-Agent', 'Mozilla/5.0 (Kodi Joyn Relay)')
    return headers


def copied_response_headers(upstream):
    headers = {name: value for name, value in upstream.headers.items()
               if name.lower() in RESPONSE_HEADERS}
    # ClientSession transparently decompresses. The upstream Content-Length
    # then describes the compressed representation, not what is streamed.
    if upstream.headers.get('Content-Encoding'):
        headers.pop('Content-Length', None)
    return headers


def rewritten_manifest_headers(upstream, kind='hls'):
    """Headers for a newly generated playlist body.

    Validators and ranges apply to the upstream bytes. They are invalid after
    URLs have been expanded, while web.Response will calculate the new length.
    """
    headers = copied_response_headers(upstream)
    invalid = {'accept-ranges', 'content-length', 'content-range', 'etag'}
    for name in list(headers):
        if name.lower() in invalid:
            headers.pop(name, None)
    headers['Content-Type'] = ('application/dash+xml' if kind == 'dash'
                               else 'application/vnd.apple.mpegurl')
    return headers


async def upstream_request(session, method, target, headers, body):
    current = target
    current_method = method
    current_body = body
    for _ in range(MAX_REDIRECTS + 1):
        await validate_public_url(current)
        response = await session.request(current_method, current, headers=headers,
                                         data=current_body, allow_redirects=False)
        if response.status not in REDIRECT_STATUSES or 'Location' not in response.headers:
            return response, current
        next_url = urljoin(current, response.headers['Location'])
        response.release()
        if response.status == 303 or (response.status in (301, 302) and current_method == 'POST'):
            current_method, current_body = 'GET', None
        current = next_url
    raise web.HTTPBadGateway(text='too many upstream redirects')


async def relay(request):
    return await proxy(request, target_from_request(request))


async def base(request):
    return await proxy(request, target_from_prefix(request))


async def proxy(request, target):
    body = await request.read()
    if len(body) > MAX_REQUEST_BYTES:
        raise web.HTTPRequestEntityTooLarge(max_size=MAX_REQUEST_BYTES,
                                            actual_size=len(body))
    method = request.method
    if method not in ('GET', 'HEAD', 'POST'):
        raise web.HTTPMethodNotAllowed(method, ('GET', 'HEAD', 'POST'))

    session = request.app['session']
    request_headers = forwarded_request_headers(request, target)
    target_host = urlsplit(target).hostname
    is_license = method == 'POST' and target_host in LICENSE_HOSTS
    if is_license:
        # Never log the target query, challenge or response. These fields are
        # sufficient to diagnose headers being lost between ISA and Joyn.
        LOG.info('Widevine POST request bytes=%s content-type=%s origin=%s '
                 'referer=%s user-agent=%s header-names=%s',
                 len(body), request_headers.get('Content-Type', 'missing'),
                 request_headers.get('Origin', 'missing'),
                 request_headers.get('Referer', 'missing'),
                 request_headers.get('User-Agent', 'missing'),
                 ','.join(sorted(name.lower() for name in request_headers)))
    upstream, final_url = await upstream_request(
        session, method, target, request_headers, body or None)
    try:
        if is_license:
            LOG.info('Widevine POST response status=%s reason=%s content-type=%s '
                     'www-authenticate=%s content-length=%s',
                     upstream.status, upstream.reason,
                     upstream.headers.get('Content-Type', 'missing'),
                     upstream.headers.get('WWW-Authenticate', 'missing'),
                     upstream.headers.get('Content-Length', 'missing'))
            if upstream.status >= 400:
                data = await upstream.content.read(4097)
                preview = data[:4096].decode('utf-8', 'replace')
                preview = re.sub(r'[A-Za-z0-9_+/=-]{24,}', 'MASKED', preview)
                LOG.info('Widevine error response body=%r truncated=%s',
                         preview, len(data) > 4096)
                return web.Response(status=upstream.status,
                                    headers=copied_response_headers(upstream),
                                    body=data)
        content_type = upstream.headers.get('Content-Type', '')
        path_kind = manifest_kind('', final_url)
        type_kind = manifest_kind(content_type, '')
        # Cover extensionless manifests too. If their first request was a
        # partial probe, repeat it without Range before attempting a rewrite.
        if (method == 'GET' and upstream.status == 206 and type_kind
                and any(name.lower() == 'range' for name in request_headers)):
            upstream.release()
            request_headers = {name: value for name, value in request_headers.items()
                               if name.lower() not in ('range', 'if-range')}
            upstream, final_url = await upstream_request(
                session, method, target, request_headers, body or None)
            content_type = upstream.headers.get('Content-Type', '')
            path_kind = manifest_kind('', final_url)
            type_kind = manifest_kind(content_type, '')
        kind = path_kind or type_kind
        if method == 'HEAD' and kind:
            # The GET body will grow when child URLs are signed. Do not expose
            # upstream range/length validators that describe the old body.
            response = web.StreamResponse(
                status=200 if 200 <= upstream.status < 300 else upstream.status,
                headers=rewritten_manifest_headers(upstream, kind))
            await response.prepare(request)
            await response.write_eof()
            LOG.info('HEAD %s -> %s (HLS headers normalized)',
                     urlsplit(final_url).hostname, response.status)
            return response
        if method != 'HEAD' and kind:
            # StreamReader.read(n) returns only what is already buffered, so a
            # manifest arriving in several packets used to be cut short. Read
            # to the end, still bounded.
            buf = bytearray()
            async for chunk in upstream.content.iter_chunked(64 * 1024):
                buf.extend(chunk)
                if len(buf) > MAX_MANIFEST_BYTES:
                    raise web.HTTPBadGateway(text='upstream manifest is too large')
            data = bytes(buf)
            kind = manifest_kind(content_type, final_url, data[:256])
            if kind:
                rewritten = (rewrite_dash_manifest(data, final_url)
                             if kind == 'dash'
                             else rewrite_playlist(data, final_url))
                headers = rewritten_manifest_headers(upstream, kind)
                status = 200 if 200 <= upstream.status < 300 else upstream.status
                LOG.info('%s %s -> %s (rewritten %s)', method,
                         urlsplit(final_url).hostname, status, kind.upper())
                return web.Response(status=status, headers=headers, body=rewritten)
            # Not a manifest after all: the body is already read, pass it on.
            headers = copied_response_headers(upstream)
            headers.pop('Content-Length', None)
            return web.Response(status=upstream.status, headers=headers, body=data)

        headers = copied_response_headers(upstream)
        response = web.StreamResponse(status=upstream.status, headers=headers)
        await response.prepare(request)
        try:
            if method != 'HEAD':
                async for chunk in upstream.content.iter_chunked(128 * 1024):
                    await response.write(chunk)
            await response.write_eof()
        except (ClientConnectionError, ConnectionResetError, asyncio.CancelledError):
            # Kodi intentionally closes range probes as soon as it has enough
            # bytes to identify a stream. This is normal, not a relay failure.
            LOG.debug('client closed %s %s early', method,
                      urlsplit(final_url).hostname)
        LOG.info('%s %s -> %s', method, urlsplit(final_url).hostname, upstream.status)
        return response
    finally:
        upstream.release()


async def health(_request):
    return web.json_response({'status': 'ok'})


async def create_app():
    if len(SIGNING_KEY) < 32:
        raise RuntimeError('RELAY_SIGNING_KEY must contain at least 32 characters')
    if not PUBLIC_BASE.startswith(('http://', 'https://')):
        raise RuntimeError('RELAY_PUBLIC_BASE must be an HTTP(S) URL')
    app = web.Application(client_max_size=MAX_REQUEST_BYTES)
    timeout = ClientTimeout(total=None, connect=20, sock_read=90)
    app['session'] = ClientSession(timeout=timeout,
                                   connector=TCPConnector(limit=100, ttl_dns_cache=300),
                                   auto_decompress=True, trust_env=False)
    app.router.add_get('/healthz', health)
    app.router.add_route('*', '/v1/relay', relay)
    app.router.add_route('*', r'/v1/base/{exp:\d+}/{sig:[0-9a-f]{64}}/{prefix:[A-Za-z0-9_-]+}/{tail:.*}', base)

    async def close_session(application):
        await application['session'].close()

    app.on_cleanup.append(close_session)
    return app


if __name__ == '__main__':
    web.run_app(create_app(), host=LISTEN_HOST, port=LISTEN_PORT,
                access_log=None)
