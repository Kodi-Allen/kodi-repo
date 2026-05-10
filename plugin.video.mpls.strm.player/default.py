import sys
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs
from urllib.parse import urlencode, parse_qsl

addon = xbmcaddon.Addon()
addon_id = addon.getAddonInfo('id')
addon_name = addon.getAddonInfo('name')
handle = int(sys.argv[1])


def log(msg):
    xbmc.log(f'[{addon_name}] {msg}', xbmc.LOGINFO)


def get_url(**kwargs):
    return f'{sys.argv[0]}?{urlencode(kwargs)}'


# ============================================================
# MAIN MENU
# ============================================================

def show_main_menu():
    """Show the main menu."""

    # Browse STRM Files
    li = xbmcgui.ListItem(label='Browse STRM Files')
    li.setArt({'icon': 'DefaultFolder.png'})
    xbmcplugin.addDirectoryItem(handle, get_url(action='browse'), li, True)

    # STRM Creator submenu
    li = xbmcgui.ListItem(label='STRM Creator')
    li.setArt({'icon': 'DefaultAddSource.png'})
    xbmcplugin.addDirectoryItem(handle, get_url(action='creator_menu'), li, True)

    xbmcplugin.endOfDirectory(handle)


def show_creator_menu():
    """Show the STRM Creator submenu."""

    li = xbmcgui.ListItem(label='Create from EAN / UPC (auto-scan all discs)')
    li.setArt({'icon': 'DefaultAddSource.png'})
    xbmcplugin.addDirectoryItem(handle, get_url(action='creator_upc'), li, False)

    li = xbmcgui.ListItem(label='Create from thediscdb.com URL (single disc)')
    li.setArt({'icon': 'DefaultAddSource.png'})
    xbmcplugin.addDirectoryItem(handle, get_url(action='creator_url'), li, False)

    xbmcplugin.endOfDirectory(handle)


# ============================================================
# BROWSE STRM FILES
# ============================================================

def get_strm_folders():
    """Get configured STRM folders from settings."""
    folders = []
    for i in range(1, 6):
        folder = addon.getSetting(f'strm_folder{i}')
        if folder and folder.strip():
            folders.append(folder.strip())
    return folders


def find_strm_files(folder_path):
    """Recursively find all .strm files in a folder."""
    strm_files = []
    folder_path = folder_path.rstrip('/') + '/'
    try:
        dirs, files = xbmcvfs.listdir(folder_path)
        for filename in files:
            if filename.lower().endswith('.strm'):
                strm_files.append(f"{folder_path}{filename}")
        for dirname in dirs:
            strm_files.extend(find_strm_files(f"{folder_path}{dirname}"))
    except Exception as e:
        log(f'Error scanning {folder_path}: {e}')
    return strm_files


def browse_strm_files():
    """List all .strm files from configured folders."""
    folders = get_strm_folders()

    if not folders:
        xbmcgui.Dialog().ok(addon_name,
            'No STRM folders configured. Please set them in addon settings.')
        addon.openSettings()
        return

    xbmcplugin.setContent(handle, 'movies')

    for folder in folders:
        for strm_path in find_strm_files(folder):
            # Extract filename
            title = strm_path.rsplit('/', 1)[-1]
            if title.lower().endswith('.strm'):
                title = title[:-5]

            try:
                f = xbmcvfs.File(strm_path, 'r')
                strm_url = f.read().strip()
                f.close()
            except Exception:
                continue

            if not strm_url:
                continue

            li = xbmcgui.ListItem(label=title)
            li.setInfo('video', {'title': title, 'mediatype': 'movie'})
            li.setProperty('IsPlayable', 'true')

            url = get_url(action='play', url=strm_url, title=title)
            xbmcplugin.addDirectoryItem(handle, url, li, False)

    xbmcplugin.endOfDirectory(handle)


# ============================================================
# PLAY VIDEO (plugin:// handler)
# ============================================================

def play_video(url, title):
    """Resolve and play a video URL. Called via plugin:// from .strm files."""
    log(f'Playing: {title} -> {url}')
    play_item = xbmcgui.ListItem(path=url)
    play_item.setInfo('video', {'title': title})
    xbmcplugin.setResolvedUrl(handle, True, listitem=play_item)


# ============================================================
# SHARED HELPERS
# ============================================================

def check_output_settings():
    """Check output folder settings. Returns (output_uhd, output_bd) or None."""
    dialog = xbmcgui.Dialog()
    output_uhd = addon.getSetting('strm_output_uhd')
    output_bd = addon.getSetting('strm_output_bd')
    if not output_uhd and not output_bd:
        dialog.ok(addon_name,
            'No output folders configured.',
            'Please set at least one STRM output folder in addon settings.')
        addon.openSettings()
        return None
    return output_uhd, output_bd


