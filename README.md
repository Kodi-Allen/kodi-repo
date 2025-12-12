# Kodi Allen Repository

Kodi Omega (v21) compatible add-on repository.

## 📦 Installation

### Method 1: Via ZIP File

1. **Download the repository ZIP:**
   - Go to [Releases](https://github.com/Kodi-Allen/kodi-repo/releases)
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

---

## 🛠️ For Developers

### Updating the Repository

To add or update an add-on:

1. **Add an add-on:**
   ```bash
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

---

## 📜 License

Each add-on has its own license. See the respective LICENSE.txt files.

---

## 🙏 Credits

- **Artwork Beef:** Based on [script.artwork.beef](https://github.com/rmrector/script.artwork.beef) by rmrector
- **Maintainer:** Kodi Allen

---

**Enjoy your add-ons! 🎉**
