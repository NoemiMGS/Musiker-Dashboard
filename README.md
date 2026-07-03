# Musiker-Ausschreibungs-Agent

Durchsucht täglich mehrere Plattformen nach Ausschreibungen, Festen und
Veranstaltungen im Umkreis von Regensburg, bei denen Musiker gesucht werden,
und zeigt die Treffer in einem Web-Dashboard an.

## Was du bekommst

- `scraper.py` – das eigentliche Suchskript
- `config.yaml` – Einstellungen (Standort, Radius, Genres, Quellen)
- `docs/index.html` – das Dashboard (wird per GitHub Pages veröffentlicht)
- `.github/workflows/daily-scrape.yml` – automatischer täglicher Lauf
- `data/results.json` – die aktuellen Treffer (wird automatisch aktualisiert)

## Einmalige Einrichtung (ca. 10–15 Minuten)

### 1. GitHub-Account anlegen
Falls noch nicht geschehen: auf **github.com** registrieren (kostenlos).

### 2. Neues Repository erstellen
- Auf github.com auf **"New repository"** klicken
- Name z.B. `musiker-agent`
- Sichtbarkeit: **Public** (nötig für die kostenlose GitHub-Pages-Funktion in
  der Basisversion; falls dir das nicht recht ist, sag Bescheid — es gibt
  auch eine Private-Variante mit GitHub Pro)
- "Create repository" klicken

### 3. Dateien hochladen
- Im neuen Repository auf **"uploading an existing file"** klicken
- Alle Dateien und Ordner aus diesem Paket hineinziehen (Ordnerstruktur bleibt
  erhalten, wenn du den ganzen Ordnerinhalt auf einmal hochlädst)
- Commit-Nachricht z.B. "Initial setup" und bestätigen

### 4. GitHub Pages aktivieren
- Im Repository auf **Settings → Pages**
- Unter "Build and deployment" → Source: **"Deploy from a branch"**
- Branch: **main**, Ordner: **/docs**
- Speichern. Nach ein paar Minuten ist das Dashboard erreichbar unter:
  `https://DEIN-BENUTZERNAME.github.io/musiker-agent/`

### 5. Actions aktivieren
- Im Repository auf **Actions** klicken
- Falls gefragt: Workflows aktivieren (bei manchen Accounts Standard bereits aktiv)
- Der Workflow "Täglicher Musiker-Agent-Lauf" läuft ab jetzt automatisch
  jeden Tag um 06:00 UTC. Du kannst ihn auch manuell testen:
  Actions → "Täglicher Musiker-Agent-Lauf" → **"Run workflow"**

### 6. Ersten Testlauf prüfen
Nach dem ersten Lauf (automatisch oder manuell gestartet):
- Prüfe unter **Actions**, ob der Lauf grün (erfolgreich) ist
- Öffne dein Dashboard unter dem GitHub-Pages-Link
- Falls eine Quelle 0 Treffer liefert, obwohl du welche erwartest: siehe
  Abschnitt "Wartung" unten

## Konfiguration anpassen

Öffne `config.yaml` direkt auf GitHub (Datei anklicken → Stift-Symbol zum
Bearbeiten) und passe an:

- **Radius/Standort:** unter `standorte:` den `radius_km`-Wert ändern oder
  weitere Standorte hinzufügen
- **Genres/Suchbegriffe:** unter `profile: genres:` ergänzen oder entfernen
- **Ausschlussbegriffe:** unter `profile: ausschluss_begriffe:`
- **Quellen ein/ausschalten:** unter `quellen:` jeweils `aktiv: true/false`

Nach dem Speichern übernimmt der nächste automatische Lauf die neuen Einstellungen.

## Wichtiger Hinweis zu den Webseiten-Selektoren

Die Skripte lesen die HTML-Struktur der jeweiligen Plattformen aus. Ändert
eine Plattform ihr Layout, kann es sein, dass eine Quelle plötzlich 0 Treffer
liefert. In `scraper.py` sind die entsprechenden Stellen mit `# TODO`
markiert. Melde dich einfach, wenn eine Quelle "leerläuft" — das lässt sich
in der Regel schnell nachjustieren.

## Rechtliche Hinweise (wichtig)

- Der Agent prüft vor jedem Zugriff automatisch die `robots.txt` der
  jeweiligen Seite. Ist Scraping dort explizit untersagt, wird die Quelle für
  diesen Lauf übersprungen (kein Umgehen von Sperren).
- Nur öffentlich einsehbare, nicht login-pflichtige Seitenbereiche werden
  angefragt.
- Zwischen den Anfragen wird eine Pause eingehalten (Netiquette, siehe
  `request_delay_sekunden` in `config.yaml`).
- Trotzdem gilt: Nutzungsbedingungen können sich ändern. Bei Unsicherheit zu
  einer bestimmten Plattform lohnt sich ein kurzer Blick in deren aktuelle
  AGB, insbesondere wenn du die Daten kommerziell nutzen möchtest (z.B. als
  Vermittlungsangebot).

## Erweiterungsideen für später

- Weitere Quellen ergänzen (z.B. lokale Gemeinde-Veranstaltungskalender,
  Amtsblätter)
- E-Mail-Digest zusätzlich zum Dashboard (z.B. via GitHub Actions + SMTP)
- Mehrere Standorte/Profile parallel (z.B. für verschiedene Bands)
- Automatische Umkreisberechnung per Geocoding statt reiner Textfilterung
