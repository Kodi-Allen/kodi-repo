# GeoTV – Phase 1: Privado USA und Tubi

Dieser Stack routet ausschließlich das Tubi-Kodi-Add-on über eine US-IP. Kodis
globaler Proxy bleibt unverändert; andere Add-ons, ARD, Rai und normale
Internetverbindungen verwenden weiterhin den normalen Anschluss.

## Architektur

```text
Kodi / plugin.video.tubitv
├── API, Auth, Katalog ── CONNECT-Proxy 192.0.2.10:8883
│                         └── gluetun-us ── Privado USA
└── HLS, Segmente, Bilder, Untertitel und DRM-Lizenztransport
                          └── Relay 192.0.2.10:8893
                              └── Netzwerk-Namespace von gluetun-us
```

InputStream Adaptive 21 besitzt keine dokumentierte Proxy-Eigenschaft pro
Stream. Deshalb ersetzt das Add-on Medien-URLs durch zeitlich begrenzte,
HMAC-signierte Relay-URLs. Der Relay schreibt alle URI-Zeilen und `URI=`-
Attribute in HLS-Playlists um. Child-Playlists, Segmente, Schlüssel-URLs,
Untertitel, Artwork, Redirects und rohe POST-Antworten eines legitimen
Widevine-Lizenztransports bleiben dadurch auf dem US-Ausgang. Es findet keine
DRM-Umgehung statt.

Der Relay akzeptiert kein frei verwendbares URL-Argument: jede URL benötigt
eine gültige Signatur und ein Ablaufdatum. Zusätzlich blockiert er lokale und
private Upstream-Adressen. Die LAN-Ports werden nur an die proxy-host-Adresse
gebunden und dürfen nicht am Router weitergeleitet werden.

## Verzeichnisstruktur

Die produktive Installation liegt vollständig unter:

```text
/opt/geotv/
├── compose.yml
├── .env                       # 0600, nicht versionieren
├── .env.example
├── config/gluetun/us/privado-us.ovpn   # alter Einzelserver-Fallback, nicht mehr aktiv
├── config/threadfin/{de,it,us}/       # für spätere Phasen reserviert
├── playlists/{sources,generated}/
├── epg/{sources,generated}/
├── logs/
├── logos/
├── scripts/prepare-privado-us.sh
└── tubi/
    ├── relay/
    ├── kodi-addon-patch/
    └── documentation/
```

Threadfin und der Master-M3U/XMLTV-Aggregator sind in Phase 1 absichtlich noch
nicht aktiv.

## Einmalige Einrichtung

```bash
cd /opt/geotv
cp .env.example .env
chmod 600 .env
./scripts/prepare-privado-us.sh
```

In `.env` gehören die Privado-Service-Zugangsdaten, zufällige Proxy-
Zugangsdaten und ein Relay-Schlüssel. Zufallswerte lassen sich so erzeugen:

```bash
openssl rand -hex 24   # HTTPPROXY_PASSWORD
openssl rand -hex 32   # RELAY_SIGNING_KEY
```

VPN-, Proxy- und Relay-Geheimnisse gehören weder in `compose.yml` noch in Git.
Das vorbereitete OpenVPN-Profil enthält keine Zugangsdaten. Aktuelle US-
Profile zeigt dieser Befehl:

```bash
./scripts/prepare-privado-us.sh --list-us
```

## Start, Stop und Status

```bash
cd /opt/geotv
docker compose up -d --build
docker compose ps

docker compose stop
docker compose start

docker compose down       # Container/Netz entfernen, Datenvolume bleibt
```

Erwartete Ports:

- `192.0.2.10:8883`: authentifizierter Gluetun HTTP/HTTPS-CONNECT-Proxy
- `192.0.2.10:8893`: signierter Tubi-Medien-Relay
- `34403`: für Threadfin USA in einer späteren Phase reserviert

## Kodi-Add-on

Unter **TubiTV → Einstellungen → Netzwerkroute** gibt es genau zwei Modi:

- **Direkt**: API und Medien laufen ohne GeoTV.
- **Benutzerdefiniert**: die gespeicherten Felder bilden das GeoTV-US-Profil.

Für den Beispiel-Host sind die Felder:

```text
Route:              Benutzerdefiniert
Proxy-Host:         192.0.2.10
Proxy-Port:         8883
Proxy-Benutzer:     Wert aus .env
Proxy-Passwort:     Wert aus .env
Medien-Relay-Host:  192.0.2.10
Medien-Relay-Port:  8893
Relay-Schlüssel:    RELAY_SIGNING_KEY aus .env
```

