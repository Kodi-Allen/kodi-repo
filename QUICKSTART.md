# Quick start

## Install the repository in Kodi

1. Download **[`repository.kodiallen-1.0.1.zip`](https://raw.githubusercontent.com/Kodi-Allen/kodi-repo/main/repository.kodiallen/repository.kodiallen-1.0.1.zip)**
   and save it to a location Kodi can access.
2. In Kodi, open **Settings → System → Add-ons**, enable **Unknown sources**, and confirm
   Kodi's warning.
3. Open **Settings → Add-ons → Install from zip file** and select the downloaded ZIP.
4. Wait for confirmation, then open **Install from repository → Kodi Allen Repository**.
   Choose an add-on and select **Install**.

The installer is an add-on ZIP. GitHub's **Code → Download ZIP** is a source archive and
cannot be installed as a Kodi add-on. Version 1.0.1 includes both the main add-on feed and
the GitHub Releases feed used by Aeon Tajo.

See the [main README](README.md) for the add-on catalogue, compatibility notes and help.
The steps below are for maintainers publishing repository changes.

## Prepare a repository update

Work in a checkout of [Kodi-Allen/kodi-repo](https://github.com/Kodi-Allen/kodi-repo).
Read the [version branch notes](BRANCHES.md) before choosing `main`, `kodi-21` or `kodi-22`.
When maintaining a fork, update the URLs in `repository.kodiallen/addon.xml` to point to
your own public repository and the intended branch.

1. Add or update the add-on folder at the repository root. It needs a valid `addon.xml`,
   a unique add-on ID, its license and original credits.
2. Increase the add-on version in `addon.xml` and update its changelog.
3. Run the generator **from the repository root**:

   ```bash
   python3 tools/generate_repo.py
   ```

   On Windows PowerShell:

   ```powershell
   $env:PYTHONIOENCODING = 'utf-8'
   python .\tools\generate_repo.py
   ```

The generator scans the current directory. Running it from `tools/` will not find the
add-ons. It creates the versioned ZIP for each add-on with a root `addon.xml`, plus
`addons.xml` and `addons.xml.md5`. With the current repository metadata, the installer
is `repository.kodiallen/repository.kodiallen-1.0.1.zip`.

## Review and publish

1. Review the source changes, generated ZIPs, `addons.xml` and its checksum.
   Check that versions and URLs match the intended feed.
2. Commit the intended source, ZIP and feed changes, then push them to the chosen branch.
3. Confirm that the repository installer and feeds are publicly downloadable, then test
   installation or updating in Kodi.

GitHub Releases are optional for ZIPs served directly from the repository. For add-ons
distributed through the separate release feed, such as Aeon Tajo, upload the versioned ZIP
to the matching release tag and maintain `addons-releases.xml` and
`addons-releases.xml.md5` separately. The generator does not update this feed.

The existing `v1.0.0` release contains the older repository installer. Share the current
1.0.1 direct download linked above for installations using both feeds.

## Troubleshooting

| Problem | What to check |
|---|---|
| Kodi cannot open the ZIP | Download the repository installer ZIP to a local folder or share that Kodi can access. A GitHub web page or source archive is not the installer. |
| The generator reports no add-ons | Run it from the repository root, where the add-on folders are located. |
| An add-on is missing | Check its category, the installed repository version and the relevant feed. Aeon Tajo uses the second feed included in repository version 1.0.1. |
| A new version is missing | Check the published `addon.xml` version, ZIP filename, feed contents and checksum. In Kodi, open the repository's context menu and choose **Check for updates**. |
| A fork cannot load its feed | Confirm that the repository URLs point to the correct public repository and branch, and that the files exist there. |

Repository questions and bugs: [GitHub issues](https://github.com/Kodi-Allen/kodi-repo/issues).
General Kodi help: [Kodi community forum](https://forum.kodi.tv/).
