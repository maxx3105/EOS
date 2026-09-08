# EOS + Victron Cerbo GX auf Synology DS920+

Diese Anleitung richtet den EOS-Fork als **PV-Prognoseserver auf einer Synology DS920+** ein und verbindet ihn **direkt und nur lesend** mit einem Victron Cerbo GX.

Der Datenweg ist bewusst einfach:

```text
Open-Meteo (15-min Wetter)
          |
          v
        PVLib --------------+
          |                 |
          v                 |
15-min PV-Prognose          |
                            |
Cerbo GX -- Modbus TCP -----+
  |  PV Ist-Leistung
  |  Netz / Last
  |  Batterie / SoC
  v
lokaler PV-kWh-Zaehler
          |
          v
Istwert-Korrektur der PV-Prognose
```

Es werden **kein Home Assistant, kein Node-RED und kein MQTT-Broker** benoetigt.

> **Sicherheit:** Der Victron-Adapter in diesem Fork fuehrt nur Modbus-Lesezugriffe aus. Er schreibt keine ESS-Sollwerte und veraendert keine Cerbo-/Wechselrichter-Einstellungen.

## 1. Voraussetzungen

Du brauchst:

- Synology DS920+ mit DSM und einer fuer das Modell kompatiblen Version von **Container Manager**.
- Cerbo GX und Synology im selben lokalen Netzwerk bzw. in Netzen, zwischen denen TCP-Port 502 erreichbar ist.
- Eine feste bzw. per DHCP reservierte IP-Adresse fuer den Cerbo GX. Beispiel: `192.168.1.50`.
- Internetzugriff der Synology fuer Open-Meteo und fuer den einmaligen Docker-Build.
- Deine PV-Anlagendaten: Standort, Modulneigung, Azimut, Modul-/Wechselrichterdaten bzw. eine passende PVLib-Konfiguration.

### Hinweis zur DS920+ und Container Manager

Synology hat die Container-Manager-Version `24.0.2-1630` fuer die DS920+ ausgeschlossen. Falls diese Version im Paket-Zentrum nicht angeboten wird, verwende `24.0.2-1606` oder eine andere fuer deine DS920+ angebotene kompatible Version. Nicht manuell eine fuer das Modell ausgeschlossene Version erzwingen.

## 2. Cerbo GX vorbereiten

Am Cerbo GX Modbus TCP aktivieren.

Je nach Venus-OS-Version befindet sich die Einstellung unter einem dieser Pfade:

```text
Einstellungen -> Integrationen -> Modbus TCP Server
```

oder bei aelteren Oberflaechen:

```text
Einstellungen -> Dienste -> Modbus TCP
```

Dann:

1. **Modbus TCP Server aktivieren**.
2. Wenn deine Venus-OS-Version eine Zugriffsberechtigung anbietet, fuer diesen Anwendungsfall vorzugsweise **Read-only / nur Lesen** einstellen.
3. Unter **Available services / Verfuegbare Dienste** nach `com.victronenergy.system` sehen.
4. Fuer die Systemdaten normalerweise **Unit ID 100** verwenden. Victron empfiehlt 100 gegenueber Unit ID 0.
5. Die IP-Adresse des Cerbo notieren.

EOS benutzt standardmaessig Port `502`.

## 3. Projektordner auf der Synology anlegen

Beispiel:

```text
/volume1/docker/eos-victron
```

Den Inhalt dieses Repository-Branches dort ablegen.

### Variante A - ohne SSH

Auf GitHub den Branch `feature/openmeteo-pv-15min` oeffnen, als ZIP herunterladen und in den Ordner `eos-victron` entpacken.

### Variante B - mit SSH

```bash
git clone --branch feature/openmeteo-pv-15min \
  https://github.com/maxx3105/EOS.git \
  /volume1/docker/eos-victron
```

Nach dem Merge des Pull Requests kann spaeter stattdessen `main` verwendet werden.

## 4. Nur eine Konfigurationsdatei anpassen

Im Projektordner:

```bash
cp synology.env.example synology.env
```

Ohne SSH kannst du `synology.env.example` in Synology File Station kopieren und die Kopie in `synology.env` umbenennen.

In `synology.env` musst du fuer den ersten Start im Wesentlichen nur diese Werte anpassen:

