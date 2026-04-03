#!/usr/bin/env python3
"""
DiscDB STRM Creator
===================
Erstellt Kodi .strm Files für Multi-Episode Blu-ray Discs anhand von thediscdb.com URLs.

Verwendung:
    python discdb_strm_creator.py <discdb_url> <disc_pfad>

    disc_pfad:  Entweder der Pfad zum BDMV-Ordner ODER zur .iso Datei (Windows-Pfad)

Beispiele:
    # BDMV Ordner (UHD):
    python discdb_strm_creator.py \\
        https://thediscdb.com/series/friends-1994/releases/2024-complete-series-4k/discs/s01d01 \\
        "Z:\\Serien\\UHD\\Friends (1994)\\Staffel 1\\Friends.1994.S01D01.COMPLETE.UHD.BLURAY\\BDMV"

    # ISO (BD):
    python discdb_strm_creator.py \\
        https://thediscdb.com/series/las-vegas-2003/releases/.../discs/s01d01 \\
        "Z:\\Serien\\BLURAY\\Las Vegas (2003)\\Las.Vegas.S01D01.COMPLETE.BLURAY-SLIPSTREAM.iso"

Drag & Drop: Starte run_discdb_strm.bat und ziehe den Disc-Ordner darauf.
"""

import sys
import os
import re
import json
import urllib.request
import urllib.parse
from pathlib import Path

# ============================================================
# KONFIGURATION - Hier deine Pfade eintragen
# ============================================================

# NAS Einstellungen
NAS_IP = "192.168.68.114"
NAS_NFS_BASE = "/volume1/NAS"       # NFS Export-Pfad auf dem NAS

# Windows Laufwerk das auf den NAS-Root gemappt ist
# Z:\ = nfs://192.168.68.114/volume1/NAS/
WINDOWS_DRIVE_LETTER = "Z"          # Nur der Buchstabe, ohne :\

# Ausgabe-Ordner für .strm Files
UHD_STRM_OUTPUT = r"Z:\Serien\UHD\STRMS"
BD_STRM_OUTPUT  = r"Z:\Serien\BLURAY\STRMS"

# Show-Unterordner im STRM-Ausgabeordner erstellen?
# True:  Z:\Serien\UHD\STRMS\Friends (1994)\Friends.S01E01.strm
# False: Z:\Serien\UHD\STRMS\Friends.S01E01.strm
ORGANIZE_BY_SHOW = True

# Nur Episode-Titles ausgeben (keine Extras, Menüs etc.)?
EPISODES_ONLY = True

# ============================================================
# ERWEITERTE EINSTELLUNGEN
# ============================================================

# GraphQL Endpoint
GRAPHQL_URL = "https://thediscdb.com/graphql/"

# GraphQL Query
GRAPHQL_QUERY = """
query GetDisc($seriesSlug: String!, $releaseSlug: String!, $discSlug: String!) {
  mediaItems(where: { slug: { eq: $seriesSlug } }) {
    nodes {
      id
      title
      year
      releases(where: { slug: { eq: $releaseSlug } }) {
        id
        title
        discs(where: { slug: { eq: $discSlug } }) {
          id
          slug
          name
          format
          titles {
            id
            index
            description
            season
            episode
            itemType
            sourceFile
            duration
            displaySize
          }
        }
      }
    }
  }
}
"""


# ============================================================
# KERNFUNKTIONEN
# ============================================================

def log(msg):
    print(msg)


def parse_discdb_url(url):
    """
    Parst eine thediscdb.com URL und extrahiert Series-, Release- und Disc-Slug.

    Unterstützte Formate:
      https://thediscdb.com/series/friends-1994/releases/2024-complete-series-4k/discs/s01d01
    """
    pattern = r'thediscdb\.com/(?:series|movies)/([^/]+)/releases/([^/]+)/discs/([^/?#\s]+)'
    match = re.search(pattern, url)
    if not match:
        raise ValueError(
            f"Ungültige thediscdb.com URL: {url}\n"
            "Erwartetes Format: https://thediscdb.com/series/<serie>/releases/<release>/discs/<disc>"
        )
    return match.group(1), match.group(2), match.group(3)


def query_graphql(series_slug, release_slug, disc_slug):
    """Fragt die thediscdb.com GraphQL API ab."""
    payload = json.dumps({
        "query": GRAPHQL_QUERY,
        "variables": {
            "seriesSlug": series_slug,
            "releaseSlug": release_slug,
            "discSlug": disc_slug
        }
    }).encode('utf-8')

    req = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'DiscDB-STRM-Creator/1.0'
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP-Fehler beim Abrufen der API: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Netzwerkfehler: {e.reason}")


