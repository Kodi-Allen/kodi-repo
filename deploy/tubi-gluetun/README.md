# Tubi über eine US-IP mit Gluetun

Dieses Compose-Projekt stellt einen lokalen HTTP-CONNECT-Proxy auf Port 8888
bereit. Gluetun verbindet ihn ausschließlich mit einem VPN-Server in den USA.

```text
Tubi-Add-on (Python API) ----\
                              +-- HTTP CONNECT --> Gluetun --> US-VPN --> Tubi
Kodi / inputstream.adaptive -/
```

Beide Pfade müssen dieselbe US-IP verwenden. Der in diesem Repository
enthaltene Tubi-Patch übernimmt Kodis globale HTTP-Proxy-Einstellung deshalb
automatisch auch für seine Python-Requests. Kodi selbst verwendet die
Einstellung für Manifest, Videosegmente, Untertitel und Widevine-Lizenz.

## 1. Gluetun konfigurieren

```bash
cd deploy/tubi-gluetun
cp .env.example .env
```

Das Projekt ist fest für **Mullvad über WireGuard** eingerichtet. Im
[Mullvad-Konfigurationsgenerator](https://mullvad.net/en/account/wireguard-config)
anmelden, eine WireGuard-Konfiguration erzeugen und herunterladen. Aus dem
`[Interface]`-Abschnitt der `.conf` werden zwei Werte benötigt:

```ini
[Interface]
PrivateKey = <kommt in WIREGUARD_PRIVATE_KEY>
Address = 10.64.x.x/32,fc00:.../128
```

Für `WIREGUARD_ADDRESSES` nur die erste, also die IPv4-Adresse einschließlich
`/32`, verwenden. Der auf Mullvads Geräteseite angezeigte **WireGuard Key** ist
nicht der benötigte private Schlüssel; maßgeblich sind `PrivateKey` und
`Address` aus der heruntergeladenen Konfiguration. Siehe Gluetuns aktuelle
[Mullvad-Anleitung](https://github.com/qdm12/gluetun-wiki/blob/main/setup/providers/mullvad.md).

Beide Werte lokal in `.env` eintragen und weder committen noch im Chat senden.
`SERVER_COUNTRIES` ist im Compose fest auf `United States` gesetzt. Optional
kann `SERVER_CITIES` oder `SERVER_HOSTNAMES` in `.env` gesetzt werden, falls
Tubi einen bestimmten Mullvad-Ausgang ablehnt.

Wenn Kodi auf einem anderen Gerät läuft, muss `GLUETUN_BIND_ADDRESS` die
LAN-Adresse des Docker-Hosts sein. Port 8888 darf nicht am Internet-Router
freigegeben werden.

## 2. Starten und US-Ausgang prüfen

```bash
docker compose up -d
docker compose ps
docker compose logs --tail=100 gluetun
```

Ohne Proxy-Authentifizierung lässt sich die Ausgangs-IP so prüfen:

```bash
curl --fail --proxy http://127.0.0.1:8888 https://ipinfo.io/json
```

Bei Kodi auf einem anderen Gerät `127.0.0.1` durch die LAN-Adresse des
Docker-Hosts ersetzen. Falls Benutzername und Passwort gesetzt wurden:

```bash
curl --fail --proxy http://BENUTZER:PASSWORT@HOST:8888 https://ipinfo.io/json
```

Die Antwort muss `"country": "US"` enthalten.

## 3. Kodi konfigurieren

Unter **Einstellungen -> System -> Internetzugriff**:

1. **Proxyserver verwenden** einschalten.
2. Proxytyp **HTTP** wählen.
3. Als Server die Adresse des Docker-Hosts eintragen.
4. Port **8888** eintragen.
5. Falls gesetzt, Proxy-Benutzername und -Passwort ergänzen.

Danach Kodi neu starten und `TubiTV` aus dem Kodi-Allen-Repository öffnen.

## Wichtig

- Der Proxy gilt in Kodi global, weil auch der Player und
  `inputstream.adaptive` darüber laufen müssen. Der Add-on-Patch sorgt dafür,
  dass Tubi-Browsing und Anmeldung nicht an Gluetun vorbeigehen.
- Der Verkehr zwischen Kodi und Gluetun sollte im vertrauenswürdigen LAN
  bleiben. HTTPS-Inhalte bleiben durch den CONNECT-Tunnel Ende-zu-Ende
  verschlüsselt, Proxy-Zugangsdaten selbst sind jedoch kein Ersatz für eine
  abgesicherte Netzwerkgrenze.
- Für DRM-Titel benötigt Kodi weiterhin `inputstream.adaptive` und Widevine.
- Tubi-Inhalte und Verfügbarkeit richten sich nach der Ausgangs-IP und den
  jeweiligen Nutzungsbedingungen.
