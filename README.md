# Kodi Allen Repository

Kodi Omega (v21) compatible add-on repository.

## 📦 Installation

### Method 1: Via ZIP File (Recommended)

1. **Download the repository ZIP:**
   - Go to [Releases](https://github.com/kodiallen/kodi-repo/releases)
   - Download `repository.kodiallen-1.0.0.zip`

2. **Install in Kodi:**
   - Open Kodi
   - Go to: **Settings** → **Add-ons** → **Install from zip file**
   - Select the downloaded `repository.kodiallen-1.0.0.zip`
   - Wait for confirmation

3. **Install add-ons:**
   - Go to: **Settings** → **Add-ons** → **Install from repository**
   - Select **Kodi Allen Repository**
   - Choose your desired add-on and install

### Method 2: Direct Download

You can also download individual add-ons directly:

1. Go to the add-on folder (e.g. `script.artwork.beef/`)
2. Download the ZIP file
3. Install via: **Settings** → **Add-ons** → **Install from zip file**

---

## 📋 Available Add-ons

### Script: Artwork Beef (v0.28.6)
**Automatic artwork management for your Kodi library**

- ✅ Kodi Omega (v21) compatible
- ✅ Fully migrated to Python 3
- ✅ All GUI dialogs working
- ✅ Supports: fanart.tv, TheTVDB.com, The Movie Database, TheAudioDB

**Features:**
- Automatic artwork download for movies, TV shows and music
- Manual artwork selection with GUI
- Context menu integration (right-click menu)
- Background service for automatic updates
- Local artwork caching

**Installation:** Via repository or [direct download](script.artwork.beef/script.artwork.beef-0.28.6.zip)

---

## 🛠️ For Developers

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
├── repository.kodiallen/        # Repository add-on
│   ├── addon.xml
│   ├── icon.png
│   └── fanart.jpg
├── script.artwork.beef/         # Example add-on
│   ├── addon.xml
│   ├── icon.png
│   ├── changelog.txt
│   ├── ... (all addon files)
│   └── script.artwork.beef-0.28.6.zip  # Auto-generated
├── addons.xml                   # Index of all add-ons (auto-generated)
├── addons.xml.md5               # Checksum (auto-generated)
├── tools/
│   └── generate_repo.py         # Generator script
└── README.md
```

### Creating ZIP Files

The `generate_repo.py` script automatically creates:
- ZIP files for each add-on
- `addons.xml` index
- `addons.xml.md5` checksum

**Important:** Run the script after every change!

---

## 📝 Adding an Add-on

### Requirements
- Add-on must have a valid `addon.xml`
- Add-on ID should be unique
- Must be Kodi Omega (v21) compatible

### Steps

1. **Create add-on folder:**
   ```
   script.myaddon/
   ├── addon.xml
   ├── icon.png (512x512 recommended)
   ├── fanart.jpg (1920x1080 recommended)
   ├── changelog.txt
   ├── LICENSE.txt
   └── ... (other files)
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
           <source>https://github.com/kodiallen/kodi-repo</source>
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

## 🔄 Updating an Add-on

1. Update files in your add-on folder
2. Increase version number in `addon.xml`
3. Update `changelog.txt`
4. Run `python3 tools/generate_repo.py`
5. Commit and push changes

Kodi will detect updates automatically!

---

## 🆘 Support

For issues or questions:
- Open an [Issue](https://github.com/kodiallen/kodi-repo/issues)
- Visit the Kodi Forum

---

## 📜 License

Each add-on has its own license. See the respective LICENSE.txt files.

The repository framework is available under MIT License.

---

## 🙏 Credits

- **Artwork Beef:** Based on [script.artwork.beef](https://github.com/rmrector/script.artwork.beef) by rmrector
- **Repository Framework:** Inspired by the Kodi community
- **Maintainer:** Kodi Allen

---

## ⚠️ Disclaimer

These add-ons are community ports for Kodi Omega. Use at your own risk.
For issues, please create an issue in this repository.

---

**Enjoy your add-ons! 🎉**