```dotenv
# Standort deiner PV-Anlage
EOS_GENERAL__LATITUDE=48.2082
EOS_GENERAL__LONGITUDE=16.3738

# IP des Cerbo GX
EOS_ADAPTER__VICTRON__HOST=192.168.1.50

# Diesen Wert durch eine eigene lange Zufallszeichenfolge ersetzen
EOS_SERVER__EOSDASH_SESSKEY=change-me-to-a-long-random-string
```

Die restlichen Victron-Vorgaben koennen fuer eine typische Anlage zunaechst so bleiben:

```dotenv
EOS_ADAPTER__PROVIDER=["Victron"]
EOS_ADAPTER__VICTRON__PORT=502
EOS_ADAPTER__VICTRON__UNIT_ID=100
EOS_ADAPTER__VICTRON__INCLUDE_AC_COUPLED_PV=true
EOS_EMS__MODE=PREDICTION
EOS_EMS__INTERVAL=300
EOS_WEATHER__WEATHER_PROVIDER=OpenMeteo
EOS_PVFORECAST__PVFORECAST_PROVIDER=PVForecastPVLib
```

`PREDICTION` ist fuer die erste Installation absichtlich der Standard. EOS liest damit Cerbo-Daten und erstellt Prognosen, ohne eine Speicher-/Verbraucheroptimierung an Victron zu schicken.

## 5. In Synology Container Manager installieren

1. **Container Manager -> Projekt -> Erstellen** oeffnen.
2. Projektname: `eos-victron`.
3. Als Pfad den Projektordner auswaehlen, z. B. `/volume1/docker/eos-victron`.
4. Als Quelle die Datei `docker-compose.synology.yaml` hochladen. Falls die Synology-Oberflaeche zwingend den Namen `docker-compose.yml` verlangt, den Inhalt von `docker-compose.synology.yaml` im integrierten Editor einfuegen.
5. Projekt erstellen und **Build / Erstellen** ausfuehren. Das Image wird direkt aus deinem Fork gebaut.
6. Projekt **Starten**.

Die Daten werden dauerhaft unter

```text
/volume1/docker/eos-victron/synology-data
```

gespeichert. Ein neuer Container oder ein Rebuild loescht diese Daten daher nicht.

## 6. EOS oeffnen

Im Browser:

```text
EOS Dashboard: http://DEINE-NAS-IP:8504
EOS API:       http://DEINE-NAS-IP:8503
API Docs:      http://DEINE-NAS-IP:8503/docs
```

Beispiel:

```text
http://192.168.1.20:8504
```

## 7. PV-Anlage in EOS eintragen

Fuer eine korrekte PVLib-Prognose muessen die Dach-/PV-Flaechen in EOS konfiguriert sein. Pro Flaeche sind insbesondere relevant:

- `surface_tilt`: Modulneigung in Grad.
- `surface_azimuth`: Ausrichtung; bei PVLib typischerweise 0=Norden, 90=Osten, 180=Sueden, 270=Westen.
- Modulmodell.
- Wechselrichtermodell.
- Module pro String.
- Strings pro Wechselrichter.

Bei mehreren Dachflaechen (z. B. Ost/West) jede Flaeche separat anlegen. EOS summiert die PVLib-Ergebnisse.

## 8. Victron-Verbindung pruefen

In Container Manager die Protokolle des Containers `eos-victron` oeffnen.

Bei erfolgreicher Verbindung erscheint sinngemaess:

```text
Victron GX: PV=4200 W, grid=-350 W, load=1100 W, battery=2750 W, SoC=72 %
```

Der Adapter liest aus dem Victron-System unter anderem:

- gesamte PV-Istleistung (AC-gekoppelte PV plus DC-PV),
- Netzleistung,
- AC-Verbrauch,
- Batterieleistung,
- Batterie-SoC.

Aus der PV-Istleistung erzeugt EOS selbst den kumulativen Messwert:

```text
victron_pv_emr   [kWh]
```

Dieser wird automatisch in `measurement.pv_production_emr_keys` eingetragen und steht dadurch der PV-Prognosekorrektur zur Verfuegung.

## 9. Wie die Prognosekorrektur arbeitet

EOS vergleicht die gemessene PV-Energie der letzten Stunde mit der PVLib-Prognose fuer dasselbe Zeitfenster.

Vereinfacht:

```text
Korrekturfaktor = gemessene PV-Energie / modellierte PV-Energie
```

