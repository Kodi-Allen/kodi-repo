# MyMovies Back Artwork Copy

Kodi script add-on that scans movie and TV show folders from the Kodi video library.
Every found `mymovies-back.jpg` is copied in the same folder as `back.jpg`.
After a completed run, the add-on can immediately trigger a Kodi video library scan.

## Development Layout

This folder is the add-on root:

```text
script.mymovies.backcopy/
  addon.xml
  default.py
  resources/
```

For testing, install or copy this complete `script.mymovies.backcopy` folder into Kodi's `addons` directory, or package it as a zip with this folder as the top-level zip entry.

## Behavior

- Reads movie, TV show, and episode paths from Kodi's video library through JSON-RPC.
- Recursively scans the compacted library folders with `xbmcvfs`.
- Copies `mymovies-back.jpg` to `back.jpg` in the same directory.
- Folders with an existing `back.jpg` are skipped early by default.
- Enable `Renew existing back.jpg` in the add-on settings to replace existing `back.jpg` files.
- Manual run: start the add-on from Kodi's program add-ons or press "Run now" in the add-on settings.
- Scheduled run: enable scheduled runs in the add-on settings and choose startup/interval behavior.
- The video library scan is started with `UpdateLibrary(video)` immediately after the copy pass.

The script can also be launched with:

```text
RunScript(script.mymovies.backcopy,renew=false,scan_library=true)
```
