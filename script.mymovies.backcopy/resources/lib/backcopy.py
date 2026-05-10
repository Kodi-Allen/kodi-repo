import json
import sys
import traceback

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs


ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name")

SOURCE_FILENAME = "mymovies-back.jpg"
TARGET_FILENAME = "back.jpg"
PAGE_SIZE = 1000
RUNNING_PROPERTY = "{}.running".format(ADDON_ID)
SKIP_DIRECTORY_NAMES = (
    "@eadir",
    "__pycache__",
    ".git",
    ".svn",
    ".appledouble",
    "certificate",
)
DISC_DIRECTORY_NAMES = (
    "bdmv",
    "video_ts",
)
DISC_MARKER_FILES = (
    "index.bdmv",
    "movieobject.bdmv",
    "video_ts.ifo",
)
MEDIA_EXTENSIONS = (
    ".iso",
    ".strm",
    ".mkv",
    ".mp4",
    ".avi",
    ".m2ts",
    ".mts",
    ".ts",
    ".mov",
    ".wmv",
    ".mpg",
    ".mpeg",
)


class SilentProgress:
    def create(self, heading, message=""):
        return None

    def update(self, percent, message=""):
        return None

    def close(self):
        return None

    def iscanceled(self):
        return False


def log(message, level=xbmc.LOGINFO):
    xbmc.log("[{}] {}".format(ADDON_ID, message), level)


def current_addon():
    return xbmcaddon.Addon(ADDON_ID)


def setting_bool(setting_id, default=False):
    addon = current_addon()
    try:
        return addon.getSettingBool(setting_id)
    except AttributeError:
        value = addon.getSetting(setting_id)
        if value == "":
            return default
        return value.lower() == "true"


def setting_int(setting_id, default=0):
    addon = current_addon()
    try:
        return addon.getSettingInt(setting_id)
    except AttributeError:
        value = addon.getSetting(setting_id)
        if value == "":
            return default
        try:
            return int(float(value))
        except ValueError:
            return default


def arg_bool(name, default):
    prefix = "{}=".format(name)
    for arg in sys.argv[1:]:
        if arg.lower().startswith(prefix):
            value = arg[len(prefix):].strip().lower()
            return value in ("1", "true", "yes", "on")
    return default


def arg_bool_optional(name):
    prefix = "{}=".format(name)
    for arg in sys.argv[1:]:
        if arg.lower().startswith(prefix):
            value = arg[len(prefix):].strip().lower()
            return value in ("1", "true", "yes", "on")
    return None


def get_renew_existing():
    renew_arg = arg_bool_optional("renew")
    if renew_arg is not None:
        return renew_arg

    overwrite_arg = arg_bool_optional("overwrite")
    if overwrite_arg is not None:
        return overwrite_arg

    return setting_bool("renew_existing", False)


def json_rpc(method, params=None):
    request = {
        "jsonrpc": "2.0",
        "id": ADDON_ID,
        "method": method,
    }
    if params is not None:
        request["params"] = params

    raw_response = xbmc.executeJSONRPC(json.dumps(request))
    try:
        response = json.loads(raw_response)
    except ValueError as exc:
        raise RuntimeError("{} returned invalid JSON: {}".format(method, exc))

    if "error" in response:
        raise RuntimeError("{} failed: {}".format(method, response["error"]))

    return response.get("result", {})


def fetch_library_items(method, result_key, properties):
    items = []
    start = 0

    while True:
        result = json_rpc(
            method,
            {
                "properties": properties,
                "limits": {"start": start, "end": start + PAGE_SIZE},
            },
        )

        batch = result.get(result_key, [])
        if not batch:
            break

        items.extend(batch)
        limits = result.get("limits", {})
        total = limits.get("total", len(items))
        if len(items) >= total:
            break

        start += PAGE_SIZE

    return items


def has_scheme(path):
    return "://" in path


def is_absolute_path(path):
    if not path:
        return False
    return has_scheme(path) or path.startswith("\\\\") or (len(path) >= 2 and path[1] == ":")


def trailing_separator(path):
    if "\\" in path and "/" not in path:
        return "\\"
    return "/"


def ensure_dir_path(path):
    if not path:
        return ""
    if path.endswith(("/", "\\")):
        return path
    return path + trailing_separator(path)


def parent_path(path):
    if not path:
        return ""

    stripped = path.rstrip("/\\")
    slash = stripped.rfind("/")
    backslash = stripped.rfind("\\")
    index = max(slash, backslash)
    if index < 0:
        return ""

    return stripped[: index + 1]


