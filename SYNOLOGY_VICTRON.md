# EOS + Victron Cerbo GX auf Synology DS920+

Diese Variante ist für eine möglichst einfache Installation auf einer **Synology DS920+** gedacht.
EOS läuft als fertiges Docker-Image und wird anschließend **im Browser eingerichtet**.

```text
1 Compose-Datei auf die NAS
        |
        v
Container-Manager-Projekt starten
        |
        v
http://NAS-IP:8504 öffnen
        |
        v
Standort + Cerbo + PV-Daten eintragen
        |
        v
Einrichtung speichern
```

Nicht benötigt werden: Git, SSH, Dockerfile, lokaler Docker-Build, Python, Home Assistant, Node-RED oder MQTT.

Das Image lautet:

```text
ghcr.io/maxx3105/eos-victron:latest
```

> Der Victron-Adapter arbeitet in dieser Ausbaustufe nur lesend. Es werden keine ESS-Sollwerte oder Geräteeinstellungen geschrieben.

## 1. Voraussetzungen

- Synology DS920+ mit einer kompatiblen Version von **Container Manager**
- Victron Cerbo GX / GX-Gerät im lokalen Netzwerk
- Internetzugriff der NAS für das Container-Image und Open-Meteo
- feste bzw. reservierte IP-Adressen für NAS und Cerbo sind empfohlen
- Daten der PV-Anlage: Neigung, Azimut, Modulleistung, Module pro String, Anzahl Strings und Wechselrichterleistung

## 2. Cerbo GX vorbereiten

Am Cerbo den **Modbus TCP Server** aktivieren.

Je nach Venus-OS-Version:

```text
Einstellungen -> Integrationen -> Modbus TCP Server
```

oder bei älteren Versionen:

```text
Einstellungen -> Dienste -> Modbus TCP
```

Danach:

1. Modbus TCP aktivieren.
2. Wenn verfügbar, Zugriff auf **Read-only / Nur Lesen** stellen.
3. `com.victronenergy.system` unter den verfügbaren Diensten prüfen.
4. Für die Systemdaten normalerweise **Unit ID 100** verwenden.
5. IP-Adresse des Cerbo notieren.

Standard-Port ist TCP `502`.

## 3. Ordner auf der Synology anlegen

In **File Station**:

```text
/volume1/docker/eos-victron
```

Die Ordnerstruktur bleibt minimal:

```text
/volume1/docker/eos-victron/
├── docker-compose.yml
└── synology-data/
```

`synology-data` enthält später Konfiguration, Datenbank, Messwerte und Cache und muss bei Updates erhalten bleiben.

## 4. Compose-Datei kopieren

Aus dem `main`-Branch dieses Repositories wird nur folgende Datei benötigt:

```text
docker-compose.synology.yaml
```

Auf der NAS als

```text
docker-compose.yml
```

speichern.

Die Compose-Datei lädt das fertige Image und bindet den persistenten Datenordner ein. Eine `synology.env` ist für die normale Installation nicht mehr nötig.

## 5. Projekt im Container Manager erstellen

In DSM:

```text
Container Manager
-> Projekt
-> Erstellen
```

Eintragen:

```text
Projektname: eos-victron
Pfad:        /volume1/docker/eos-victron
```

Als Compose-Datei `docker-compose.yml` verwenden und das Projekt erstellen/starten.

Container Manager lädt automatisch:

```text
ghcr.io/maxx3105/eos-victron:latest
```

## 6. EOS öffnen

Beispiel: Die NAS hat `192.168.1.20`.

```text
Dashboard: http://192.168.1.20:8504
API:       http://192.168.1.20:8503
API Docs:  http://192.168.1.20:8503/docs
```

Auf der Startseite befindet sich die **Schnelleinrichtung: Synology + Victron Cerbo GX**.

## 7. Browser-Einrichtung

Der Assistent fragt folgende Werte ab.

### Standort

- Breitengrad
- Längengrad

### Cerbo GX

- IP-Adresse oder Hostname

Port `502`, Unit ID `100`, Timeout und Read-only-Datenzugriff sind für die Standardinstallation bereits vorgesehen.

### PV-Anlage – erste Dachfläche

- Modulneigung in Grad
- Azimut: `0=Norden`, `90=Osten`, `180=Süden`, `270=Westen`
- Modulleistung in Wp
- Module pro String
- Strings pro Wechselrichter
- Wechselrichterleistung in W

Für die einfache Einrichtung reicht die Leistung von Modul und Wechselrichter. PVLib sucht daraus ein passendes CEC-Modell.

Nach **Einrichtung speichern** setzt EOS automatisch:

```text
EMS-Modus:            PREDICTION
Intervall:            5 Minuten
Wetter:               OpenMeteo
PV-Prognose:          PVForecastPVLibVictron
Prognosehorizont:     48 Stunden
Adapter:              Victron
Cerbo Port:           502
Cerbo Unit ID:        100
PV-Istwertkorrektur:  aktiv
```

Die Konfiguration wird unter `/data` gespeichert und liegt damit physisch im NAS-Ordner `synology-data`.

