# Samsung TV Plus for Kodi (Italy)

An unofficial Kodi video add-on for the free **Samsung TV Plus** live channels
of **Italy**, with its own full-screen interface: Home, Live TV guide and
Search, favourites, and optional integration into Kodi's TV section.

Not affiliated with or endorsed by Samsung. Samsung and the channel providers
decide which channels play where; the add-on shows what they serve.

## Features

- **Home** with two featured cards showing what is on now, and channel rows
  by Samsung's own groups (Film, Serie TV, Sport, News, …)
- **Live TV guide**: channel logos, now and next, a half-hour timeline, the
  current time and programme progress; categories are All channels, your
  Favourites and Samsung's groups
- **Favourites**: press the context-menu key on a channel in the guide, or use
  *Add to favourites* in the classic folders
- **Search** by channel name, group or the programme on now
- **Playback** through InputStream Adaptive
- **Network route**: direct, or through an Italian relay for the channels that
  only play from Italy (all playlists and segments then go through the relay)
- **Kodi TV (optional)**: channels for IPTV Manager, off by default

## Requirements

- Kodi 21 (Omega). Developed and tested on Kodi 21.1.
- `inputstream.adaptive`
- `script.module.requests`
- For Kodi TV: `service.iptv.manager` with IPTV Simple Client

## Installation

From the Kodi Allen repository: *Add-ons → Install from repository →
Kodi Allen Repository → Video add-ons → Samsung TV Plus*, or install the
release ZIP with *Install from zip file*. Open it from *Videos → Add-ons*.

## Region and network

Italy is the supported region. Most channels play from anywhere Samsung serves
them; some only from an Italian connection. For those, choose *Settings →
Network → Route: Italian relay* and enter your relay's host, port and signing
key. Kodi then fetches every playlist and segment through the relay, as signed,
short-lived URLs; the add-on's own requests (channel list, guide) stay direct,
so no proxy is needed.

The [Kodi Allen media relay](../deploy/joyn-relay/README.md) works as that
relay when it runs behind an Italian exit with `RELAY_ALLOWED_HOSTS` set to an
empty value: Samsung's streams come from many CDNs, so the Joyn host list does
not fit. Private and local addresses stay refused.

Samsung lists a few Italian channels with Widevine protection (Discovery,
NOVE, DMAX, the Sony One channels, …). Their licence server serves Samsung
devices only, so the add-on leaves them out.

## Kodi TV

*Settings → Kodi TV → Add Samsung TV Plus to Kodi Live TV* exports the
channels to IPTV Manager as group *Samsung TV Plus IT*, with fixed numbers from
8001 that never change. If Kodi already has channels in that range from
another source (for example the same channels through Threadfin), nothing is
exported, so no channel appears twice. Playlist entries are plugin routes; no
expiring stream address is ever stored.

## Data sources

Channel list, groups, logos and the programme guide come from the Samsung TV
Plus data that Matt Huisman publishes at `i.mjh.nz/SamsungTVPlus`; playback
starts at `jmp2.uk`, which redirects to the stream Samsung currently serves.
The same sources are used by
[samsung-tvplus-for-channels](https://github.com/matthuisman/samsung-tvplus-for-channels)
and SlyGuy's Samsung TV Plus add-on. No code was taken from either.

## Licence

GPL-3.0-or-later, see [LICENSE.txt](LICENSE.txt). The interface is derived from
the Kodi Allen Tubi and Joyn add-ons.
