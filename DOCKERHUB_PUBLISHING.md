# Einmalige Docker-Hub-Einrichtung für `maxx3105/eos`

Diese Schritte sind **nur einmal für den Maintainer** nötig. Endanwender brauchen danach nur noch Synology Container Manager und suchen dort nach `maxx3105/eos`.

## 1. Öffentliches Docker-Hub-Repository anlegen

Bei Docker Hub mit dem Benutzer `maxx3105` anmelden und ein neues öffentliches Repository anlegen:

```text
Repository: eos
Visibility: Public
```

Das vollständige Image lautet danach:

```text
maxx3105/eos
```

## 2. Docker-Hub-Token erzeugen

Unter Docker Hub einen Personal Access Token für CI/CD erzeugen. Er benötigt mindestens **Read & Write**.

Den Token nicht in Dateien, Commits, Issues oder Chats einfügen.

## 3. Token in GitHub hinterlegen

Im Repository `maxx3105/EOS`:

```text
Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

Name:

```text
DOCKERHUB_TOKEN
```

Als Wert den Docker-Hub-Token einsetzen.

## 4. GitHub Actions aktivieren

Falls Actions im Fork noch deaktiviert sind:

```text
Actions
→ Workflows aktivieren
```

Danach den Workflow `docker-build` einmal manuell über **Run workflow** auf `main` starten oder einen neuen Commit auf `main` pushen.

## 5. Ergebnis

Der Workflow baut automatisch beide Plattformen:

```text
linux/amd64
linux/arm64
```

und veröffentlicht auf Docker Hub unter anderem:

```text
maxx3105/eos:latest
maxx3105/eos:main
maxx3105/eos:sha-...
```

Bei Releases/TAGs wie `v1.2.3` werden zusätzlich passende Versions-Tags erzeugt.

Sobald `latest` erfolgreich veröffentlicht wurde und das Repository öffentlich ist, können Synology-Nutzer in **Container Manager → Registrierung** nach `maxx3105/eos` suchen, das Image herunterladen und ohne GitHub-/Compose-Schritte starten.
