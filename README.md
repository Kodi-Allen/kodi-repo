# Kodi Allen Repository

Kodi Omega (v21) compatible add-on repository.

## ðŸ“¦ Installation

### Method 1: Via ZIP File (Recommended)

1. **Download the repository ZIP:**
   - Go to [Releases](https://github.com/Kodi-Allen/kodi-repo/releases)
   - Download `repository.kodiallen-1.0.0.zip`

2. **Install in Kodi:**
   - Open Kodi
   - Go to: **Settings** â†’ **Add-ons** â†’ **Install from zip file**
   - Select the downloaded `repository.kodiallen-1.0.0.zip`
   - Wait for confirmation

3. **Install add-ons:**
   - Go to: **Settings** â†’ **Add-ons** â†’ **Install from repository**
   - Select **Kodi Allen Repository**
   - Choose your desired add-on and install

### Method 2: Direct Download

You can also download individual add-ons directly:

1. Go to the add-on folder (e.g. `script.artwork.beef/`)
2. Download the ZIP file
3. Install via: **Settings** â†’ **Add-ons** â†’ **Install from zip file**

---

## ðŸ“‹ Available Add-ons

### Script: Artwork Beef (v0.28.6)
**Automatic artwork management for your Kodi library**

- âœ… Kodi Omega (v21) compatible
- âœ… Fully migrated to Python 3
- âœ… All GUI dialogs working
- âœ… Supports: fanart.tv, TheTVDB.com, The Movie Database, TheAudioDB

**Features:**
- Automatic artwork download for movies, TV shows and music
- Manual artwork selection with GUI
- Context menu integration (right-click menu)
- Background service for automatic updates
- Local artwork caching

**Installation:** Via repository or [direct download](script.artwork.beef/script.artwork.beef-0.28.6.zip)

---

## ðŸ› ï¸ For Developers

### Updating the Repository

To add or update an add-on:

1. **Add an add-on:**
   ```bash
   # Copy your addon directory into the repository
   cp -r /path/to/script.myaddon ./
   ```

2. **Generate repository:**
   ```bash
   cd tools
   python3 generate_repo.py
   ```

3. **Push to GitHub:**
   ```bash
   git add .
   git commit -m "Add/Update: script.myaddon v1.0.0"
   git push
   ```

### Repository Structure

```
kodi-repo/
â”œâ”€â”€ repository.kodiallen/        # Repository add-on
â”‚   â”œâ”€â”€ addon.xml
â”‚   â”œâ”€â”€ icon.png
â”‚   â””â”€â”€ fanart.jpg
â”œâ”€â”€ script.artwork.beef/         # Example add-on
â”‚   â”œâ”€â”€ addon.xml
â”‚   â”œâ”€â”€ icon.png
â”‚   â”œâ”€â”€ changelog.txt
â”‚   â”œâ”€â”€ ... (all addon files)
â”‚   â””â”€â”€ script.artwork.beef-0.28.6.zip  # Auto-generated
â”œâ”€â”€ addons.xml                   # Index of all add-ons (auto-generated)
â”œâ”€â”€ addons.xml.md5               # Checksum (auto-generated)
â”œâ”€â”€ tools/
â”‚   â””â”€â”€ generate_repo.py         # Generator script
â””â”€â”€ README.md
```

### Creating ZIP Files

The `generate_repo.py` script automatically creates:
- ZIP files for each add-on
- `addons.xml` index
- `addons.xml.md5` checksum

**Important:** Run the script after every change!

---

## ðŸ“ Adding an Add-on

### Requirements
- Add-on must have a valid `addon.xml`
- Add-on ID should be unique
- Must be Kodi Omega (v21) compatible

### Steps

1. **Create add-on folder:**
   ```
   script.myaddon/
   â”œâ”€â”€ addon.xml
   â”œâ”€â”€ icon.png (512x512 recommended)
   â”œâ”€â”€ fanart.jpg (1920x1080 recommended)
   â”œâ”€â”€ changelog.txt
   â”œâ”€â”€ LICENSE.txt
   â””â”€â”€ ... (other files)
   ```

2. **addon.xml example:**
   ```xml
   <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
   <addon id="script.myaddon" name="My Add-on" version="1.0.0" provider-name="Your Name">
       <requires>
           <import addon="xbmc.python" version="3.0.1"/>
       </requires>
       <extension point="xbmc.python.script" library="default.py">
           <provides>executable</provides>
       </extension>
       <extension point="xbmc.addon.metadata">
           <summary lang="en">Short description</summary>
           <description lang="en">Detailed description</description>
           <platform>all</platform>
           <license>GPL-3.0</license>
           <source>https://github.com/Kodi-Allen/kodi-repo</source>
           <assets>
               <icon>icon.png</icon>
               <fanart>fanart.jpg</fanart>
           </assets>
       </extension>
   </addon>
   ```

3. **Regenerate repository:**
   ```bash
   cd tools
   python3 generate_repo.py
   ```

4. **Commit and push:**
   ```bash
   git add .
   git commit -m "Add: script.myaddon v1.0.0"
   git push
   ```

---

## ðŸ”„ Updating an Add-on

1. Update files in your add-on folder
2. Increase version number in `addon.xml`
3. Update `changelog.txt`
4. Run `python3 tools/generate_repo.py`
5. Commit and push changes

Kodi will detect updates automatically!

---

## ðŸ†˜ Support

For issues or questions:
- Open an [Issue](https://github.com/Kodi-Allen/kodi-repo/issues)
- Visit the Kodi Forum

---

## ðŸ“œ License

Each add-on has its own license. See the respective LICENSE.txt files.

The repository framework is available under MIT License.

---

## ðŸ™ Credits

- **Artwork Beef:** Based on [script.artwork.beef](https://github.com/rmrector/script.artwork.beef) by rmrector
- **Repository Framework:** Inspired by the Kodi community
- **Maintainer:** Kodi Allen

---

## âš ï¸ Disclaimer

These add-ons are community ports for Kodi Omega. Use at your own risk.
For issues, please create an issue in this repository.

---

**Enjoy your add-ons! ðŸŽ‰**