`Direkt` ist der Paket-Default. Auf dem Vero wird das gespeicherte
benutzerdefinierte Profil aktiviert. Eine unvollständige benutzerdefinierte
Konfiguration schlägt absichtlich geschlossen fehl und fällt nicht auf die
normale öffentliche IP zurück.

## Tests

Direkte öffentliche IP:

```bash
curl https://ipinfo.io/json
```

US-Proxy (Passwort interaktiv oder aus einer bereits geladenen `.env`):

```bash
cd /opt/geotv
set -a; source .env; set +a
curl --proxy "http://${GEOTV_BIND_ADDRESS}:8883" \
  --proxy-user "${HTTPPROXY_USER}:${HTTPPROXY_PASSWORD}" \
  https://ipinfo.io/json
```

Relay und Container:

```bash
curl http://192.0.2.10:8893/healthz
docker compose ps
docker compose logs --tail=100 gluetun-us tubi-relay
```

Die Direkt-IP muss Österreich zeigen, der Proxy USA. Ein echter Kodi-Test muss
im Relay-Log sowohl `rewritten HLS` als auch weitere CDN-GETs zeigen. Das ist
der Nachweis, dass nicht nur die API, sondern auch Child-Playlists und
Mediensegmente über Privado laufen.

## Update

Vor jedem Update ein Backup anlegen. Danach Images neu ziehen und nur den
GeoTV-Stack neu erstellen:

```bash
cd /opt/geotv
docker compose pull
docker compose build --pull tubi-relay
docker compose up -d
docker compose ps
```

Seit 2026-10-04 nutzt `gluetun-us` Gluetuns eingebauten Privado-Anbieter
(`VPN_SERVICE_PROVIDER=privado`) mit einer Städteliste im Osten und in der Mitte
der USA (`SERVER_CITIES` in `compose.yml`). Gluetun wählt zufällig einen Server
und wechselt auf einen anderen, wenn der Healthcheck den Tunnel neu startet;
`UPDATER_PERIOD=24h` hält die Serverliste aktuell. Ein Einzelserver-Profil wie
früher (`privado-us.ovpn`) hatte keine Ausfallsicherheit: `atl-008` lieferte am
2026-10-04 zuerst nur noch tröpfelnd und war dann zwei Stunden weg. Änderungen
an der Städteliste mit `docker compose up -d --force-recreate gluetun-us tubi-relay`
aktivieren; der Relay teilt sich Gluetuns Netzwerk und muss mit.

## Backup

Mindestens diese Dateien sichern:

```text
/opt/geotv/.env
/opt/geotv/compose.yml
/opt/geotv/tubi/relay/
```

`.env` enthält Geheimnisse und muss im Backup entsprechend geschützt werden.
Das benannte Docker-Volume enthält nur Gluetun-Laufzeitdaten und ist für eine
Wiederherstellung nicht zwingend nötig.

## Fehlerdiagnose

```bash
cd /opt/geotv
docker compose ps
docker compose logs --tail=200 gluetun-us
docker compose logs --tail=200 tubi-relay
curl http://192.0.2.10:8893/healthz
ss -lnt | grep -E ':8883|:8893'
```

- Proxy `407`: Benutzername oder Passwort in Kodi stimmt nicht mit `.env`
  überein.
- Relay `401`: Relay-Schlüssel zwischen Kodi und `.env` stimmt nicht überein
  oder die signierte URL ist abgelaufen.
- Relay `403`: Ziel löst auf eine private/lokale Adresse auf; der SSRF-Schutz
  hat die Anfrage blockiert.
- Katalog funktioniert, Video nicht: Relay-Log auf `rewritten HLS` oder
  `rewritten DASH` und anschließende CDN-Requests prüfen.
- `stream stalled` kurz nach dem Start: mindestens Relay `1.1.0` und Tubi-
  Add-on `2026.10.4+kodiallen.4` verwenden; ältere Builds behandelten Kodis
  Manifest-Range-Probe nicht korrekt.
- Vero 4K/4K+: Die letzte 32-Bit-ARM-Widevine-CDM stürzt auch mit einem
  offiziellen Shaka-Teststream nativ ab. Version `.4` blockiert deshalb nur
  verschlüsselte Titel mit einer Meldung, statt Kodi neu starten zu lassen.
- Nach einer Schlüsselrotation müssen Stack und Kodi-Einstellungen gemeinsam
  aktualisiert werden.

Ein älterer, separater Gluetun-Stack auf demselben Host ist unabhängig und
darf für GeoTV nicht verändert werden.