## 8. Mehrere PV-Flächen

Der Schnelleinrichtungsassistent legt bewusst zunächst **eine** PV-Fläche an.

Bei Ost/West, mehreren Wechselrichtern oder unterschiedlich geneigten Flächen anschließend im Dashboard unter **Config** weitere `pvforecast.planes` ergänzen.

## 9. Was EOS vom Cerbo liest

Unter anderem:

- AC-gekoppelte PV-Leistung
- DC-PV / Victron MPPT
- Netzleistung
- AC-Verbrauch
- Batterieleistung
- Batterie-SoC

EOS bildet aus der PV-Istleistung einen lokalen kumulativen Zähler:

```text
victron_pv_emr [kWh]
```

Dieser wird automatisch für die kurzfristige Korrektur der PV-Prognose verwendet.

## 10. Prognosekorrektur

Der Victron-spezifische PVLib-Provider nutzt das letzte abgeschlossene 15-Minuten-Fenster und vergleicht die gemessene PV-Energie mit der modellierten PV-Energie.

Der Korrekturfaktor ist begrenzt und klingt mit zunehmendem Prognosehorizont wieder in Richtung der physikalischen Wetter-/PVLib-Prognose ab.

Direkt nach dem ersten Start kann deshalb noch keine Istwertkorrektur sichtbar sein: Zunächst muss EOS genügend aktuelle Cerbo-Messwerte sammeln.

## 11. Update

Für Updates ist kein Git-Pull und kein lokaler Build nötig.

1. Container-Manager-Projekt stoppen.
2. `ghcr.io/maxx3105/eos-victron:latest` aktualisieren/herunterladen.
3. Projekt erneut erstellen bzw. starten.

Nicht löschen:

```text
/volume1/docker/eos-victron/synology-data/
```

Die Browser-Konfiguration bleibt dadurch erhalten.

## 12. Backup

Für EOS ist vor allem dieser Ordner zu sichern:

```text
/volume1/docker/eos-victron/synology-data/
```

Diesen Ordner in **Hyper Backup** aufnehmen.

Optional zusätzlich sichern:

```text
/volume1/docker/eos-victron/docker-compose.yml
```

Das Container-Image selbst muss nicht gesichert werden, weil es erneut aus GHCR geladen werden kann.

## 13. Wiederherstellung

1. Container Manager installieren.
2. `/volume1/docker/eos-victron` anlegen.
3. `docker-compose.yml` wiederherstellen.
4. `synology-data` aus dem Backup zurückkopieren.
5. Projekt erstellen/starten.

EOS lädt das Image erneut und verwendet die vorhandene persistente Konfiguration und Messhistorie.

## 14. Fehlerbehebung

### Image kann nicht geladen werden

Bei `denied`, `unauthorized` oder `manifest unknown` prüfen:

- GitHub Actions im Fork aktiviert?
- `docker-build` erfolgreich gelaufen?
- GHCR-Paket `eos-victron` öffentlich?
- NAS hat Internet- und DNS-Zugriff?

### Dashboard nicht erreichbar

Prüfen:

- Container läuft?
- NAS-Firewall erlaubt Port 8504?
- Port 8504 bereits belegt?

Bei einer Kollision können die Host-Ports in `docker-compose.yml` geändert werden:

```yaml
ports:
  - "18503:8503"
  - "18504:8504"
```

Dann ist das Dashboard unter `http://NAS-IP:18504` erreichbar.

### Cerbo nicht erreichbar

Im Container-Protokoll auf Meldungen wie

```text
Cannot connect to Victron GX ...:502
```

achten.

Prüfen:

- IP-Adresse im Browser-Assistenten korrekt?
- Modbus TCP am Cerbo aktiviert?
- Port 502 zwischen NAS und Cerbo erreichbar?
- Firewall/VLAN-Regeln?
- `com.victronenergy.system` vorhanden?
- Unit ID 100 korrekt?

Die Cerbo-IP kann jederzeit erneut über die Schnelleinrichtung oder detailliert unter **Config -> adapter.victron.host** geändert werden.

### Prognose fehlt

Prüfen:

- Standort korrekt?
- PV-Daten vollständig?
- Internetzugriff zu Open-Meteo?
- unter Config steht `weather.provider = OpenMeteo`?
- unter Config steht `pvforecast.provider = PVForecastPVLibVictron`?

### NAS war länger ausgeschaltet

Lange Datenlücken werden bewusst nicht mit der zuletzt bekannten PV-Leistung hochgerechnet. Dadurch entstehen keine künstlichen PV-Energiezählerstände.

## 15. Sicherheit

Nicht direkt ins Internet weiterleiten:

```text
502   Victron Modbus TCP
8503  EOS API
8504  EOS Dashboard
```

Für externen Zugriff VPN oder einen korrekt abgesicherten HTTPS-Reverse-Proxy verwenden.

Wenn Venus OS die Option anbietet:

```text
Modbus TCP -> Access permissions -> Read-only
```

Die aktuelle Victron-Integration bleibt damit eine lokale, lesende Mess- und Prognoselösung.
