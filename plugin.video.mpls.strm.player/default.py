import sys
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs
from urllib.parse import urlencode, parse_qsl
import os

# Get addon info
addon = xbmcaddon.Addon()
addon_id = addon.getAddonInfo('id')
addon_name = addon.getAddonInfo('name')

# Get the plugin handle
handle = int(sys.argv[1])

def log(msg):
    xbmc.log(f'[{addon_name}] {msg}', xbmc.LOGINFO)

def get_url(**kwargs):
    """Create a URL for calling the plugin recursively"""
    return f'{sys.argv[0]}?{urlencode(kwargs)}'

def read_strm_file(strm_path):
    """Read the content of a .strm file and return the URL"""
    try:
        with xbmcvfs.File(strm_path, 'r') as f:
            content = f.read()
            # Clean up the content
            url = content.strip()
            log(f'Read .strm: {strm_path} -> {url}')
            return url
    except Exception as e:
        log(f'Error reading .strm file {strm_path}: {str(e)}')
        return None

def find_strm_files(folder_path):
    """Recursively find all .strm files in a folder"""
    strm_files = []
    
    try:
        dirs, files = xbmcvfs.listdir(folder_path)
        
        # Process files in current directory
        for filename in files:
            if filename.lower().endswith('.strm'):
                full_path = os.path.join(folder_path, filename)
                strm_files.append(full_path)
        
        # Recursively process subdirectories
        for dirname in dirs:
            subdir_path = os.path.join(folder_path, dirname)
            strm_files.extend(find_strm_files(subdir_path))
                
    except Exception as e:
        log(f'Error scanning folder {folder_path}: {str(e)}')
    
    return strm_files

def list_videos(folder_path):
    """List all .strm files in the specified folder"""
    xbmcplugin.setContent(handle, 'movies')
    
    log(f'Scanning folder: {folder_path}')
    
    strm_files = find_strm_files(folder_path)
    log(f'Found {len(strm_files)} .strm files')
    
    for strm_path in strm_files:
        # Get the filename without extension
        filename = os.path.basename(strm_path)
        title = os.path.splitext(filename)[0]
        
        # Read the .strm content
        mpls_url = read_strm_file(strm_path)
        
        if not mpls_url:
            continue
        
        # Create list item
        list_item = xbmcgui.ListItem(label=title)
        list_item.setInfo('video', {'title': title, 'mediatype': 'movie'})
        list_item.setProperty('IsPlayable', 'true')
        
        # Create URL for playback
        url = get_url(action='play', url=mpls_url, title=title)
        
        # Add to directory
        xbmcplugin.addDirectoryItem(handle, url, list_item, False)
    
    xbmcplugin.endOfDirectory(handle)

def play_video(url, title):
    """Play the video at the specified URL"""
    log(f'Playing: {title} -> {url}')
    
    # Create a playable item
    play_item = xbmcgui.ListItem(path=url)
    play_item.setInfo('video', {'title': title})
    
    # Play the item
    xbmcplugin.setResolvedUrl(handle, True, listitem=play_item)

def router(paramstring):
    """Router function that calls other functions depending on provided paramstring"""
    params = dict(parse_qsl(paramstring))
    
    if not params:
        # No parameters - show settings or folder selection
        folder_path = addon.getSetting('strm_folder')
        
        if not folder_path:
            xbmcgui.Dialog().ok(addon_name, 
                'Please configure the .strm folder in addon settings!')
            addon.openSettings()
            return
        
        list_videos(folder_path)
    
    elif params['action'] == 'play':
        # Play the video
        play_video(params['url'], params.get('title', 'Unknown'))

if __name__ == '__main__':
    router(sys.argv[2][1:])  # Trim the leading '?' from the query string
