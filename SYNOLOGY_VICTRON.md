# EOS + Victron Cerbo GX auf Synology DS920+

Ziel dieser Variante ist eine Installation wie bei einem normalen Docker-Image:

```text
Container Manager
→ Registrierung
→ maxx3105/eos suchen
→ herunterladen
→ ausführen
→ http://NAS-IP:8504 öffnen
→ Anlage im Browser einrichten
```

Für Endanwender werden **kein GitHub-Konto, kein Git, kein SSH, kein Compose und keine ENV-Datei** benötigt.

Das öffentliche Docker-Hub-Image lautet:

```text
maxx3105/eos:latest
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

## 2. Image im Synology Container Manager suchen

DSM öffnen:

```text
Container Manager
→ Registrierung
```

Nach folgendem Image suchen:

```text
maxx3105/eos
```

Das Image auswählen und herunterladen.

Als Tag verwenden:

```text
latest
```

Die DS920+ verwendet automatisch die `linux/amd64`-Variante des Multi-Arch-Images.

## 3. Container starten

Nach dem Download:

```text
Container Manager
→ Image
→ maxx3105/eos:latest
→ Ausführen
```

Containername zum Beispiel:

```text
eos
```

### Ports

Diese Ports zuordnen:

```text
Lokaler Port 8503 → Container-Port 8503
Lokaler Port 8504 → Container-Port 8504
```

### Persistenter Speicher

In File Station zunächst beispielsweise anlegen:

```text
/volume1/docker/eos
```

Diesen Ordner im Container als Volume einbinden:

```text
/volume1/docker/eos → /data
```

Dadurch bleiben Konfiguration, Datenbank und Messhistorie bei Image-Updates erhalten.

Weitere Umgebungsvariablen sind für die Standardinstallation nicht nötig.

Container anschließend starten.

## 4. EOS im Browser öffnen

Wenn die Synology beispielsweise `192.168.1.20` hat:

```text
http://192.168.1.20:8504
```

Zusätzlich:

```text
API:      http://192.168.1.20:8503
API-Doku: http://192.168.1.20:8503/docs
```

Das Docker-Image bindet API und Dashboard bereits standardmäßig auf alle Container-Netzwerkschnittstellen, damit keine zusätzlichen Docker-Variablen gesetzt werden müssen.

## 5. Browser-Schnelleinrichtung

Auf der EOSdash-Startseite befindet sich die **Schnelleinrichtung: Synology + Victron Cerbo GX**.

Dort werden eingetragen:

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

## 6. Mehrere Dachflächen

Die Schnelleinrichtung legt zunächst eine PV-Fläche an.

Für Ost/West-Anlagen oder mehrere Wechselrichter können anschließend unter **Config** weitere `pvforecast.planes` ergänzt werden.

## 7. Update

In Container Manager:

```text
Registrierung
→ maxx3105/eos
→ latest erneut herunterladen
```

Danach den bestehenden Container mit dem neuen Image neu erstellen bzw. aktualisieren.

Der Ordner

```text
/volume1/docker/eos
```

bleibt erhalten und wird wieder nach `/data` eingebunden.

## 8. Backup

Für das EOS-Backup reicht im Wesentlichen:

```text
/volume1/docker/eos/
```

Diesen Ordner in **Hyper Backup** aufnehmen.

Das Image selbst muss nicht gesichert werden; es kann erneut über Container Manager heruntergeladen werden.

## 9. Fehlerbehebung

### `maxx3105/eos` wird in der Registrierung nicht gefunden

Prüfen, ob das Docker-Hub-Repository öffentlich ist und mindestens ein Tag wie `latest` veröffentlicht wurde.

### Dashboard nicht erreichbar

Prüfen:

- Container läuft?
- Port `8504` wurde auf den Host gemappt?
- NAS-Firewall erlaubt Port `8504`?
- Port `8504` ist nicht bereits belegt?

Falls `8504` belegt ist, kann als lokaler Port z. B. `18504` verwendet werden:

```text
Lokaler Port 18504 → Container-Port 8504
```

Dann lautet die Adresse:

```text
http://NAS-IP:18504
```

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

## 10. Sicherheit

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