def windows_to_nfs_path(windows_path):
    """
    Konvertiert einen Windows-Pfad (Z:\\Serien\\...) in einen NFS-Pfad
    (nfs://192.168.68.114/volume1/NAS/Serien/...).

    Leerzeichen und Sonderzeichen werden NICHT enkodiert - Kodi verarbeitet
    NFS-Pfade direkt. (Nur innerhalb von udf:// müssen sie enkodiert werden.)
    """
    path = str(windows_path)

    # Laufwerksbuchstabe entfernen (z.B. "Z:")
    if len(path) >= 2 and path[1] == ':':
        path = path[2:]

    # Backslashes → Forward Slashes
    path = path.replace('\\', '/')

    # Führenden Slash entfernen (wird durch NFS Base wieder hinzugefügt)
    path = path.lstrip('/')

    return f"nfs://{NAS_IP}{NAS_NFS_BASE}/{path}"


def build_strm_content(disc_path, mpls_file):
    """
    Erstellt den Inhalt einer .strm Datei.

    disc_path:  Pfad zum BDMV-Ordner oder .iso File (Windows-Pfad)
    mpls_file:  MPLS-Dateiname, z.B. "00101.mpls"

    Gibt den Kodi-kompatiblen Pfad zurück.
    """
    disc_path = os.path.normpath(str(disc_path))
    is_iso = disc_path.lower().endswith('.iso')

    if is_iso:
        # ISO-Format:
        # udf://nfs%3a%2f%2f<IP>%2f...<pfad>...iso/BDMV/PLAYLIST/<mpls>
        # Klammern () werden in Kodi-URLs nicht enkodiert; Hex-Kodierung lowercase
        nfs_path = windows_to_nfs_path(disc_path)
        # Nur die Hex-Buchstaben in %XX-Sequenzen kleinschreiben (Kodi-Format)
        nfs_encoded = re.sub(r'%[0-9A-F]{2}',
                             lambda m: m.group(0).lower(),
                             urllib.parse.quote(nfs_path, safe='()'))
        return f"udf://{nfs_encoded}/BDMV/PLAYLIST/{mpls_file}"
    else:
        # BDMV-Ordner Format:
        # nfs://<IP>/volume1/NAS/.../BDMV/PLAYLIST/<mpls>

        # Sicherstellen dass der Pfad auf BDMV endet
        if not disc_path.upper().endswith('BDMV'):
            disc_path = os.path.join(disc_path, 'BDMV')

        playlist_path = os.path.join(disc_path, 'PLAYLIST', mpls_file)
        return windows_to_nfs_path(playlist_path)


def sanitize_filename(name):
    """Entfernt Zeichen die in Dateinamen nicht erlaubt sind."""
    # Ungültige Zeichen ersetzen oder entfernen
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    return name.strip()


def build_strm_filename(show_title, season, episode):
    """Erstellt den .strm Dateinamen im Format: Show.Name.S01E01.strm"""
    safe_show = sanitize_filename(show_title).replace(' ', '.')
    # Mehrfache Punkte reduzieren
    safe_show = re.sub(r'\.{2,}', '.', safe_show)
    return f"{safe_show}.S{season:02d}E{episode:02d}.strm"


# ============================================================
# HAUPTFUNKTION
# ============================================================