def library_art_root(path):
    if not path:
        return ""

    stripped = path.rstrip("/\\")
    item_name = basename(stripped).lower()

    if item_name in DISC_MARKER_FILES:
        disc_dir = parent_path(stripped)
        if basename(disc_dir).lower() in DISC_DIRECTORY_NAMES:
            return parent_path(disc_dir)
        return disc_dir

    if item_name in DISC_DIRECTORY_NAMES:
        return parent_path(stripped)

    if path.endswith(("/", "\\")):
        return ensure_dir_path(path)

    return parent_path(path)


def join_path(parent, child):
    if not parent:
        return child
    if is_absolute_path(child):
        return child
    if parent.endswith(("/", "\\")):
        return parent + child
    return parent + trailing_separator(parent) + child


def basename(path):
    return path.rstrip("/\\").replace("\\", "/").split("/")[-1]


def lowercase_names(items):
    return set(basename(item).lower() for item in items)


def compare_path(path):
    return ensure_dir_path(path).replace("\\", "/").lower()


def should_skip_directory(directory):
    return basename(directory).lower() in SKIP_DIRECTORY_NAMES


def has_media_file(files):
    for item in files:
        name = basename(item).lower()
        if name.endswith(MEDIA_EXTENSIONS):
            return True
    return False


def is_disc_boundary(folder, dirs, files):
    folder_name = basename(folder).lower()
    dir_names = lowercase_names(dirs)
    file_names = lowercase_names(files)

    return (
        folder_name in DISC_DIRECTORY_NAMES
        or bool(dir_names.intersection(DISC_DIRECTORY_NAMES))
        or bool(file_names.intersection(DISC_MARKER_FILES))
        or has_media_file(files)
    )


def compact_roots(paths):
    roots = []
    seen = set()

    for path in sorted(paths, key=lambda value: len(compare_path(value))):
        key = compare_path(path)
        if not key or key in seen:
            continue

        if any(key.startswith(parent_key) for parent_key in seen):
            continue

        seen.add(key)
        roots.append(ensure_dir_path(path))

    return roots


def collect_video_library_roots(progress):
    roots = []

    progress.update(1, "Reading movies from video library...")
    movies = fetch_library_items("VideoLibrary.GetMovies", "movies", ["file"])
    for movie in movies:
        movie_file = movie.get("file", "")
        movie_dir = library_art_root(movie_file)
        if movie_dir:
            roots.append(movie_dir)

    progress.update(3, "Reading TV shows from video library...")
    tvshows = fetch_library_items("VideoLibrary.GetTVShows", "tvshows", ["file"])
    for tvshow in tvshows:
        tvshow_dir = tvshow.get("file", "")
        if tvshow_dir:
            roots.append(ensure_dir_path(tvshow_dir))

    progress.update(5, "Reading TV episodes from video library...")
    episodes = fetch_library_items("VideoLibrary.GetEpisodes", "episodes", ["file"])
    for episode in episodes:
        episode_file = episode.get("file", "")
        episode_dir = parent_path(episode_file)
        if episode_dir:
            roots.append(episode_dir)

    return compact_roots(roots)


def update_progress(progress, percent, stats, current_path):
    message = "Folders: {folders} | Found: {found} | Copied: {copied} | Skipped: {skipped} | Errors: {errors}\n{path}".format(
        folders=stats["folders"],
        found=stats["found"],
        copied=stats["copied"],
        skipped=stats["skipped"],
        errors=stats["errors"],
        path=current_path,
    )
    progress.update(percent, message)


def copy_back_art(source_path, target_path, renew, stats):
    stats["found"] += 1

    if xbmcvfs.exists(target_path):
        if not renew:
            stats["skipped"] += 1
            log("Skipped existing target: {}".format(target_path))
            return

        if not xbmcvfs.delete(target_path):
            stats["errors"] += 1
            log("Could not delete existing target: {}".format(target_path), xbmc.LOGERROR)
            return

    if xbmcvfs.copy(source_path, target_path):
        stats["copied"] += 1
        log("Copied {} to {}".format(source_path, target_path))
        return

    stats["errors"] += 1
    log("Copy failed: {} to {}".format(source_path, target_path), xbmc.LOGERROR)


def handle_files(folder, files, renew, stats):
    source_items = [item for item in files if basename(item).lower() == SOURCE_FILENAME]
    if not source_items:
        return

    source_path = join_path(folder, source_items[0])
    target_path = join_path(folder, TARGET_FILENAME)
    copy_back_art(source_path, target_path, renew, stats)


