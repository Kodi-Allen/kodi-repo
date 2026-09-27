# ParkStream

Unofficial Kodi video add-on for South Park.

ParkStream lets you browse and watch South Park episodes from the official South Park
websites in Kodi. It is an independently maintained fork of
[wargio/plugin.video.southpark_unofficial](https://github.com/wargio/plugin.video.southpark_unofficial).

## Features

- Playback through the current official South Park video service
- Season list with covers for all seasons, descriptions and premiere years
- Episode list with official episode stills, air dates and runtimes
- Show artwork (clear logo, clear art, banner, fan art) for Kodi skins that display it
- Random episode, optionally played directly
- Episodes with more than one audio track offer all tracks in Kodi's audio menu
- Menus in English, German, Italian, Portuguese (Brazil, Portugal), Spanish (Spain, Mexico)
  and Swedish

## Requirements

- Kodi 21 (Omega). Tested on a Vero 4K+ with Kodi 21.1; Kodi 19 and 20 are untested.

## Installation

1. Download `plugin.video.parkstream-<version>.zip`.
2. In Kodi, enable *Settings → System → Add-ons → Unknown sources*.
3. Open *Add-ons → Install from zip file* and select the downloaded file.

## Usage

Open ParkStream from the video add-ons. The add-on settings contain:

| Setting | Effect |
|---|---|
| Location | Selects the regional South Park site, which determines the audio and description language. *Germany* plays German, *North America [EN]* plays English. |
| Enable subtitles | Only applies to legacy streams; the current video service delivers no separate subtitles to the add-on. |
| Play random episode directly | Starts a random episode instead of listing it first. |
| Show loading notification | Shows "Loading …" with the episode title while an episode starts. On by default. |
| Clear cache | Removes the cached episode lists. |

Confirm changes in the settings dialog with **OK**. Closing the dialog with *Back* discards them.
Kodi does not reload the list that is already on screen, so a new location shows up once you open
a folder or return to ParkStream.

## Known limitations

- Which episodes are available depends on your location and on the regional catalogue of the
  official site. A few episodes are not offered in every language.
- *North America [EN]* uses the English version of the official German-language site
  (`southpark.de/en`). This is verified for viewers in Germany, Austria and Switzerland.
  Other regions may be redirected by the official site.
- The official streams contain inserted advertising breaks.

## Data sources

- Episode lists: the `addon-data` branch of
  [wargio/plugin.video.southpark_unofficial](https://github.com/wargio/plugin.video.southpark_unofficial/tree/addon-data).
- Streams, episode stills, English and German season descriptions and runtimes: the official
  South Park websites. `tools/generate-episode-metadata.py` regenerates
  `resources/data/episode-metadata.json`.
- Spanish and Portuguese season descriptions: [TheTVDB](https://thetvdb.com/series/south-park).
  Locations without descriptions in their own language fall back to English.

## Development

Run the resolver tests from the repository root:

```sh
PYTHONPATH=. python3 -m unittest tests.test_stream_resolver
```

## Credits

- Original add-on *plugin.video.southpark_unofficial* by Giovanni Dante Grazioli (wargio)
- Contributors to the original add-on: anxdpanic, eldergabriel, mvn23, Niema Moshiri, serajr

## License

ParkStream is free software, licensed under the
[GNU General Public License, version 2](LICENSE.txt) (GPL-2.0-only).

- Copyright (C) 2015–2023 Giovanni Dante Grazioli (wargio) and contributors
- Copyright (C) 2026 Kodi-Allen — modifications for ParkStream, see [changelog.txt](changelog.txt)
  and the Git history for what was changed and when

The GPL applies to the source code. It does not cover the South Park artwork included for
identification (season covers, logos, fan art), which remains the property of its owners.

## Disclaimer

ParkStream is unofficial and not affiliated with or endorsed by South Park Studios,
Comedy Central or Paramount. South Park and all related titles, characters and artwork are
trademarks and copyrights of their respective owners. Check your local laws before use.