Der Faktor wird auf einen sicheren Bereich begrenzt und wirkt vor allem auf die kurzfristige Prognose. Mit zunehmendem Prognosehorizont klingt die Korrektur wieder in Richtung des physikalischen Wetter-/PV-Modells ab.

Die Korrektur wird nicht angewendet, wenn zum Beispiel:

- noch nicht genug aktuelle Messdaten vorhanden sind,
- die Messdaten zu alt sind,
- ein Zaehlerreset erkannt wird,
- die modellierte PV-Leistung fuer eine stabile Quotientenbildung zu klein ist.

## 10. AC-PV, MPPT und gemischte Anlagen

Standard:

```dotenv
EOS_ADAPTER__VICTRON__INCLUDE_AC_COUPLED_PV=true
```

Damit wird die vom Victron-Systemdienst gemeldete AC-gekoppelte PV zusammen mit der DC-gekoppelten PV beruecksichtigt. Das ist fuer ESS-Anlagen mit beispielsweise Fronius-/AC-PV plus Victron-MPPT sinnvoll.

Wenn deine Anlage bewusst **nur den DC-PV-Wert** verwenden soll:

```dotenv
EOS_ADAPTER__VICTRON__INCLUDE_AC_COUPLED_PV=false
```

## 11. Fehlerbehebung

### `Cannot connect to Victron GX ...:502`

Pruefen:

- stimmt `EOS_ADAPTER__VICTRON__HOST`?
- ist der Cerbo eingeschaltet und vom NAS erreichbar?
- ist Modbus TCP am Cerbo aktiviert?
- blockiert Firewall/VLAN TCP-Port 502?

### `Modbus exception` / falsche Unit ID

Am Cerbo unter **Available services / Verfuegbare Dienste** kontrollieren, welche Unit ID fuer `com.victronenergy.system` angezeigt wird. Standard und Victron-Empfehlung ist 100.

### Victron-Daten sind da, aber noch keine Istwertkorrektur

EOS benoetigt ein zusammenhaengendes aktuelles Messfenster. Direkt nach einer Neuinstallation bzw. wenn die NAS zuvor ausgeschaltet war, bleibt deshalb zunaechst die reine PVLib-Prognose aktiv. Sobald ein ausreichendes valides Messfenster vorliegt, wird die Korrektur automatisch verwendet.

### NAS war laenger ausgeschaltet

Der Adapter integriert einen langen Daten-Ausfall absichtlich **nicht** nachtraeglich als PV-Energie. Dadurch wird verhindert, dass die zuletzt bekannte Leistung ueber die gesamte Ausfallzeit hochgerechnet wird.

### Container startet nach Reboot nicht

Das Compose-Projekt verwendet:

```yaml
restart: unless-stopped
```

Falls es trotzdem gestoppt ist, in **Container Manager -> Projekt** den Projektstatus und das Container-Protokoll pruefen.

## 12. Aktualisieren

Bei Git-Installation:

```bash
cd /volume1/docker/eos-victron
git pull
```

Anschliessend in Container Manager beim Projekt **Build** und danach **Start/Neu starten** ausfuehren.

Bei ZIP-Installation die Programmdateien durch die neue Version ersetzen, aber diese lokalen Dateien/Ordner behalten:

```text
synology.env
synology-data/
```

## 13. Backup

Fuer eine einfache Sicherung genuegt es, mindestens folgenden Ordner in Hyper Backup aufzunehmen:

```text
/volume1/docker/eos-victron/synology-data
```

Zusaetzlich `synology.env` sichern, da dort deine lokale Konfiguration steht.

## 14. Netzwerksicherheit

- Cerbo-Modbus-Port `502` **nicht ins Internet weiterleiten**.
- EOS-Ports `8503` und `8504` ebenfalls nicht direkt per Router-Portfreigabe veroeffentlichen.
- Fuer externen Zugriff besser VPN bzw. eine abgesicherte Reverse-Proxy-Loesung verwenden.
- Wenn Venus OS die Option anbietet, fuer diese Integration **Read-only** als Modbus-Zugriffsberechtigung setzen.

Damit bleibt die erste Ausbaustufe bewusst eine lokale, lesende Mess- und Prognoseloesung. Eine spaetere aktive ESS-Steuerung sollte separat, explizit und mit eigenen Sicherheitsgrenzen implementiert werden.
