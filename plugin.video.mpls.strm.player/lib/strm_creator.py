"""
DiscDB STRM Creator - Kodi Integration
=======================================
Creates .strm files for multi-episode Blu-ray discs using thediscdb.com metadata.
Generates plugin:// URLs so Kodi calls the addon directly for playback.

Two modes:
  1. URL mode:  Enter a thediscdb.com URL + browse to a single disc
  2. UPC mode:  Enter EAN/UPC + browse to parent folder → auto-scans all discs

Disc paths are browsed via Kodi's source browser, so any protocol
(NFS, SMB, WebDAV, local, etc.) works out of the box.
"""

import re
import json
import urllib.request
import urllib.parse
import xbmc
import xbmcvfs

ADDON_ID = 'plugin.video.mpls.strm.player'

GRAPHQL_URL = "https://thediscdb.com/graphql/"

GRAPHQL_QUERY_URL = """
query GetDisc($seriesSlug: String!, $releaseSlug: String!, $discSlug: String!) {
  mediaItems(where: { slug: { eq: $seriesSlug } }) {
    nodes {
      title
      year
      releases(where: { slug: { eq: $releaseSlug } }) {
        slug
        title
        discs(where: { slug: { eq: $discSlug } }) {
          slug
          name
          format
          titles {
            description
            season
            episode
            itemType
            sourceFile
          }
        }
      }
    }
  }
}
"""

GRAPHQL_QUERY_UPC = """
query GetByUpc($upc: String!) {
  mediaItems(where: { releases: { some: { upc: { eq: $upc } } } }) {
    nodes {
      title
      year
      slug
      releases(where: { upc: { eq: $upc } }) {
        slug
        title
        upc
        discs {
          slug
          name
          format
          titles {
            description
            season
            episode
            itemType
            sourceFile
          }
        }
      }
    }
  }
}
"""


def log(msg):
    xbmc.log(f'[MPLS STRM Creator] {msg}', xbmc.LOGINFO)


# ============================================================
# API
# ============================================================

def graphql_request(query, variables):
    """Execute a GraphQL request against thediscdb.com."""
    payload = json.dumps({
        "query": query,
        "variables": variables
    }).encode('utf-8')

    req = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'MPLS-STRM-Player/4.1'
        }
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode('utf-8'))

    if 'errors' in data:
        errors = '; '.join(e.get('message', str(e)) for e in data['errors'])
        raise RuntimeError(f"API error: {errors}")

    return data


def parse_discdb_url(url):
    """Parse a thediscdb.com URL and extract series, release, and disc slugs."""
    pattern = r'thediscdb\.com/(?:series|movies)/([^/]+)/releases/([^/]+)/discs/([^/?#\s]+)'
    match = re.search(pattern, url)
    if not match:
        raise ValueError(
            "Invalid thediscdb.com URL.\n"
            "Expected: .../series/<series>/releases/<release>/discs/<disc>"
        )
    return match.group(1), match.group(2), match.group(3)


# ============================================================
# PATH BUILDING
# ============================================================

def build_playback_url(disc_path, mpls_file):
    """
    Build the playback URL for an MPLS file on a disc.
    disc_path comes from Kodi's browse dialog (nfs://, smb://, local, etc.).
    """
    disc_path = disc_path.rstrip('/')

    if disc_path.lower().endswith('.iso'):
        # ISO: wrap in udf:// with URL-encoded source path
        encoded = urllib.parse.quote(disc_path, safe='()')
        encoded = re.sub(r'%[0-9A-F]{2}', lambda m: m.group(0).lower(), encoded)
        return f"udf://{encoded}/BDMV/PLAYLIST/{mpls_file}"
    else:
        # BDMV folder
        if not disc_path.upper().endswith('BDMV'):
            disc_path = disc_path + '/BDMV'
        return f"{disc_path}/PLAYLIST/{mpls_file}"


def build_plugin_url(playback_url, title):
    """Wrap a playback URL into a plugin:// URL for .strm files."""
    params = urllib.parse.urlencode({
        'action': 'play',
        'url': playback_url,
        'title': title
    })
    return f"plugin://{ADDON_ID}/?{params}"


# ============================================================
# FILENAME HELPERS
# ============================================================

def sanitize_filename(name):
    """Remove characters not allowed in filenames."""
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()


def build_strm_filename(show_title, season, episode):
    """Build .strm filename: Show.Name.S01E01.strm"""
    safe_show = sanitize_filename(show_title).replace(' ', '.')
    safe_show = re.sub(r'\.{2,}', '.', safe_show)
    return f"{safe_show}.S{season:02d}E{episode:02d}.strm"