def select_output_folder(output_uhd, output_bd):
    """Let user pick UHD or BD output folder. Returns path or None."""
    if output_uhd and output_bd:
        fmt = xbmcgui.Dialog().select('Disc format', ['UHD (4K)', 'Blu-ray (1080p)'])
        if fmt < 0:
            return None
        return output_uhd if fmt == 0 else output_bd
    return output_uhd or output_bd


# ============================================================
# STRM CREATOR - URL MODE (single disc)
# ============================================================

def run_creator_url():
    """Create .strm files from a thediscdb.com URL."""
    dialog = xbmcgui.Dialog()

    outputs = check_output_settings()
    if not outputs:
        return
    output_uhd, output_bd = outputs

    # Step 1: Enter DiscDB URL
    discdb_url = dialog.input(
        'Enter thediscdb.com URL',
        type=xbmcgui.INPUT_ALPHANUM
    )
    if not discdb_url:
        return

    # Step 2: BDMV folder or ISO?
    disc_type = dialog.select('Disc type', ['BDMV Folder', 'ISO File'])
    if disc_type < 0:
        return

    # Step 3: Browse for disc source
    if disc_type == 0:
        disc_path = dialog.browse(0, 'Select BDMV folder', 'video')
    else:
        disc_path = dialog.browse(1, 'Select ISO file', 'video', '.iso')

    if not disc_path:
        return
    disc_path = disc_path.rstrip('/')

    # Step 4: Select output folder
    output_base = select_output_folder(output_uhd, output_bd)
    if not output_base:
        return

    # Step 5: Run
    progress = xbmcgui.DialogProgress()
    progress.create(addon_name, 'Creating STRM files...')

    try:
        from lib.strm_creator import create_strm_files
        created, show_title, output_folder = create_strm_files(
            discdb_url, disc_path, output_base, progress
        )
        progress.close()

        dialog.ok(addon_name,
            f'{len(created)} .strm files created!',
            f'Show: {show_title}',
            f'Output: {output_folder}'
        )

    except Exception as e:
        progress.close()
        log(f'Creator URL error: {e}')
        import traceback
        log(traceback.format_exc())
        dialog.ok(addon_name, f'Error: {str(e)}')


# ============================================================
# STRM CREATOR - UPC/EAN MODE (auto-scan all discs)
# ============================================================

def run_creator_upc():
    """Create .strm files from EAN/UPC — auto-scans folder for all discs."""
    dialog = xbmcgui.Dialog()

    outputs = check_output_settings()
    if not outputs:
        return
    output_uhd, output_bd = outputs

    # Step 1: Enter EAN/UPC
    upc = dialog.input(
        'Enter EAN or UPC barcode number',
        type=xbmcgui.INPUT_ALPHANUM
    )
    if not upc:
        return

    # Step 2: Browse to parent folder containing disc folders/ISOs
    parent_path = dialog.browse(
        0,  # ShowAndGetDirectory
        'Select folder containing the disc folders or ISOs',
        'video'
    )
    if not parent_path:
        return

    # Step 3: Select output folder
    output_base = select_output_folder(output_uhd, output_bd)
    if not output_base:
        return

    # Step 4: Run
    progress = xbmcgui.DialogProgress()
    progress.create(addon_name, 'Scanning discs and creating STRM files...')

    try:
        from lib.strm_creator import create_strm_files_by_upc
        created, show_title, output_folder, matched, total = create_strm_files_by_upc(
            upc, parent_path, output_base, progress
        )
        progress.close()

        dialog.ok(addon_name,
            f'{len(created)} .strm files created!',
            f'Show: {show_title}',
            f'Discs matched: {matched}/{total}',
            f'Output: {output_folder}'
        )

    except Exception as e:
        progress.close()
        log(f'Creator UPC error: {e}')
        import traceback
        log(traceback.format_exc())
        dialog.ok(addon_name, f'Error: {str(e)}')


# ============================================================
# ROUTER
# ============================================================

def router(paramstring):
    params = dict(parse_qsl(paramstring))

    if not params:
        show_main_menu()
    elif params.get('action') == 'browse':
        browse_strm_files()
    elif params.get('action') == 'play':
        play_video(params['url'], params.get('title', 'Unknown'))
    elif params.get('action') == 'creator_menu':
        show_creator_menu()
    elif params.get('action') == 'creator_url':
        run_creator_url()
    elif params.get('action') == 'creator_upc':
        run_creator_upc()


if __name__ == '__main__':
    router(sys.argv[2][1:])
