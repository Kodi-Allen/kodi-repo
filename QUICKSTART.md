# 🚀 Quick Start: GitHub Repository Setup

## Step 1: Create GitHub Repository

1. Go to [GitHub](https://github.com) and sign in
2. Click **"New Repository"** (green button)
3. Repository settings:
   - **Name:** `kodi-repo` (or another name)
   - **Description:** "Kodi Omega compatible add-ons repository"
   - **Public** or **Private** (your choice)
   - ❌ **DO NOT** check "Initialize with README"
4. Click **"Create repository"**

## Step 2: Upload Repository

### Option A: With Git Command Line (recommended)

```bash
# 1. Go to your repository directory
cd /path/to/kodi-repo

# 2. Initialize Git
git init

# 3. Add files to staging
git add .

# 4. Create first commit
git commit -m "Initial commit: Kodi Allen Repository"

# 5. Rename branch (if needed)
git branch -M main

# 6. Add remote
git remote add origin https://github.com/kodiallen/kodi-repo.git

# 7. Upload
git push -u origin main
```

### Option B: With GitHub Desktop

1. Open [GitHub Desktop](https://desktop.github.com/)
2. **File** → **Add local repository**
3. Select your `kodi-repo` folder
4. Click **"Publish repository"**

### Option C: Directly via GitHub Web Interface

1. Go to your repository on GitHub
2. Click **"uploading an existing file"**
3. Drag all files into the window
4. Commit message: "Initial commit"
5. Click **"Commit changes"**

## Step 3: Create Repository ZIP (for installation)

```bash
# Regenerate repository
cd tools
python3 generate_repo.py
cd ..

# Repository ZIP is now available at:
# repository.kodiallen/repository.kodiallen-1.0.0.zip
```

## Step 4: Create GitHub Release (optional)

1. Go to your repository on GitHub
2. Click **"Releases"** → **"Create a new release"**
3. Tag: `v1.0.0`
4. Title: `Repository v1.0.0 - Initial Release`
5. **Add these files:**
   - `repository.kodiallen/repository.kodiallen-1.0.0.zip`
   - All add-on ZIPs (e.g. `script.artwork.beef/script.artwork.beef-0.28.6.zip`)
6. Click **"Publish release"**

## Step 5: Install in Kodi

### Installation via Repository ZIP:

1. Download `repository.kodiallen-1.0.0.zip`:
   - From GitHub Releases OR
   - Direct: `https://raw.githubusercontent.com/kodiallen/kodi-repo/main/repository.kodiallen/repository.kodiallen-1.0.0.zip`

2. In Kodi:
   - **Settings** → **Add-ons** → **Install from zip file**
   - Select `repository.kodiallen-1.0.0.zip`

3. Done! Your repository is now installed.

### Installation via direct URL (Alternative):

You can also install the repository directly with this URL:
```
https://raw.githubusercontent.com/kodiallen/kodi-repo/main/repository.kodiallen/repository.kodiallen-1.0.0.zip
```

## Common Problems

### Problem: "Unable to connect"
- Check your internet connection
- Make sure the repository is **Public** (not Private)
- Wait 2-3 minutes after push (GitHub cache)

### Problem: "Installation failed"
- Check if all URLs are correct
- Make sure `addons.xml` and `addons.xml.md5` exist
- Regenerate the repository with `python3 tools/generate_repo.py`

### Problem: "No addons found"
- Run `python3 tools/generate_repo.py`
- Commit and push the generated files
- Clear cache in Kodi: **Settings** → **System** → **Add-ons** → Clear cache

## Next Steps

1. **Add more add-ons:**
   ```bash
   # Copy your add-on
   cp -r /path/to/script.myaddon ./
   
   # Regenerate repository
   cd tools && python3 generate_repo.py && cd ..
   
   # Push to GitHub
   git add .
   git commit -m "Add: script.myaddon"
   git push
   ```

2. **Update an add-on:**
   - Change version in `addon.xml`
   - Update `changelog.txt`
   - Regenerate: `python3 tools/generate_repo.py`
   - Push to GitHub

3. **Share your repository:**
   - GitHub URL: `https://github.com/kodiallen/kodi-repo`
   - Installation link: `https://raw.githubusercontent.com/kodiallen/kodi-repo/main/repository.kodiallen/repository.kodiallen-1.0.0.zip`

## Support

For questions:
- GitHub Issues: `https://github.com/kodiallen/kodi-repo/issues`
- Kodi Forum: https://forum.kodi.tv

**Good luck! 🎉**