# ============================================================
# DISC SLUG EXTRACTION
# ============================================================

def extract_disc_slug(name):
    """
    Extract disc slug (e.g. 's01d01') from a folder or file name.
    Matches patterns like S01D01, S1D1, s02d03, etc.
    """
    match = re.search(r'[Ss](\d+)[Dd](\d+)', name)
    if match:
        season = int(match.group(1))
        disc = int(match.group(2))
        return f"s{season:02d}d{disc:02d}"
    return None


def scan_disc_sources(parent_path):
    """
    Scan a parent folder for disc sources (BDMV folders and ISOs).
    Returns list of (disc_slug, disc_path) tuples.
    """
    parent_path = parent_path.rstrip('/')
    found = []

    try:
        dirs, files = xbmcvfs.listdir(parent_path + '/')
    except Exception as e:
        log(f'Error listing {parent_path}: {e}')
        return found

    # Check subdirectories (BDMV disc folders)
    for dirname in dirs:
        slug = extract_disc_slug(dirname)
        if slug:
            disc_path = f"{parent_path}/{dirname}"
            found.append((slug, disc_path))
            log(f'Found disc folder: {dirname} -> {slug}')

    # Check files (ISOs)
    for filename in files:
        if filename.lower().endswith('.iso'):
            slug = extract_disc_slug(filename)
            if slug:
                disc_path = f"{parent_path}/{filename}"
                found.append((slug, disc_path))
                log(f'Found ISO: {filename} -> {slug}')

    found.sort(key=lambda x: x[0])
    return found


# ============================================================
# STRM WRITING (shared by both modes)
# ============================================================

def write_strm_files_for_disc(disc_data, disc_path, show_title, show_year, output_base):
    """
    Write .strm files for all episodes on a single disc.
    Returns list of created file paths.
    """
    titles = disc_data.get('titles') or []

    # Filter episodes
    episodes = [
        t for t in titles
        if t.get('itemType') == 'Episode'
        and t.get('season')
        and t.get('episode')
        and t.get('sourceFile')
    ]
    if not episodes:
        episodes = [t for t in titles if t.get('sourceFile')]

    if not episodes:
        return []

    # Output folder: output_base/Show Title (Year)/
    show_folder = sanitize_filename(
        f"{show_title} ({show_year})" if show_year else show_title
    )
    output_folder = f"{output_base.rstrip('/')}/{show_folder}"

    created = []
    for title_entry in sorted(episodes, key=lambda t: (
        int(t.get('season') or 0), int(t.get('episode') or 0)
    )):
        mpls_file = title_entry['sourceFile']
        try:
            season = int(title_entry['season'])
            episode = int(title_entry['episode'])
        except (TypeError, ValueError):
            continue

        playback_url = build_playback_url(disc_path, mpls_file)
        ep_title = f"{show_title} S{season:02d}E{episode:02d}"
        plugin_url = build_plugin_url(playback_url, ep_title)

        season_folder = f"{output_folder}/Season {season:02d}"
        xbmcvfs.mkdirs(season_folder)

        strm_filename = build_strm_filename(show_title, season, episode)
        strm_path = f"{season_folder}/{strm_filename}"

        f = xbmcvfs.File(strm_path, 'w')
        f.write(plugin_url)
        f.close()

        log(f'Created: {strm_path} -> {mpls_file}')
        created.append(strm_path)

    return created


# ============================================================
# MODE 1: CREATE FROM URL (single disc)
# ============================================================

def create_strm_files(discdb_url, disc_path, output_base, progress=None):
    """
    Create .strm files from a thediscdb.com URL and a single disc path.
    Returns (created_files, show_title, output_folder).
    """
    if progress:
        progress.update(10, "Parsing URL...")
    series_slug, release_slug, disc_slug = parse_discdb_url(discdb_url)

    if progress:
        progress.update(20, "Querying thediscdb.com...")
    data = graphql_request(GRAPHQL_QUERY_URL, {
        "seriesSlug": series_slug,
        "releaseSlug": release_slug,
        "discSlug": disc_slug
    })

    if progress:
        progress.update(40, "Processing disc data...")

    media_nodes = (data.get('data') or {}).get('mediaItems', {}).get('nodes', [])
    if not media_nodes:
        raise ValueError(f"No data found for '{series_slug}'.")

    media_item = media_nodes[0]
    show_title = media_item['title']
    show_year = str(media_item.get('year', '') or '')

    releases = media_item.get('releases') or []
    if not releases:
        raise ValueError(f"Release '{release_slug}' not found.")

    disc_nodes = releases[0].get('discs') or []
    if not disc_nodes:
        raise ValueError(f"Disc '{disc_slug}' not found.")

    if progress:
        progress.update(50, "Creating .strm files...")

    created = write_strm_files_for_disc(
        disc_nodes[0], disc_path, show_title, show_year, output_base
    )

    show_folder = sanitize_filename(
        f"{show_title} ({show_year})" if show_year else show_title
    )
    output_folder = f"{output_base.rstrip('/')}/{show_folder}"

    if progress:
        progress.update(100, "Done!")

    return created, show_title, output_folder


