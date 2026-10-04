# Tubi Kodi add-on patch

Produktive Version: `plugin.video.tubitv 2026.10.4+kodiallen.4`

Die gebaute ZIP-Datei wird bei der Bereitstellung aus dem Repository hierher
kopiert. Der Quellcode liegt im Repository unter `plugin.video.tubitv/`.

Wesentliche Änderungen gegenüber dem Upstream-Fork:

- Add-on-Einstellung **Direkt / Benutzerdefiniert**
- eigener authentifizierter HTTP-CONNECT-Proxy nur für Tubi-API/Auth
- signierte Relay-URLs für HLS, DASH/SegmentBase, Segmente, Untertitel, Artwork
  und Widevine-Lizenztransport
- DASH-Präferenz für DRM-Titel auf unterstützten Kodi-Geräten
- gezielter Absturzschutz für Widevine auf 32-Bit-OSMC Vero 4K/4K+; DRM-Titel
  werden dort mit einer Meldung abgewiesen, klare Streams und Live-TV bleiben
  verfügbar
- fail-closed bei unvollständiger benutzerdefinierter Konfiguration
- Kodis globaler Proxy bleibt unberührt

Auf dem Vero 4K+ ist zusätzlich `script.module.t1mlib 4.0.9` aus dem offiziellen
Kodi-Omega-Repository erforderlich.
