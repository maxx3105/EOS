# EOS + Victron Cerbo GX auf Synology DS920+

Diese Anleitung installiert EOS auf einer **Synology DS920+** mit **Container Manager** und verbindet EOS direkt und nur lesend mit einem **Victron Cerbo GX**.

Die Installation ist absichtlich einfach gehalten:

```text
2 Dateien auf die NAS kopieren
        |
        v
3 Pflichtwerte eintragen
        |
        v
Container-Manager-Projekt starten
        |
        v
fertiges Image wird aus GHCR geladen
        |
        v
EOS läuft
```

Es werden **kein Git, kein Dockerfile, kein lokaler Build, kein Home Assistant, kein Node-RED und kein MQTT-Broker** benötigt.

Das fertige Image lautet:

```text
ghcr.io/maxx3105/eos-victron:latest
```

> **Sicherheit:** Der Victron-Adapter dieser Variante führt nur Modbus-Lesezugriffe aus. Er schreibt keine ESS-Sollwerte und verändert keine Cerbo- oder Wechselrichter-Einstellungen.

## 1. Voraussetzungen

Du brauchst:

- Synology DS920+ mit einer kompatiblen Version von Container Manager
- Cerbo GX und Synology im selben lokalen Netzwerk oder per Routing erreichbar
- eine feste bzw. reservierte IP-Adresse für den Cerbo GX
- Internetzugriff der NAS für Open-Meteo und das Herunterladen des Container-Images
- später für PVLib die Daten deiner PV-Anlage: Neigung, Azimut, Modul- und Wechselrichterdaten

## 2. Cerbo GX vorbereiten

Am Cerbo GX **Modbus TCP Server** aktivieren.

Je nach Venus-OS-Version findest du die Einstellung unter:

```text
Einstellungen -> Integrationen -> Modbus TCP Server
```

oder bei älteren Versionen unter:

```text
Einstellungen -> Dienste -> Modbus TCP
```

Dann:

1. Modbus TCP Server aktivieren.
2. Wenn angeboten, die Zugriffsberechtigung auf **Read-only / nur Lesen** stellen.
3. Unter den verfügbaren Diensten `com.victronenergy.system` prüfen.
4. Für diese Systemdaten normalerweise **Unit ID 100** verwenden.
5. IP-Adresse des Cerbo notieren, zum Beispiel `192.168.1.50`.

EOS verwendet standardmäßig TCP-Port `502`.

## 3. Ordner auf der Synology anlegen

In File Station diesen Ordner anlegen:

```text
/volume1/docker/eos-victron
```

Die fertige Ordnerstruktur ist sehr klein:

```text
/volume1/docker/eos-victron/
├── docker-compose.yml
├── synology.env
└── synology-data/
```

`synology-data` wird beim ersten Start automatisch verwendet und enthält die persistenten EOS-Daten.

## 4. Zwei Dateien aus dem Repository übernehmen

Aus dem `main`-Branch dieses Repositories brauchst du nur:

```text
docker-compose.synology.yaml
synology.env.example
```

Auf der NAS benennst du sie um zu:

```text
docker-compose.yml
synology.env
```

Du musst **nicht das komplette Repository** auf die Synology kopieren.

## 5. Nur drei Pflichtwerte ändern

Öffne `synology.env`.

Für die erste Installation musst du nur diese drei Werte anpassen:

```dotenv
# 1/3 Breitengrad der PV-Anlage
EOS_GENERAL__LATITUDE=48.2082

# 2/3 Längengrad der PV-Anlage
EOS_GENERAL__LONGITUDE=16.3738

# 3/3 IP-Adresse des Cerbo GX
EOS_ADAPTER__VICTRON__HOST=192.168.1.50
```

Empfohlen ist zusätzlich ein eigener langer Session-Key:

```dotenv
EOS_SERVER__EOSDASH_SESSKEY=hier-eine-lange-zufaellige-zeichenfolge-eintragen
```

Die übrigen Werte sind bereits sinnvoll vorbelegt:

```dotenv
EOS_EMS__MODE=PREDICTION
EOS_EMS__INTERVAL=300
EOS_WEATHER__WEATHER_PROVIDER=OpenMeteo
EOS_PVFORECAST__PVFORECAST_PROVIDER=PVForecastPVLibVictron
EOS_PREDICTION__HOURS=48
EOS_ADAPTER__PROVIDER=["Victron"]
EOS_ADAPTER__VICTRON__PORT=502
EOS_ADAPTER__VICTRON__UNIT_ID=100
EOS_ADAPTER__VICTRON__INCLUDE_AC_COUPLED_PV=true
```

Damit läuft EOS alle fünf Minuten im sicheren Prediction-Modus.

## 6. Projekt in Container Manager erstellen

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

Als Compose-Datei die dort liegende `docker-compose.yml` verwenden.

Diese Datei enthält **keinen lokalen Build mehr**. Container Manager lädt automatisch:

```text
ghcr.io/maxx3105/eos-victron:latest
```

Beim ersten Start kann das Herunterladen einige Zeit beanspruchen. Die DS920+ muss dafür Internetzugriff haben.

## 7. Projekt starten

Nach dem Erstellen das Projekt starten.

Unter:

```text
Container Manager -> Container -> eos-victron -> Protokoll
```

kannst du den Start verfolgen.

Bei erfolgreicher Cerbo-Verbindung erscheint sinngemäß:

```text
Victron GX: PV=4200 W, grid=-350 W, load=1100 W, battery=2750 W, SoC=72 %
```