# ============================================================
# MODE 2: CREATE FROM UPC (auto-scan all discs)
# ============================================================

def create_strm_files_by_upc(upc, parent_path, output_base, progress=None):
    """
    Create .strm files for an entire release identified by UPC/EAN.
    Scans parent_path for disc folders/ISOs, matches them to API disc slugs.

    Returns (created_files, show_title, output_folder, matched_count, total_api_discs).
    """
    # Normalize: strip leading zero from EAN-13 to get UPC-12
    upc = upc.strip()
    if len(upc) == 13 and upc.startswith('0'):
        upc_12 = upc[1:]
    else:
        upc_12 = upc

    # 1. Query API by UPC
    if progress:
        progress.update(5, "Querying thediscdb.com by UPC...")

    data = graphql_request(GRAPHQL_QUERY_UPC, {"upc": upc_12})

    media_nodes = (data.get('data') or {}).get('mediaItems', {}).get('nodes', [])
    if not media_nodes:
        # Try with original input (maybe it's already UPC-12 or a different format)
        if upc != upc_12:
            data = graphql_request(GRAPHQL_QUERY_UPC, {"upc": upc})
            media_nodes = (data.get('data') or {}).get('mediaItems', {}).get('nodes', [])

    if not media_nodes:
        raise ValueError(f"No release found for UPC/EAN '{upc}'.")

    media_item = media_nodes[0]
    show_title = media_item['title']
    show_year = str(media_item.get('year', '') or '')

    releases = media_item.get('releases') or []
    if not releases:
        raise ValueError("Release data not found.")

    release = releases[0]
    api_discs = release.get('discs') or []
    log(f'UPC lookup: {show_title} ({show_year}), Release: {release["title"]}, {len(api_discs)} discs')

    # 2. Build lookup: slug -> disc data
    disc_lookup = {}
    for disc in api_discs:
        disc_lookup[disc['slug']] = disc

    # 3. Scan folder for disc sources
    if progress:
        progress.update(15, "Scanning disc folders...")

    local_discs = scan_disc_sources(parent_path)
    if not local_discs:
        raise ValueError(
            f"No disc folders (S01D01, S02D01, ...) or ISOs found in:\n{parent_path}"
        )

    log(f'Found {len(local_discs)} local disc(s), API has {len(api_discs)} disc(s)')

    # 4. Match local discs to API discs
    matched = []
    unmatched_local = []
    for slug, disc_path in local_discs:
        if slug in disc_lookup:
            matched.append((slug, disc_path, disc_lookup[slug]))
        else:
            unmatched_local.append((slug, disc_path))
            log(f'No API match for local disc: {slug}')

    if not matched:
        available = ', '.join(sorted(disc_lookup.keys()))
        found = ', '.join(s for s, _ in local_discs)
        raise ValueError(
            f"No discs matched between folder and API.\n"
            f"Folder: {found}\n"
            f"API: {available}"
        )

    log(f'Matched {len(matched)} disc(s)')

    # 5. Create .strm files for all matched discs
    all_created = []
    for i, (slug, disc_path, disc_data) in enumerate(matched):
        if progress:
            pct = 20 + int((i / len(matched)) * 75)
            disc_name = disc_data.get('name', slug)
            progress.update(pct, f"Processing {disc_name}...")

        created = write_strm_files_for_disc(
            disc_data, disc_path, show_title, show_year, output_base
        )
        all_created.extend(created)
        log(f'Disc {slug}: {len(created)} .strm files')

    show_folder = sanitize_filename(
        f"{show_title} ({show_year})" if show_year else show_title
    )
    output_folder = f"{output_base.rstrip('/')}/{show_folder}"

    if progress:
        progress.update(100, "Done!")

    return all_created, show_title, output_folder, len(matched), len(api_discs)
