# EOS + Victron Cerbo GX auf Synology DS920+

Diese Installation ist auf **möglichst wenige Schritte** reduziert.

Du brauchst **kein GitHub-Konto, kein GitHub Actions, kein GHCR, keine ENV-Datei, kein SSH und kein Git**.

```text
1 Datei herunterladen
        ↓
Container Manager → Projekt → Erstellen
        ↓
docker-compose.yml hochladen
        ↓
Projekt erstellen/starten
        ↓
http://NAS-IP:8504 öffnen
        ↓
Standort + Cerbo + PV-Anlage im Browser eintragen
        ↓
fertig
```

Der Container wird beim ersten Erstellen automatisch direkt aus dem öffentlichen `main`-Branch dieses Forks gebaut. Docker unterstützt öffentliche Git-Repositories als Build-Kontext; dadurch ist kein separates Container-Registry-Image nötig.

> Der Victron-Adapter arbeitet in dieser Ausbaustufe nur lesend. EOS schreibt keine ESS-Sollwerte und verändert keine Cerbo- oder Wechselrichter-Einstellungen.

## 1. Cerbo GX vorbereiten

Am Cerbo GX den **Modbus TCP Server** aktivieren.

Je nach Venus-OS-Version findest du die Einstellung unter:

```text
Einstellungen → Integrationen → Modbus TCP Server
```

oder bei älteren Versionen unter:

```text
Einstellungen → Dienste → Modbus TCP
```

Danach:

1. Modbus TCP aktivieren.
2. Wenn verfügbar **Read-only / Nur Lesen** auswählen.
3. `com.victronenergy.system` prüfen.
4. Normalerweise **Unit ID 100** verwenden.
5. IP-Adresse des Cerbo notieren, z. B. `192.168.1.50`.

Standard-Port ist TCP `502`.

## 2. Eine einzige Datei herunterladen

Lade aus dem `main`-Branch diese Datei herunter:

```text
synology/docker-compose.yml
```

Die Datei heißt bereits korrekt `docker-compose.yml`. Du musst sie nicht bearbeiten.

Sie enthält:

- den automatischen Build direkt aus `https://github.com/maxx3105/EOS.git#main`
- Port `8503` für die API
- Port `8504` für EOSdash
- persistenten Speicher in `./synology-data`
- automatische Neustarts

## 3. Projekt in Container Manager erstellen

In DSM:

```text
Container Manager
→ Projekt
→ Erstellen
```

Eintragen:

```text
Projektname: eos-victron
```

Als Projektpfad zum Beispiel:

```text
/volume1/docker/eos-victron
```

Bei **Quelle** die heruntergeladene `docker-compose.yml` hochladen.

Danach das Projekt erstellen und starten.

Beim ersten Erstellen lädt Docker den Quellcode und die benötigten Basis-Images und baut EOS lokal auf der DS920+. Das dauert beim ersten Mal länger als ein normaler Container-Start, erfordert aber keinerlei GitHub- oder Registry-Einrichtung.

## 4. EOS im Browser öffnen

Wenn die Synology beispielsweise die IP `192.168.1.20` hat:

```text
http://192.168.1.20:8504
```

Zusätzlich:

```text
API:      http://192.168.1.20:8503
API-Doku: http://192.168.1.20:8503/docs
```

Auf der Startseite erscheint die **Schnelleinrichtung: Synology + Victron Cerbo GX**.

## 5. Browser-Assistent ausfüllen

Der Assistent fragt nur die für die erste Prognose nötigen Daten ab.

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

Danach auf **Einrichtung speichern** klicken.

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

Die Konfiguration wird unter `/data` gespeichert und liegt damit dauerhaft im NAS-Ordner:

```text
/volume1/docker/eos-victron/synology-data/
```

## 6. Mehrere Dachflächen

Die Schnelleinrichtung legt bewusst zunächst eine PV-Fläche an.

Bei Ost/West-Anlagen oder mehreren Wechselrichtern können anschließend unter **Config** weitere `pvforecast.planes` ergänzt werden.