## 8. EOS öffnen

Angenommen die NAS hat die IP `192.168.1.20`:

```text
Dashboard: http://192.168.1.20:8504
API:       http://192.168.1.20:8503
API Docs:  http://192.168.1.20:8503/docs
```

## 9. PV-Anlage konfigurieren

Für die physikalische PVLib-Prognose müssen die PV-Flächen in EOS konfiguriert werden.

Wichtig sind pro Fläche insbesondere:

- `surface_tilt`: Modulneigung
- `surface_azimuth`: 0=Norden, 90=Osten, 180=Süden, 270=Westen
- Modulmodell
- Wechselrichtermodell
- Module pro String
- Strings pro Wechselrichter

Bei einer Ost/West-Anlage beide Flächen separat anlegen. EOS summiert deren Prognosen.

## 10. Was der Cerbo-Adapter liest

EOS liest unter anderem:

- gesamte PV-Istleistung
- Netzleistung
- AC-Verbrauch
- Batterieleistung
- Batterie-SoC

Aus der PV-Leistung erzeugt EOS den kumulativen Messwert:

```text
victron_pv_emr [kWh]
```

Dieser wird automatisch für die laufende PV-Prognosekorrektur verwendet.

## 11. AC-PV und Victron-MPPT

Standardmäßig gilt:

```dotenv
EOS_ADAPTER__VICTRON__INCLUDE_AC_COUPLED_PV=true
```

Damit berücksichtigt EOS AC-gekoppelte PV plus DC-PV/MPPT.

Wenn du bewusst nur DC-PV verwenden möchtest:

```dotenv
EOS_ADAPTER__VICTRON__INCLUDE_AC_COUPLED_PV=false
```

## 12. Update

Das Update benötigt keinen Git-Pull und keinen Build mehr.

Neue Versionen werden in GitHub automatisch als neues Image veröffentlicht:

```text
ghcr.io/maxx3105/eos-victron:latest
```

Für ein Update:

1. Projekt in Container Manager stoppen.
2. Aktuelles Image `ghcr.io/maxx3105/eos-victron:latest` erneut herunterladen bzw. aktualisieren.
3. Projekt erneut erstellen/starten, sodass das neue Image verwendet wird.

Die Daten bleiben erhalten, weil sie außerhalb des Containers unter folgendem Ordner liegen:

```text
/volume1/docker/eos-victron/synology-data
```

`synology.env` ebenfalls nicht löschen oder überschreiben.

## 13. Backup

Für ein vollständiges lokales Backup reichen im Wesentlichen:

```text
/volume1/docker/eos-victron/synology.env
/volume1/docker/eos-victron/synology-data/
```

Diese beiden Pfade am besten in Hyper Backup aufnehmen.

Die Dateien `docker-compose.yml` und das Container-Image können jederzeit erneut aus dem Repository bzw. GHCR bezogen werden.

## 14. Wiederherstellung

Nach einem NAS-Ausfall oder einer Neuinstallation:

1. Container Manager installieren.
2. `/volume1/docker/eos-victron` anlegen.
3. `docker-compose.yml` wiederherstellen.
4. `synology.env` aus dem Backup wiederherstellen.
5. `synology-data` zurückkopieren.
6. Projekt in Container Manager erstellen und starten.

Das Image wird erneut aus GHCR geladen.

## 15. Fehlerbehebung

### Image kann nicht geladen werden

Wenn bei `ghcr.io/maxx3105/eos-victron:latest` ein Fehler wie `denied` oder `unauthorized` erscheint, prüfen, ob das GHCR-Paket auf GitHub öffentlich sichtbar ist.

### `Cannot connect to Victron GX ...:502`

Prüfen:

- Cerbo-IP in `synology.env`
- Modbus TCP am Cerbo aktiviert
- Port 502 erreichbar
- NAS und Cerbo im gleichen Netz bzw. Routing korrekt
- Firewall/VLAN-Regeln

### `Modbus exception`

Am Cerbo prüfen, welche Unit ID für `com.victronenergy.system` angezeigt wird. Standardmäßig wird Unit ID 100 verwendet.

### EOS läuft, Dashboard ist nicht erreichbar

Prüfen:

- Container läuft
- NAS-Firewall
- Port 8504 ist nicht anderweitig belegt

Bei einer Portkollision kannst du in `docker-compose.yml` zum Beispiel ändern:

```yaml
ports:
  - "18503:8503"
  - "18504:8504"
```

Dann ist das Dashboard unter `http://NAS-IP:18504` erreichbar.

### Noch keine Istwertkorrektur

Direkt nach dem ersten Start fehlen zunächst historische Cerbo-Messungen. EOS verwendet dann vorübergehend die reine PVLib-Prognose. Sobald genügend zusammenhängende Messwerte vorliegen, wird die Korrektur automatisch aktiv.

### NAS war länger ausgeschaltet

Lange Datenlücken werden absichtlich nicht mit der letzten bekannten PV-Leistung hochgerechnet. Dadurch entstehen keine künstlich falschen Energiezählerstände.

## 16. Sicherheit

Nicht ins Internet weiterleiten:

```text
502   Victron Modbus TCP
8503  EOS API
8504  EOS Dashboard
```

Für externen Zugriff besser VPN oder einen korrekt abgesicherten HTTPS-Reverse-Proxy verwenden.

Am Cerbo, wenn möglich:

```text
Modbus TCP -> Access permissions -> Read-only
```

Damit bleibt diese erste Ausbaustufe eine lokale, lesende Mess- und Prognoselösung.