def create_strm_files(discdb_url, disc_path):
    """
    Hauptfunktion: Erstellt .strm Files aus einer discdb URL und einem Disc-Pfad.

    Gibt eine Liste der erstellten Dateipfade zurück.
    """
    print()
    print("=" * 60)
    print("  DiscDB STRM Creator")
    print("=" * 60)
    print(f"  URL:  {discdb_url}")
    print(f"  Disc: {disc_path}")
    print("=" * 60)
    print()

    # 1. URL parsen
    series_slug, release_slug, disc_slug = parse_discdb_url(discdb_url)
    print(f"  Serie:    {series_slug}")
    print(f"  Release:  {release_slug}")
    print(f"  Disc:     {disc_slug}")
    print()

    # 2. GraphQL abfragen
    print("  Abfrage thediscdb.com API...")
    data = query_graphql(series_slug, release_slug, disc_slug)

    # Fehlerbehandlung
    if 'errors' in data:
        errors = '; '.join(e.get('message', str(e)) for e in data['errors'])
        raise RuntimeError(f"GraphQL Fehler: {errors}")

    # 3. Disc-Daten extrahieren
    media_nodes = (data.get('data') or {}).get('mediaItems', {}).get('nodes', [])
    if not media_nodes:
        raise ValueError(
            f"Keine Daten für '{series_slug}' gefunden.\n"
            "Prüfe ob der Serie-Slug in der URL korrekt ist."
        )

    media_item  = media_nodes[0]
    show_title  = media_item['title']
    show_year   = str(media_item.get('year', '') or '')

    releases = media_item.get('releases') or []
    if not releases:
        raise ValueError(f"Release '{release_slug}' nicht gefunden.")

    disc_nodes = releases[0].get('discs') or []
    if not disc_nodes:
        raise ValueError(f"Disc '{disc_slug}' nicht gefunden.")

    disc        = disc_nodes[0]
    disc_format = (disc.get('format') or 'BD').upper()   # "UHD" oder "BD"
    titles      = disc.get('titles') or []

    print(f"  Show:     {show_title} ({show_year})")
    print(f"  Format:   {disc_format}")
    print(f"  Titles:   {len(titles)} gefunden")
    print()

    # 4. Nur Episoden filtern (kein Menü, Trailer etc.)
    if EPISODES_ONLY:
        episodes = [
            t for t in titles
            if t.get('itemType') == 'Episode'
            and t.get('season')
            and t.get('episode')
            and t.get('sourceFile')
        ]
        if not episodes:
            # Fallback: Alle Titles mit sourceFile nehmen
            print("  WARNUNG: Keine itemType='Episode' Einträge - zeige alle Titles:")
            episodes = [t for t in titles if t.get('sourceFile')]
    else:
        episodes = [t for t in titles if t.get('sourceFile')]

    if not episodes:
        raise ValueError("Keine abspielbaren Titel auf dieser Disc gefunden.")

    print(f"  Episoden: {len(episodes)}")
    print()

    # 5. Ausgabe-Ordner bestimmen
    output_base = UHD_STRM_OUTPUT if disc_format == 'UHD' else BD_STRM_OUTPUT

    if ORGANIZE_BY_SHOW:
        folder_name = sanitize_filename(
            f"{show_title} ({show_year})" if show_year else show_title
        )
        output_folder = os.path.join(output_base, folder_name)
    else:
        output_folder = output_base

    os.makedirs(output_folder, exist_ok=True)

    # 6. .strm Files erstellen
    created = []
    skipped = []

    print(f"  Erstelle .strm Files in:")
    print(f"  {output_folder}")
    print()

    for title_entry in sorted(episodes, key=lambda t: (
        int(t.get('season') or 0),
        int(t.get('episode') or 0)
    )):
        mpls_file   = title_entry['sourceFile']
        ep_desc     = title_entry.get('description') or ''
        item_type   = title_entry.get('itemType') or 'Unknown'

        try:
            season  = int(title_entry['season'])
            episode = int(title_entry['episode'])
        except (TypeError, ValueError):
            print(f"  SKIP  {mpls_file:<16} (Season/Episode nicht parsebar)")
            skipped.append(mpls_file)
            continue

        # STRM-Inhalt bauen
        strm_content = build_strm_content(disc_path, mpls_file)

        # Dateiname bauen
        strm_filename = build_strm_filename(show_title, season, episode)
        strm_path = os.path.join(output_folder, strm_filename)

        # Schreiben
        with open(strm_path, 'w', encoding='utf-8') as f:
            f.write(strm_content)

        ep_label = f"S{season:02d}E{episode:02d}"
        print(f"  OK    {mpls_file:<16} -> {ep_label}  {ep_desc}")
        print(f"        {strm_content}")
        print()
        created.append(strm_path)

    # 7. Zusammenfassung
    print("=" * 60)
    print(f"  Fertig! {len(created)} .strm File(s) erstellt")
    if skipped:
        print(f"  Übersprungen: {len(skipped)}")
    print(f"  Ausgabe: {output_folder}")
    print("=" * 60)
    print()

    return created


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    if len(sys.argv) < 3:
        # Interaktiver Modus wenn keine Argumente
        print(__doc__)
        print()
        print("Keine Argumente angegeben - interaktiver Modus:")
        print()
        discdb_url = input("thediscdb.com URL: ").strip()
        disc_path  = input("Disc Pfad (BDMV-Ordner oder .iso): ").strip()
        # Anführungszeichen entfernen falls vorhanden
        disc_path = disc_path.strip('"').strip("'")
    else:
        discdb_url = sys.argv[1].strip()
        disc_path  = sys.argv[2].strip().strip('"').strip("'")

    if not discdb_url or not disc_path:
        print("Fehler: URL und Disc-Pfad sind erforderlich.")
        sys.exit(1)

    try:
        create_strm_files(discdb_url, disc_path)
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        sys.exit(0)
    except Exception as e:
        print(f"\nFEHLER: {e}")
        import traceback
        traceback.print_exc()
        input("\nDrücke Enter zum Beenden...")
        sys.exit(1)

    if len(sys.argv) < 3:
        # Interaktiver Modus: warten bevor Fenster schliesst
        input("\nDrücke Enter zum Beenden...")


if __name__ == '__main__':
    main()
