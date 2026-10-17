# Artwork Beef
<span style="font-size: 1.2em; font-weight: 600">An add-on for Kodi</span>

> **Kodi Allen distribution — version 0.28.10.** This is a maintained distribution of
> [rmrector's Artwork Beef](https://github.com/rmrector/script.artwork.beef), with a Python 3
> migration, Kodi 21 (Omega) compatibility changes, and later fixes for Kodi 19+ APIs and
> dependencies. See the [changelog](changelog.txt) and current [requirements](addon.xml).
> Install it through the [Kodi Allen Repository](../README.md#installation). The upstream
> documentation below predates these changes; no complete platform or Kodi-version test
> matrix is documented for this distribution.

Artwork Beef automatically adds extra artwork for media in your video and music libraries. It is generally intended to
handle extended artwork just as Kodi and scrapers already do for basic artwork. It grabs artwork from the wonderful web
services [fanart.tv], [TheTVDB.com], [The Movie Database], and [TheAudioDB.com].

[fanart.tv]: https://fanart.tv/
[TheTVDB.com]: https://thetvdb.com/
[The Movie Database]: https://www.themoviedb.org/
[TheAudioDB.com]: https://www.theaudiodb.com/

The original upstream release was developed for Kodi 17 **Krypton**, with notes for earlier
Python 2-based Kodi versions. This distribution instead requires Python 3, as declared in
`addon.xml`; its changelog records the port and subsequent Kodi 19+ fixes. The old upstream
statement that Kodi 19 **Matrix** was unsupported does not describe this distribution.

For this distribution, report problems in [Kodi Allen Repository issues](https://github.com/Kodi-Allen/kodi-repo/issues).

Original upstream references: [forum thread](https://forum.kodi.tv/showthread.php?tid=258886) and
[source code](https://github.com/rmrector/script.artwork.beef).

Full documentation available at https://rmrector.github.io/script.artwork.beef/.

### Upstream notes

- The original upstream documentation described music library support as Kodi 18 Leia only;
  that note predates this distribution's Python 3 port.
- It cannot set artwork for "all seasons". [related trac ticket](https://trac.kodi.tv/ticket/16139)

### Thoughts

- Scrapers and NFO files need to set web service IDs like IMDB number, TVDB ID, or TMDB ID
  for media types that Kodi supports such IDs for: movies, TV shows, and episodes
  - Music files need to be tagged with MusicBrainz IDs; Artist, Release Group, and Track IDs
- Movie thumbnails / extrathumbs aren't added from external sources. There is no way to tell the
  difference between stills
  and press/marketing images from the web services, while thumbs should only include stills.
  Skins can try multiple fanart for a similar look. Generating more than one thumb from
  a video file is outside the scope of this add-on, but any provided by a media manager is added to the library.
  Plugins can also set these to the ListItem, if their source provides more than one thumbnail.
- It would be nice to have a Kodi built-in way for skins to feed multiple art to a `multiimage`,
  maybe something like `$INFO[ListItem.MultiArt(fanart)]` to pull all `fanart` and `fanart#` together.
  I have no idea how it could be implemented in Kodi, though.

### Running from source

The API keys have been removed from the repo, and are only included in the final installable zip.
Individual users that need to run from source can copy projectkeys.py from the installable zip
to the same directory in source.
