# Joyn relay

A small capability-URL relay that lets Kodi fetch Joyn's DASH manifests,
segments, subtitles and Widevine licence requests through a chosen exit,
without changing Kodi's global network settings. It is the GeoTV Tubi relay
with two additions for Joyn:

- Joyn's MPDs have no `BaseURL`; their `SegmentTemplate`s name segments
  relative to the manifest. The relay inserts one signed prefix capability
  (`/v1/base/<expiry>/<signature>/<prefix>/…`) as the MPD's `BaseURL`, so
  every init, media and subtitle segment comes back through the relay.
- Upstream hosts are limited to `RELAY_ALLOWED_HOSTS`
  (default `joyn.de,joyn.at,joyn.ch,p7s1video.net,p7s1.io`), also after
  redirects; private and local addresses are always refused.

Licence requests and responses pass through byte for byte. The relay never
sees keys and does not decrypt anything; decryption stays in the playback
device's Widevine CDM.

## Settings in the add-on

For the region that should use the exit (Settings → Germany / Switzerland):

| Setting | Value |
|---|---|
| Network route | Custom |
| HTTP CONNECT proxy host / port | the exit's CONNECT proxy |
| Proxy user name / password | as configured for the proxy |
| Media relay host / port | this relay |
| Relay signing key | `RELAY_SIGNING_KEY` |

A custom route with a missing proxy, relay or key fails closed; nothing falls
back to the direct connection. *Connection test* in the same settings
category walks API, playback right and relay step by step.

## Note on exits

Joyn checks the requesting address when it issues the playback right. It
refuses known VPN addresses (`ENT_USER_VPN_DETECTED`) and addresses outside
the region (`ENT_AssetNotAvailableInCountry`). The add-on reports both and
does not try to work around them; the exit must be a connection Joyn accepts
for that region.

## Run and test

```bash
cp compose.example.yml compose.yml   # review, then fill .env
docker compose up -d --build
curl http://192.0.2.10:34410/healthz
python -m unittest test_relay        # inside the image or with aiohttp installed
```