## 7. Was EOS vom Cerbo liest

EOS liest unter anderem:

- AC-gekoppelte PV-Leistung
- DC-PV / Victron MPPT
- Netzleistung
- Hausverbrauch
- Batterieleistung
- Batterie-SoC

Aus der PV-Istleistung erzeugt EOS den kumulativen Messwert:

```text
victron_pv_emr [kWh]
```

Dieser Messwert wird für die laufende Korrektur der kurzfristigen PV-Prognose verwendet.

## 8. Update

Auch Updates brauchen kein Git und kein Registry-Image.

In Container Manager:

```text
Projekt → eos-victron → Aktion → Erstellen
```

Da der Build-Kontext auf `main` zeigt, lädt Docker dabei den aktuellen Stand des Forks und baut das Image neu.

Danach das Projekt starten bzw. neu starten.

Nicht löschen:

```text
/volume1/docker/eos-victron/synology-data/
```

Dort liegen Konfiguration und Messhistorie.

## 9. Backup

Für ein vollständiges EOS-Backup reicht im Wesentlichen:

```text
/volume1/docker/eos-victron/synology-data/
```

Diesen Ordner in **Hyper Backup** aufnehmen.

Optional zusätzlich die `docker-compose.yml` sichern. Sie kann aber jederzeit erneut aus dem Repository geladen werden.

## 10. Wiederherstellung

1. Container Manager installieren.
2. Projektordner `/volume1/docker/eos-victron` anlegen.
3. `docker-compose.yml` erneut herunterladen.
4. `synology-data` aus dem Backup zurückkopieren.
5. Projekt in Container Manager erstellen/starten.

EOS verwendet danach wieder die vorhandene Konfiguration und Messhistorie.

## 11. Fehlerbehebung

### Build schlägt fehl

Prüfen:

- NAS hat Internetzugriff.
- DNS funktioniert.
- GitHub und Docker Hub sind von der NAS erreichbar.
- genügend freier Speicher vorhanden.

Danach in Container Manager erneut **Aktion → Erstellen** ausführen.

### Dashboard ist nicht erreichbar

Prüfen:

- Container läuft.
- NAS-Firewall erlaubt Port `8504`.
- Port `8504` ist nicht bereits belegt.

Bei einer Portkollision in der Compose-Datei beispielsweise ändern:

```yaml
ports:
  - "18503:8503"
  - "18504:8504"
```

Dann ist EOS unter `http://NAS-IP:18504` erreichbar.

### Cerbo ist nicht erreichbar

Im Container-Protokoll auf Meldungen wie

```text
Cannot connect to Victron GX ...:502
```

achten.

Prüfen:

- Cerbo-IP im Browser-Assistenten korrekt?
- Modbus TCP aktiviert?
- Port `502` erreichbar?
- `com.victronenergy.system` vorhanden?
- Unit ID `100` korrekt?
- Firewall oder VLAN blockiert die Verbindung?

### Noch keine Istwertkorrektur

Direkt nach dem ersten Start fehlen historische Cerbo-Messungen. EOS verwendet zunächst die reine PVLib-Prognose. Sobald genügend aktuelle Messwerte vorhanden sind, wird die Istwertkorrektur automatisch wirksam.

### NAS war länger ausgeschaltet

Lange Datenlücken werden nicht mit der letzten bekannten PV-Leistung hochgerechnet. Dadurch entstehen keine künstlich falschen Energiezählerstände.

## 12. Sicherheit

Nicht direkt ins Internet weiterleiten:

```text
502   Victron Modbus TCP
8503  EOS API
8504  EOS Dashboard
```

Für externen Zugriff besser VPN oder einen korrekt abgesicherten HTTPS-Reverse-Proxy verwenden.

Wenn Venus OS die Option anbietet:

```text
Modbus TCP → Access permissions → Read-only
```

Damit bleibt die aktuelle Victron-Integration eine lokale, lesende Mess- und Prognoselösung.
