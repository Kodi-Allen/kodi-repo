# Kodi Allen Repository

Kodi Omega (v21) kompatibles Add-on Repository.

## 📦 Installation

### Methode 1: Über ZIP-Datei

1. **Repository ZIP herunterladen:**
   - Gehe zu [Releases](https://github.com/kodiallen/kodi-repo/releases)
   - Lade `repository.kodiallen-1.0.0.zip` herunter

2. **In Kodi installieren:**
   - Öffne Kodi
   - Gehe zu: **Einstellungen** → **Add-ons** → **Aus ZIP-Datei installieren**
   - Wähle die heruntergeladene `repository.kodiallen-1.0.0.zip`
   - Warte auf Bestätigung

3. **Add-ons installieren:**
   - Gehe zu: **Einstellungen** → **Add-ons** → **Aus Repository installieren**
   - Wähle **Kodi Allen Repository**
   - Wähle dein gewünschtes Add-on und installiere es

---

## 📋 Verfügbare Add-ons

### Script: Artwork Beef (v0.28.6)
**Automatisches Artwork Management für deine Kodi Bibliothek**

- ✅ Kodi Omega (v21) kompatibel
- ✅ Vollständig zu Python 3 migriert
- ✅ Alle GUI-Dialoge funktionieren
- ✅ Unterstützt: fanart.tv, TheTVDB.com, The Movie Database, TheAudioDB

**Features:**
- Automatisches Herunterladen von Artwork für Filme, Serien und Musik
- Manuelle Artwork-Auswahl mit GUI
- Kontext-Menü Integration (Rechtsklick)
- Hintergrund-Service für automatische Updates
- Lokales Artwork Caching

---

## 🛠️ Für Entwickler

### Repository aktualisieren

Um ein Add-on hinzuzufügen oder zu aktualisieren:

1. **Add-on hinzufügen:**
   ```bash
   cp -r /pfad/zu/script.meinaddon ./
   ```

2. **Repository generieren:**
   ```bash
   cd tools
   python3 generate_repo.py
   ```

3. **Zu GitHub pushen:**
   ```bash
   git add .
   git commit -m "Add/Update: script.meinaddon v1.0.0"
   git push
   ```

---

## 📜 Lizenz

Jedes Add-on hat seine eigene Lizenz. Siehe die jeweiligen LICENSE.txt Dateien.

---

## 🙏 Credits

- **Artwork Beef:** Basiert auf [script.artwork.beef](https://github.com/rmrector/script.artwork.beef) von rmrector
- **Maintainer:** Kodi Allen

---

**Viel Spaß mit deinen Add-ons! 🎉**
