import xbmc
import xbmcaddon
import xbmcvfs
import xbmcgui
import os
import time

addon = xbmcaddon.Addon()

def show_notification(message, time=2000):
    """Show notification only if enabled in settings"""
    if addon.getSetting('show_notifications') == 'true':
        xbmc.executebuiltin(f'Notification(STRM Fixer, {message}, {time})')

def log(msg):
    xbmc.log(f'[STRM Fixer v3] {msg}', xbmc.LOGINFO)

def get_strm_folders():
    """Get all configured .strm folders"""
    folders = []
    for i in range(1, 11):  # Support up to 10 folders
        folder = addon.getSetting(f'strm_folder{i}')
        if folder and folder.strip():
            folders.append(folder.strip())
    
    # Backwards compatibility: check old setting name
    old_folder = addon.getSetting('strm_folder')
    if old_folder and old_folder.strip() and old_folder not in folders:
        folders.append(old_folder.strip())
    
    return folders

def find_strm_by_title(title, season, episode):
    """Find .strm file by show title, season, and episode number"""
    strm_folders = get_strm_folders()
    if not strm_folders:
        log('No .strm folders configured!')
        return None
    
    log(f'Looking for: Title="{title}" S{season:02d}E{episode:02d}')
    log(f'Searching in {len(strm_folders)} folder(s)')
    
    # Normalize title for matching
    title_normalized = title.lower().strip()
    
    def search_dir(path):
        try:
            dirs, files = xbmcvfs.listdir(path)
            
            # Get current directory name
            current_dir = os.path.basename(path).lower()
            
            # Check if current directory matches show title
            # (e.g. "Aquarius (2015)" contains "aquarius")
            title_match = title_normalized in current_dir
            
            for filename in files:
                if filename.lower().endswith('.strm'):
                    filename_lower = filename.lower()
                    
                    # Check if filename contains the episode pattern
                    if f's{season:02d}e{episode:02d}' in filename_lower or f's{season}e{episode}' in filename_lower:
                        
                        # CRITICAL: Only accept if we're in the right show folder!
                        if not title_match:
                            # Check if title is in the full path
                            full_path_lower = path.lower()
                            if title_normalized not in full_path_lower:
                                log(f'⚠️ Skipping {filename} - wrong show folder!')
                                continue
                        
                        strm_path = os.path.join(path, filename)
                        
                        # Read .strm content
                        try:
                            with xbmcvfs.File(strm_path, 'r') as f:
                                content = f.read().strip()
                                log(f'✓ FOUND: {strm_path}')
                                log(f'  Content: {content}')
                                return strm_path, content
                        except Exception as e:
                            log(f'Error reading {strm_path}: {str(e)}')
            
            # Search subdirectories
            for dirname in dirs:
                result = search_dir(os.path.join(path, dirname))
                if result:
                    return result
        except Exception as e:
            log(f'Error scanning {path}: {str(e)}')
        
        return None
    
    # Search all configured folders
    for folder in strm_folders:
        log(f'Searching in: {folder}')
        result = search_dir(folder)
        if result:
            return result
    
    log(f'⚠️ Could not find .strm in any configured folder!')
    return None

class UniversalSTRMFixer(xbmc.Player):
    def __init__(self):
        xbmc.Player.__init__(self)
        self.fixing_playback = False
        self.last_fixed_url = None
        log('STRM Fixer v3 initialized - using Library metadata!')
    
    def onAVStarted(self):
        """Called when playback starts"""
        if self.fixing_playback:
            log('Already fixing - ignoring')
            return
        
        try:
            time.sleep(0.3)
            
            if not self.isPlaying():
                return
            
            playing_file = self.getPlayingFile()
            log(f'Playback started: {playing_file}')
            
            # If this is what we just fixed, ignore
            if playing_file == self.last_fixed_url:
                log('✅ This is our corrected playback - done!')
                self.last_fixed_url = None
                return
            
            # If playing .strm directly, no fix needed
            if playing_file.lower().endswith('.strm'):
                log('✅ Playing .strm directly - OK!')
                return
            
            # Get Library metadata
            try:
                # Try to get episode info from Kodi
                title = xbmc.getInfoLabel('VideoPlayer.TVShowTitle')
                season = xbmc.getInfoLabel('VideoPlayer.Season')
                episode = xbmc.getInfoLabel('VideoPlayer.Episode')
                
                log(f'Library Info: Title="{title}" Season={season} Episode={episode}')
                
                if not title or not season or not episode:
                    log('No TV show metadata - not a Library TV show playback')
                    return
                
                season = int(season)
                episode = int(episode)
                
                # Find the .strm that should be playing
                result = find_strm_by_title(title, season, episode)
                
                if not result:
                    log(f'⚠️ Could not find .strm for {title} S{season:02d}E{episode:02d}')
                    return
                
                strm_path, strm_content = result
                log(f'✓ Found .strm: {strm_path}')
                log(f'✓ Will play: {strm_content}')
                
                # ALWAYS play what's in the .strm - no comparison needed!
                log('🔄 Replacing Library playback with .strm content...')
                
                self.fixing_playback = True
                self.last_fixed_url = strm_content
                
                show_notification('Playing from .strm...')
                
                self.stop()
                time.sleep(1.0)
                
                log(f'▶️ Playing: {strm_content}')
                
                play_item = xbmcgui.ListItem(path=strm_content)
                xbmc.Player().play(strm_content, play_item)
                
                show_notification('Playing correct file!')
                
                time.sleep(2)
                self.fixing_playback = False
                    
            except ValueError as e:
                log(f'Could not parse season/episode: {e}')
                return
            
        except Exception as e:
            log(f'💥 ERROR: {str(e)}')
            import traceback
            log(traceback.format_exc())
            self.fixing_playback = False
    
    def onPlayBackStarted(self):
        """Backup trigger"""
        self.onAVStarted()

if __name__ == '__main__':
    monitor = xbmc.Monitor()
    player = UniversalSTRMFixer()
    
    log('STRM Fixer v3 started - using Library metadata!')
    show_notification('Service running', 3000)
    
    while not monitor.abortRequested():
        if monitor.waitForAbort(1):
            break
    
    log('Service stopped')
