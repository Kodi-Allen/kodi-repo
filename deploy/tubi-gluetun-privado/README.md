# Tubi über PrivadoVPN auf proxy-host

Ja: Gluetun verwendet PrivadoVPN als benutzerdefinierten OpenVPN-Anbieter und
stellt auf proxy-host einen HTTP-CONNECT-Proxy auf Port 8888 bereit:

```text
Kodi --> proxy-host:8888 --> Gluetun --> Privado US --> Tubi
```

PrivadoVPN ist derzeit kein nativer Gluetun-Provider. Deshalb wird ein
offizielles Privado-OpenVPN-Profil als `custom`-Konfiguration eingebunden.
Privado stellt manuelle OpenVPN-Profile laut eigener Dokumentation nur für
Premiumkonten bereit.

## 1. Aktuelles US-Profil vorbereiten

Das Skript lädt Privados aktuelles offizielles Profilarchiv. Standardmäßig
wird New York (`jfk-067.default.ovpn`) gewählt:

```bash
cd deploy/tubi-gluetun-privado
./prepare-config.sh
```

Alle aktuell angebotenen US-Profile anzeigen und beispielsweise Miami wählen:

```bash
./prepare-config.sh --list-us
./prepare-config.sh mia-007.default.ovpn
```

Das Skript ersetzt den Endpoint-Hostnamen durch dessen IPv4-Adresse, wie von
Gluetun für Custom-OpenVPN-Profile verlangt, und aktiviert Privados
OpenVPN-2.6-Cipher-Angaben. Das erzeugte `config/privado-us.ovpn` bleibt durch
`.gitignore` lokal.

## 2. Zugangsdaten eintragen

```bash
cp .env.example .env
```

In `.env` den **manuellen VPN-Benutzernamen** und das dazugehörige VPN-Passwort
aus dem Privado-Administrationsbereich eintragen. Nicht die E-Mail-Adresse
verwenden und die Zugangsdaten nicht committen oder im Chat senden.

Wenn Kodi nicht auf proxy-host selbst läuft, `GLUETUN_BIND_ADDRESS` auf die
LAN-IP von proxy-host setzen. Port 8888 niemals am Internet-Router freigeben.

## 3. Starten und prüfen

```bash
docker compose up -d
docker compose ps
docker compose logs --tail=100 gluetun
set -a
source .env
set +a
curl --fail --proxy http://127.0.0.1:8888 \
  --proxy-user "${HTTPPROXY_USER}:${HTTPPROXY_PASSWORD}" \
  https://ipinfo.io/json
```

Bei Kodi auf einem anderen Gerät im letzten Befehl `127.0.0.1` durch die
proxy-host-LAN-IP ersetzen. Die Antwort muss `"country": "US"` enthalten.

## 4. Kodi

Unter **Einstellungen -> System -> Internetzugriff**:

1. **Proxyserver verwenden** einschalten.
2. Proxytyp **HTTP** auswählen.
3. proxy-host-IP und Port **8888** eintragen.
4. Optional die in `.env` gesetzten Proxy-Zugangsdaten ergänzen.
5. Kodi neu starten und das gepatchte TubiTV-Add-on öffnen.

Der Proxy gilt global für Kodis HTTP-Verkehr. Das gepatchte Add-on übernimmt
diese Kodi-Einstellung auch für seine Python-API- und Authentifizierungsaufrufe,
damit Katalog, Anmeldung und Wiedergabe dieselbe US-IP sehen.

## Quellen

- [Privado: manuelle OpenVPN-Einrichtung](https://support.privadovpn.com/kb/article/358-windows-openvpn-manual-setup-openvpn-gui-client/)
- [Gluetun: Custom OpenVPN provider](https://github.com/qdm12/gluetun-wiki/blob/main/setup/providers/custom.md)
- [Gluetun: OpenVPN configuration file](https://github.com/qdm12/gluetun-wiki/blob/main/setup/openvpn-configuration-file.md)
