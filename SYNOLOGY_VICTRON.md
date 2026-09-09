# EOS + Victron Cerbo GX auf Synology DS920+

Diese Anleitung beschreibt den einfachen Standardweg für den Fork `maxx3105/EOS`.

Die Synology benötigt nur **eine Compose-Datei**. Es werden **kein Git, kein SSH, keine GitHub Actions, kein eigenes Container-Registry-Image und keine ENV-Datei** benötigt.

Der Ablauf ist:

```text
1 Datei: docker-compose.yml
        ↓
Container Manager → Projekt → Erstellen
        ↓
öffentliches EOS-Basisimage wird geladen
        ↓
aktueller Fork-Quellcode aus main wird automatisch eingespielt
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
└── synology-data/
```

`synology-data` enthält später die persistente EOS-Konfiguration und Messhistorie.

## 3. Compose-Datei herunterladen

Verwende aus `main` entweder:

```text
synology/docker-compose.yml
```

oder die identische Datei:

```text
docker-compose.synology.yaml
```

Auf der NAS als

```text
docker-compose.yml
```

speichern.

Die aktuelle Datei enthält unter anderem:

```yaml
services:
  eos:
    image: akkudoktor/eos:latest
    entrypoint: ["/bin/sh", "-c"]
```

Sie lädt beim Containerstart automatisch den aktuellen Fork-Quellcode aus:

```text
https://github.com/maxx3105/EOS/archive/refs/heads/main.tar.gz
```

Dadurch wird auf der Synology **kein git-Programm** benötigt.

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

Beim ersten Start sollte Container Manager zuerst das öffentliche Image

```text
akkudoktor/eos:latest
```

laden. Danach erscheint im Container-Protokoll sinngemäß:

```text
EOS Victron: lade aktuellen Fork-Stand von main ...
EOS Victron: Fork-Quellcode erfolgreich geladen.
```

## 5. Alte Compose-Dateien erkennen

Wenn stattdessen im Terminal steht:

```text
pull access denied for maxx3105/eos
```

wird noch eine alte Compose-Datei verwendet.

Wenn dort steht:

```text
unable to find 'git': exec: "git": executable file not found
```

wird ebenfalls noch die ältere Git-Build-Variante verwendet.

In beiden Fällen im Projekt unter **YAML-Konfiguration** den Inhalt durch die aktuelle `docker-compose.yml` aus `main` ersetzen, speichern und das Projekt neu erstellen.

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

- Breitengrad und Längengrad
- IP-Adresse oder Hostname des Cerbo GX
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

Die Schnelleinrichtung legt zunächst eine PV-Fläche an. Für Ost/West-Anlagen oder mehrere Wechselrichter können anschließend unter **Config** weitere `pvforecast.planes` ergänzt werden.

## 9. Update

Für ein Update genügt es, das Projekt neu zu erstellen bzw. den Container neu zu erzeugen. Beim Start wird der aktuelle Quellcode von `main` erneut geladen.

Der Ordner

```text
/volume1/docker/eos-victron/synology-data/
```

darf dabei nicht gelöscht werden.

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

Alte Compose-Datei aktiv. Aktuelle YAML aus `main` übernehmen.

### `unable to find 'git'`

Alte Git-Build-Compose aktiv. Aktuelle YAML aus `main` übernehmen; sie benötigt kein Git.

### `EOS Victron: lade aktuellen Fork-Stand ...` schlägt fehl

Prüfen:

- NAS hat Internetzugriff
- DNS funktioniert
- `github.com` ist erreichbar

### Dashboard nicht erreichbar

Prüfen:

- Container läuft?
- Port `8504` veröffentlicht?
- NAS-Firewall erlaubt Port `8504`?
- Port `8504` bereits belegt?

Bei einer Portkollision in `docker-compose.yml` ändern:

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