def scan_root(root, root_index, root_count, progress, renew, visited, stats):
    stack = [ensure_dir_path(root)]

    while stack:
        if progress.iscanceled():
            return False

        folder = ensure_dir_path(stack.pop())
        folder_key = compare_path(folder)
        if not folder_key or folder_key in visited:
            continue

        visited.add(folder_key)
        stats["folders"] += 1

        percent = 5 + int((root_index / float(max(root_count, 1))) * 94)
        if stats["folders"] == 1 or stats["folders"] % 25 == 0:
            update_progress(progress, percent, stats, folder)

        try:
            dirs, files = xbmcvfs.listdir(folder)
        except Exception:
            stats["errors"] += 1
            log("Could not list folder: {}\n{}".format(folder, traceback.format_exc()), xbmc.LOGERROR)
            continue

        target_exists = xbmcvfs.exists(join_path(folder, TARGET_FILENAME))
        if target_exists and not renew:
            stats["skipped"] += 1
            log("Skipped folder with existing target: {}".format(folder))
        else:
            handle_files(folder, files, renew, stats)

        if is_disc_boundary(folder, dirs, files):
            continue

        for directory in dirs:
            if should_skip_directory(directory):
                continue
            stack.append(ensure_dir_path(join_path(folder, directory)))

    return True


def trigger_video_library_scan():
    xbmc.executebuiltin("UpdateLibrary(video)")
    log("Video library scan triggered")


def acquire_run_lock(source):
    window = xbmcgui.Window(10000)
    current = window.getProperty(RUNNING_PROPERTY)
    if current:
        log("Skipped {} run because another run is active: {}".format(source, current))
        return False

    window.setProperty(RUNNING_PROPERTY, source)
    return True


def release_run_lock():
    xbmcgui.Window(10000).clearProperty(RUNNING_PROPERTY)


def build_summary(stats, library_scan_started):
    message = (
        "Scan finished.\n"
        "Folders scanned: {folders}\n"
        "mymovies-back.jpg found: {found}\n"
        "back.jpg copied: {copied}\n"
        "Skipped existing back.jpg: {skipped}\n"
        "Errors: {errors}\n"
        "Video library scan: {library_scan}"
    )
    return message.format(
        folders=stats["folders"],
        found=stats["found"],
        copied=stats["copied"],
        skipped=stats["skipped"],
        errors=stats["errors"],
        library_scan="started" if library_scan_started else "not started",
    )


def run_backcopy(show_dialog=True, show_summary=True, source="manual"):
    if not acquire_run_lock(source):
        if show_dialog:
            xbmcgui.Dialog().notification(
                ADDON_NAME,
                "A scan is already running.",
                xbmcgui.NOTIFICATION_WARNING,
            )
        return None

    renew = get_renew_existing()
    run_library_scan = arg_bool("scan_library", setting_bool("run_library_scan", True))
    progress = xbmcgui.DialogProgress() if show_dialog else SilentProgress()
    progress_open = False
    library_scan_started = False
    stats = {
        "folders": 0,
        "found": 0,
        "copied": 0,
        "skipped": 0,
        "errors": 0,
    }

    progress.create(ADDON_NAME, "Preparing scan...")
    progress_open = True
    try:
        roots = collect_video_library_roots(progress)
        if not roots:
            progress.close()
            progress_open = False
            if show_dialog:
                xbmcgui.Dialog().ok(ADDON_NAME, "No movie or TV show folders found in the video library.")
            log("No movie or TV show folders found in the video library")
            return stats

        log("Scanning {} compacted video library roots. renew={}".format(len(roots), renew))
        visited = set()
        for index, root in enumerate(roots):
            if not scan_root(root, index, len(roots), progress, renew, visited, stats):
                progress.close()
                progress_open = False
                if show_dialog:
                    xbmcgui.Dialog().notification(ADDON_NAME, "Scan canceled.", xbmcgui.NOTIFICATION_WARNING)
                log("Scan canceled")
                return stats

        if run_library_scan:
            progress.update(100, "Starting video library scan...")
            trigger_video_library_scan()
            library_scan_started = True
        else:
            progress.update(100, "Finished.")

        message = build_summary(stats, library_scan_started)
        progress.close()
        progress_open = False
        if show_summary and show_dialog:
            xbmcgui.Dialog().ok(ADDON_NAME, message)
        elif show_dialog:
            xbmcgui.Dialog().notification(ADDON_NAME, "Scan finished.", xbmcgui.NOTIFICATION_INFO)
        log(message.replace("\n", " | "))
        return stats
    except Exception as exc:
        log(traceback.format_exc(), xbmc.LOGERROR)
        if progress_open:
            progress.close()
            progress_open = False
        if show_dialog:
            xbmcgui.Dialog().ok(ADDON_NAME, "Error: {}".format(exc))
        return None
    finally:
        if progress_open:
            progress.close()
        release_run_lock()


def run_manual():
    return run_backcopy(show_dialog=True, show_summary=True, source="manual")


def run_scheduled():
    log("Scheduled run started")
    return run_backcopy(show_dialog=False, show_summary=False, source="scheduled")
