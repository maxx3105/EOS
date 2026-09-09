# EOS + Victron Cerbo GX auf Synology DS920+

Diese Anleitung beschreibt den **aktuell funktionierenden Standardweg** für den Fork `maxx3105/EOS`.

Die Synology benötigt nur **eine Compose-Datei**. Container Manager baut das Image direkt aus dem öffentlichen `main`-Branch des Forks. Es werden **kein Docker-Hub-Image, kein GitHub-Login, keine GitHub Actions, kein SSH, kein Git und keine ENV-Datei** benötigt.

```text
1 Datei: docker-compose.yml
        ↓
Container Manager → Projekt → Erstellen
        ↓
EOS wird direkt aus main gebaut
        ↓
http://NAS-IP:8504 öffnen
        ↓
Standort + Cerbo + PV-Anlage im Browser einrichten
```

> Der Victron-Adapter arbeitet in dieser Ausbaustufe nur lesend. EOS schreibt keine ESS-Sollwerte und verändert keine Cerbo- oder Wechselrichter-Einstellungen.

## 1. Cerbo GX vorbereiten

Am Cerbo GX den **Modbus TCP Server** aktivieren.

Je nach Venus-OS-Version:

```text
Einstellungen → Integrationen → Modbus TCP Server
```

oder:

```text
Einstellungen → Dienste → Modbus TCP
```

Danach:

1. Modbus TCP aktivieren.
2. Wenn verfügbar **Read-only / Nur Lesen** auswählen.
3. `com.victronenergy.system` prüfen.
4. Normalerweise **Unit ID 100** verwenden.
5. IP-Adresse des Cerbo notieren.

Standard-Port ist TCP `502`.

## 2. Ordner auf der Synology anlegen

In **File Station**:

```text
/volume1/docker/eos-victron
```

In diesen Ordner kommt nur:

```text
/volume1/docker/eos-victron/
├── docker-compose.yml
└── synology-data/   # wird für persistente Daten verwendet
```

## 3. Richtige Compose-Datei herunterladen

Verwende aus `main` entweder:

```text
synology/docker-compose.yml
```

oder die identische Datei:

```text
docker-compose.synology.yaml
```

Auf der NAS muss sie als

```text
docker-compose.yml
```

liegen.

Die funktionierende Datei enthält unter anderem:

```yaml
services:
  eos:
    container_name: eos-victron
    image: eos-victron:local
    build:
      context: "https://github.com/maxx3105/EOS.git#main"
      dockerfile: Dockerfile
```

**Wichtig:** Wenn in deiner Datei stattdessen

```yaml
image: maxx3105/eos:latest
```

steht, ist das eine alte/falsche Datei. Dieses Docker-Hub-Image ist für diesen Installationsweg nicht erforderlich.

## 4. Projekt im Container Manager erstellen

DSM öffnen:

```text
Container Manager
→ Projekt
→ Erstellen
```

Eintragen:

```text
Projektname: eos-victron
Pfad:        /volume1/docker/eos-victron
```

Als Compose-Datei die dort liegende `docker-compose.yml` verwenden.

Projekt erstellen und starten.

Beim ersten Start baut die DS920+ das Image selbst aus `main`. Das dauert länger als ein normaler Containerstart und kann die CPU vorübergehend deutlich auslasten.

## 5. Woran erkenne ich den richtigen Ablauf?

Richtig ist, wenn Container Manager einen **Build** startet.

Falsch ist, wenn im Terminal steht:

```text
eos Pulling
pull access denied for maxx3105/eos
```

Dann wird noch eine alte Compose-Datei verwendet. Projekt schließen/löschen, die aktuelle `docker-compose.yml` aus `main` verwenden und das Projekt neu erstellen.

## 6. EOS öffnen

Wenn die NAS zum Beispiel `192.168.1.20` hat:

```text
Dashboard: http://192.168.1.20:8504
API:       http://192.168.1.20:8503
API-Doku:  http://192.168.1.20:8503/docs
```

