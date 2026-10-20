import os
import re
import unittest

os.environ.setdefault('RELAY_SIGNING_KEY', 'k' * 64)
os.environ.setdefault('RELAY_PUBLIC_BASE', 'http://relay.test:34410')

import relay  # noqa: E402

LIVE_MPD = b'''<?xml version="1.0"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="dynamic"><Period>
<AdaptationSet><ContentProtection schemeIdUri="urn:uuid:EDEF8BA9-79D6-4ACE-A3C8-27DCD51D21ED"/>
<SegmentTemplate initialization="$RepresentationID$/init.mp4" media="$RepresentationID$/$Time$.m4s"/>
<Representation id="orf1-at_video_01/cenc"/></AdaptationSet></Period></MPD>'''


class Request(object):
    def __init__(self, match, query=''):
        self.match_info = match
        self.query_string = query


class RelayTest(unittest.TestCase):
    def test_mpd_without_base_url_gets_a_signed_prefix(self):
        text = relay.rewrite_dash_manifest(LIVE_MPD, 'https://ac-003.live.p7s1video.net/x/orf1-at/cenc-default.mpd').decode()
        base = re.search(r'<BaseURL>([^<]+)</BaseURL>', text).group(1)
        self.assertTrue(base.startswith('http://relay.test:34410/v1/base/'))
        self.assertIn('urn:uuid:EDEF8BA9', text)  # DRM data untouched
        self.assertEqual(1, text.count('<BaseURL>'))
        exp, sig, prefix = base.split('/')[5:8]
        target = relay.target_from_prefix(Request({'exp': exp, 'sig': sig, 'prefix': prefix,
                                                   'tail': 'orf1-at_video_01/cenc/init.mp4'}))
        self.assertEqual('https://ac-003.live.p7s1video.net/x/orf1-at/orf1-at_video_01/cenc/init.mp4', target)

    def test_prefix_rejects_tampering_and_climbing(self):
        base = relay.prefix_url('https://cdn.joyn.de/a/')
        exp, sig, prefix = base.split('/')[5:8]
        with self.assertRaises(relay.web.HTTPUnauthorized):
            relay.target_from_prefix(Request({'exp': exp, 'sig': '0' * 64, 'prefix': prefix, 'tail': 'x'}))
        with self.assertRaises(relay.web.HTTPBadRequest):
            relay.target_from_prefix(Request({'exp': exp, 'sig': sig, 'prefix': prefix, 'tail': '../b/x'}))
        # A prefix signature is not a full-URL signature and vice versa.
        self.assertNotEqual(sig, relay._signature(prefix, exp))

    def test_existing_base_urls_are_routed(self):
        mpd = b'<MPD><BaseURL>https://cdn.joyn.de/v/</BaseURL><BaseURL>file.mp4</BaseURL></MPD>'
        text = relay.rewrite_dash_manifest(mpd, 'https://cdn.joyn.de/v/m.mpd').decode()
        self.assertIn('/v1/base/', text)
        self.assertIn('/v1/relay?u=', text)


class AllowlistTest(unittest.IsolatedAsyncioTestCase):
    async def test_foreign_hosts_are_refused(self):
        with self.assertRaises(relay.web.HTTPForbidden):
            await relay.validate_public_url('https://example.com/')


if __name__ == '__main__':
    unittest.main()
