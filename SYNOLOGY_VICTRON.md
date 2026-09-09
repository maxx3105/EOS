# EOS + Victron Cerbo GX auf Synology DS920+

Diese Anleitung beschreibt den einfachen Standardweg für den Fork `maxx3105/EOS`.

Die Synology benötigt nur **eine Compose-Datei**. Es werden **kein Git, kein SSH, keine GitHub Actions, kein eigenes Container-Registry-Image und keine ENV-Datei** benötigt.

```text
1 Datei: docker-compose.yml
        ↓
Container Manager → Projekt → Erstellen
        ↓
öffentliches EOS-Basisimage wird geladen
        ↓
aktueller Fork-Quellcode aus main wird automatisch eingespielt
        ↓
Docker legt den persistenten Datenspeicher selbst an
        ↓
http://NAS-IP:18504 öffnen
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

## 2. Projektordner auf der Synology

In **File Station** nur diesen Ordner anlegen:

```text
/volume1/docker/eos-victron
```

Dort liegt lediglich:

```text
/volume1/docker/eos-victron/
└── docker-compose.yml
```

Ein zusätzlicher Datenordner muss **nicht** manuell angelegt werden. Container Manager erzeugt automatisch das Docker-Volume:

```text
eos-victron-data
```

Darin liegen die persistenten EOS-Daten unter `/data`.

## 3. Compose-Datei herunterladen

Verwende aus `main` entweder:

```text
synology/docker-compose.yml
```

oder die identische Datei:

```text
docker-compose.synology.yaml
```

Auf der NAS als `docker-compose.yml` speichern.

Die aktuelle Datei verwendet:

```yaml
image: akkudoktor/eos:latest
```

und lädt beim Containerstart automatisch den aktuellen Fork-Quellcode aus `main`. Dadurch wird auf der Synology kein `git` benötigt.

Die Daten werden über ein Docker-Volume eingebunden:

```yaml
volumes:
  - eos-victron-data:/data
```

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

Beim ersten Start lädt Container Manager zunächst `akkudoktor/eos:latest`. Danach sollte im Container-Protokoll erscheinen:

```text
EOS Victron: lade aktuellen Fork-Stand von main ...
EOS Victron: Fork-Quellcode erfolgreich geladen.
```

## 5. EOS öffnen

Standardmäßig verwendet die Synology-Variante bewusst die Host-Ports `18503` und `18504`, um Kollisionen mit anderen Diensten zu vermeiden.

Wenn die NAS z. B. `192.168.178.93` hat:

```text
Dashboard: http://192.168.178.93:18504
API:       http://192.168.178.93:18503
API-Doku:  http://192.168.178.93:18503/docs
```

## 6. Browser-Schnelleinrichtung

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

## 7. Mehrere Dachflächen

Die Schnelleinrichtung legt zunächst eine PV-Fläche an. Für Ost/West-Anlagen oder mehrere Wechselrichter können anschließend unter **Config** weitere `pvforecast.planes` ergänzt werden.

## 8. Update

Projekt im Container Manager neu erstellen. Beim Start wird der aktuelle Quellcode von `main` erneut geladen.

Das Docker-Volume

```text
eos-victron-data
```

nicht löschen. Darin bleiben Konfiguration und Messhistorie erhalten.

## 9. Backup

Für ein vollständiges Backup müssen die Daten aus dem Docker-Volume `eos-victron-data` gesichert werden. Die Compose-Datei zusätzlich sichern.

Wichtig: Beim Löschen oder Zurücksetzen des Projekts **nicht** die Option wählen, die zugehörige Volumes löscht.

## 10. Fehlerbehebung

### `pull access denied for maxx3105/eos`

Alte Compose-Datei aktiv. Aktuelle YAML aus `main` übernehmen.

### `unable to find 'git'`

Alte Git-Build-Compose aktiv. Aktuelle YAML aus `main` übernehmen.

### `Bind mount failed ... synology-data`

Alte Compose-Datei mit einem lokalen Ordner-Mount aktiv. Die aktuelle Version verwendet stattdessen das automatisch angelegte Docker-Volume `eos-victron-data`.

### `driver failed programming external connectivity`

Meist ist ein Host-Port belegt. Die aktuelle Synology-Datei verwendet deshalb bereits:

```yaml
ports:
  - "18503:8503"
  - "18504:8504"
```

### Fork-Download schlägt fehl

Prüfen:

- NAS hat Internetzugriff
- DNS funktioniert
- `github.com` ist erreichbar

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

## 11. Sicherheit

Nicht direkt ins Internet weiterleiten:

```text
502    Victron Modbus TCP
18503  EOS API
18504  EOS Dashboard
```

Für externen Zugriff besser VPN oder einen abgesicherten HTTPS-Reverse-Proxy verwenden.

Wenn Venus OS die Option anbietet:

```text
Modbus TCP → Access permissions → Read-only
```
