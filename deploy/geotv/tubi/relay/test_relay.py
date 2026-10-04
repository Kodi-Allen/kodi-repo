import os
import base64
import re
import unittest
from urllib.parse import parse_qs, urlsplit


os.environ.setdefault('RELAY_PUBLIC_BASE', 'http://relay.test:8893')
os.environ.setdefault('RELAY_SIGNING_KEY', 'a' * 64)

import relay  # noqa: E402


class FakeRequest(object):
    def __init__(self, headers):
        self.headers = headers


class FakeUpstream(object):
    def __init__(self, headers):
        self.headers = headers


class RelayHeadersTest(unittest.TestCase):
    def test_manifest_range_probe_is_not_forwarded(self):
        request = FakeRequest({'range': 'bytes=0-4095',
                               'If-Range': 'old-etag',
                               'Accept': '*/*'})
        headers = relay.forwarded_request_headers(
            request, 'https://cdn.example/master.m3u8?token=abc')
        self.assertNotIn('range', {name.lower() for name in headers})
        self.assertNotIn('if-range', {name.lower() for name in headers})
        self.assertEqual('*/*', headers['Accept'])

    def test_dash_manifest_range_probe_is_not_forwarded(self):
        request = FakeRequest({'Range': 'bytes=0-4095'})
        headers = relay.forwarded_request_headers(
            request, 'https://cdn.example/title/manifest.mpd?token=abc')
        self.assertNotIn('range', {name.lower() for name in headers})

    def test_segment_range_is_forwarded(self):
        request = FakeRequest({'Range': 'bytes=0-4095'})
        headers = relay.forwarded_request_headers(
            request, 'https://cdn.example/segment.ts')
        self.assertEqual('bytes=0-4095', headers['Range'])

    def test_rewritten_manifest_drops_stale_representation_headers(self):
        upstream = FakeUpstream({'Content-Type': 'application/x-mpegURL',
                                 'Content-Length': '1824',
                                 'Content-Range': 'bytes 0-1823/1824',
                                 'Accept-Ranges': 'bytes',
                                 'ETag': 'upstream-body',
                                 'Cache-Control': 'max-age=10'})
        headers = relay.rewritten_manifest_headers(upstream)
        lowered = {name.lower(): value for name, value in headers.items()}
        self.assertEqual('application/vnd.apple.mpegurl', lowered['content-type'])
        self.assertEqual('max-age=10', lowered['cache-control'])
        for name in ('content-length', 'content-range', 'accept-ranges', 'etag'):
            self.assertNotIn(name, lowered)

    def test_rewritten_dash_headers_use_dash_content_type(self):
        upstream = FakeUpstream({'Content-Type': 'application/dash+xml',
                                 'Content-Length': '1824'})
        headers = relay.rewritten_manifest_headers(upstream, 'dash')
        self.assertEqual('application/dash+xml', headers['Content-Type'])
        self.assertNotIn('Content-Length', headers)

    def test_dash_base_urls_are_signed_and_resolved(self):
        source = 'https://cdn.example/title/manifest.mpd?token=manifest'
        body = b'''<?xml version="1.0"?><MPD xmlns="urn:mpeg:dash:schema:mpd:2011">
<Period><AdaptationSet><Representation><BaseURL>video.mp4?token=a&amp;b=2</BaseURL>
<SegmentBase indexRange="10-20"/></Representation></AdaptationSet></Period></MPD>'''
        rewritten = relay.rewrite_dash_manifest(body, source).decode()
        match = re.search(r'<BaseURL>(.*?)</BaseURL>', rewritten)
        self.assertIsNotNone(match)
        routed = match.group(1).replace('&amp;', '&')
        query = parse_qs(urlsplit(routed).query)
        encoded = query['u'][0]
        target = base64.urlsafe_b64decode(
            encoded + '=' * (-len(encoded) % 4)).decode()
        self.assertEqual('https://cdn.example/title/video.mp4?token=a&b=2', target)

    def test_media_keeps_length_and_range(self):
        upstream = FakeUpstream({'Content-Type': 'video/mp2t',
                                 'Content-Length': '1048576',
                                 'Content-Range': 'bytes 0-1048575/2097152'})
        headers = relay.copied_response_headers(upstream)
        self.assertEqual('1048576', headers['Content-Length'])
        self.assertEqual('bytes 0-1048575/2097152', headers['Content-Range'])


if __name__ == '__main__':
    unittest.main()