## 7. Browser-Schnelleinrichtung

Auf der Startseite befindet sich die **Schnelleinrichtung: Synology + Victron Cerbo GX**.

Dort eintragen:

### Standort

- Breitengrad
- Längengrad

### Cerbo GX

- IP-Adresse oder Hostname

Port `502`, Unit ID `100` und die übrigen Standardwerte werden automatisch gesetzt.

### PV-Anlage

Für die erste Dachfläche:

- Modulneigung
- Azimut
- Modulleistung in Wp
- Module pro String
- Anzahl Strings
- Wechselrichterleistung in W

Azimut:

```text
0°   = Norden
90°  = Osten
180° = Süden
270° = Westen
```

Danach **Einrichtung speichern** anklicken.

EOS setzt automatisch:

```text
EMS-Modus:            PREDICTION
Intervall:            5 Minuten
Wetter:               OpenMeteo
PV-Prognose:          PVForecastPVLibVictron
Prognosehorizont:     48 Stunden
Adapter:              Victron
Cerbo-Port:           502
Cerbo-Unit-ID:        100
PV-Istwertkorrektur:  aktiv
```

## 8. Mehrere Dachflächen

Die Schnelleinrichtung legt zunächst eine PV-Fläche an.

Für Ost/West-Anlagen oder mehrere Wechselrichter können anschließend unter **Config** weitere `pvforecast.planes` ergänzt werden.

## 9. Update

Im Container Manager das Projekt stoppen und **neu erstellen / neu bauen**. Dadurch wird der aktuelle `main`-Stand erneut verwendet.

Nicht löschen:

```text
/volume1/docker/eos-victron/synology-data/
```

Die Browser-Konfiguration und Messhistorie bleiben dort erhalten.

## 10. Backup

In **Hyper Backup** mindestens sichern:

```text
/volume1/docker/eos-victron/synology-data/
```

Optional zusätzlich:

```text
/volume1/docker/eos-victron/docker-compose.yml
```

## 11. Fehlerbehebung

### `pull access denied for maxx3105/eos`

Du verwendest eine alte Compose-Datei. Die aktuelle Datei muss einen `build:`-Block mit

```text
https://github.com/maxx3105/EOS.git#main
```

enthalten.

### Build schlägt beim GitHub-Zugriff fehl

Prüfen:

- NAS hat Internetzugriff
- DNS funktioniert
- `github.com` ist von der NAS erreichbar

### Dashboard nicht erreichbar

Prüfen:

- Container läuft?
- Port `8504` wurde veröffentlicht?
- NAS-Firewall erlaubt Port `8504`?
- Port `8504` ist bereits belegt?

Bei einer Portkollision können die Host-Ports in `docker-compose.yml` geändert werden:

```yaml
ports:
  - "18503:8503"
  - "18504:8504"
```

Dann ist das Dashboard unter `http://NAS-IP:18504` erreichbar.

### Cerbo nicht erreichbar

Prüfen:

- Cerbo-IP im Browser-Assistenten korrekt?
- Modbus TCP aktiviert?
- Port `502` erreichbar?
- `com.victronenergy.system` vorhanden?
- Unit ID `100` korrekt?
- Firewall/VLAN blockiert die Verbindung?

### Noch keine Istwertkorrektur

Direkt nach dem ersten Start fehlen zunächst historische Cerbo-Messungen. EOS verwendet vorübergehend die reine PVLib-Prognose. Sobald genügend aktuelle Messwerte vorhanden sind, wird die Istwertkorrektur automatisch wirksam.

## 12. Sicherheit

Nicht direkt ins Internet weiterleiten:

```text
502   Victron Modbus TCP
8503  EOS API
8504  EOS Dashboard
```

Für externen Zugriff besser VPN oder einen abgesicherten HTTPS-Reverse-Proxy verwenden.

Wenn Venus OS die Option anbietet:

```text
Modbus TCP → Access permissions → Read-only
```
