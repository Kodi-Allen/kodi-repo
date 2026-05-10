# Kodi version branches

This repository can publish separate add-on feeds per Kodi version.

## Branches

- `main`: shared base branch and current default feed
- `kodi-21`: Kodi 21 release feed
- `kodi-22`: Kodi 22 release feed

Each Kodi branch keeps its own `addons.xml`, `addons.xml.md5`, and release ZIP files.
The `repository.kodiallen` add-on in each branch must point to that same branch in
its raw GitHub URLs.

## Build

Run this from the repository root after changing an add-on:

```powershell
$env:PYTHONIOENCODING='utf-8'
python .\tools\generate_repo.py
```

Then commit the changed add-on files, ZIP file, `addons.xml`, and `addons.xml.md5`
on the active Kodi branch.

## Install URLs

Use the repository ZIP from the matching branch:

```text
https://raw.githubusercontent.com/kodiallen/kodi-repo/kodi-21/repository.kodiallen/repository.kodiallen-1.0.0.zip
https://raw.githubusercontent.com/kodiallen/kodi-repo/kodi-22/repository.kodiallen/repository.kodiallen-1.0.0.zip
```
