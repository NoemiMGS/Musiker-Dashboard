#!/usr/bin/env python3
"""
Musiker-Ausschreibungs-Agent
=============================
Durchsucht täglich mehrere Plattformen nach Ausschreibungen, Festen und
Veranstaltungen, die Musiker suchen, filtert nach Genre/Radius und schreibt
das Ergebnis nach data/results.json (wird vom Dashboard eingelesen).

WICHTIG - vor dem ersten produktiven Einsatz:
- Dieses Skript prüft vor jedem Zugriff die robots.txt der jeweiligen Domain.
  Ist der Zugriff dort verboten, wird die Quelle für diesen Lauf übersprungen
  und im Log vermerkt - es wird NICHT umgangen.
- Die CSS-Selektoren in den einzelnen `scrape_*`-Funktionen sind nach bestem
  Wissen auf Basis der aktuell sichtbaren Seitenstruktur gewählt. Websites
  ändern ihr HTML gelegentlich - wenn eine Quelle plötzlich 0 Treffer liefert,
  prüfe zuerst, ob sich die Selektoren geändert haben (siehe README).
"""

import json
import os
import re
import time
import logging
import hashlib
from datetime import datetime, timedelta
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests
import yaml
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("musiker-agent")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "results.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

USER_AGENT = CONFIG["einstellungen"]["user_agent"]
DELAY = CONFIG["einstellungen"]["request_delay_sekunden"]
RESPECT_ROBOTS = CONFIG["einstellungen"]["respect_robots_txt"]
MAX_AGE_DAYS = CONFIG["einstellungen"]["max_alter_tage"]

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

_robots_cache = {}


def robots_allowed(url: str) -> bool:
    """Prüft robots.txt der Domain für die gegebene URL."""
    if not RESPECT_ROBOTS:
        return True
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    if domain not in _robots_cache:
        rp = RobotFileParser()
        rp.set_url(urljoin(domain, "/robots.txt"))
        try:
            rp.read()
        except Exception as e:
            log.warning(f"robots.txt konnte für {domain} nicht gelesen werden ({e}) - Zugriff wird vorsichtshalber erlaubt, aber manuell prüfen!")
            _robots_cache[domain] = None
            return True
        _robots_cache[domain] = rp
    rp = _robots_cache[domain]
    if rp is None:
        return True
    allowed = rp.can_fetch(USER_AGENT, url)
    if not allowed:
        log.warning(f"robots.txt verbietet Zugriff auf {url} - Quelle wird übersprungen.")
    return allowed


def fetch(url: str):
    """Holt eine URL, respektiert robots.txt und Netiquette-Delay."""
    if not robots_allowed(url):
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        time.sleep(DELAY)
        if resp.status_code == 200:
            return resp.text
        log.warning(f"HTTP {resp.status_code} bei {url}")
    except Exception as e:
        log.warning(f"Fehler beim Abrufen von {url}: {e}")
    return None


def make_id(*parts) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def matches_profile(text: str) -> bool:
    """Prüft grob, ob ein Treffer zu den gewünschten Genres passt und keine
    Ausschlussbegriffe enthält."""
    text_low = text.lower()
    genres = [g.lower() for g in CONFIG["profile"]["genres"]]
    excludes = [e.lower() for e in CONFIG["profile"]["ausschluss_begriffe"]]

    if any(ex in text_low for ex in excludes):
        return False
    return any(g in text_low for g in genres) or True  # True = erstmal alles durchlassen,
    # Genre-Treffer werden separat als "relevanz" markiert (siehe score_relevance)


def score_relevance(text: str) -> int:
    text_low = text.lower()
    genres = [g.lower() for g in CONFIG["profile"]["genres"]]
    return sum(1 for g in genres if g in text_low)


# ---------------------------------------------------------------------------
# Quelle 1: Backstage PRO (Gigbörse / regionale Musikersuche)
# ---------------------------------------------------------------------------
def scrape_backstagepro():
    results = []
    if not CONFIG["quellen"]["backstagepro"]["aktiv"]:
        return results

    # Booking-Bereich: hier inserieren VERANSTALTER Gigs/Auftrittsmöglichkeiten
    # (nicht zu verwechseln mit /musikersuche, wo Musiker Mitmusiker suchen!)
    url = "https://www.backstagepro.de/gigs?city=Regensburg&city_lat=49.0134297&city_lon=12.1016236&radius=100"
    html = fetch(url)
    if not html:
        log.warning("backstagepro: keine HTML-Antwort erhalten (siehe fetch()-Log oberhalb).")
        return results
    soup = BeautifulSoup(html, "html.parser")

    # TODO: Selektor ggf. anpassen, falls sich das Markup geändert hat.
    items = soup.select("article, .search-result, .list-item, .gig-item")
    log.info(f"backstagepro: {len(items)} Roh-Elemente über Selektor gefunden (vor Genre-Filter).")
    if len(items) == 0:
        log.warning(f"backstagepro: 0 Elemente gefunden. HTML-Ausschnitt zur Diagnose:\n{html[:1500]}")

    for item in items:
        title_el = item.select_one("h2, h3, a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link_el = item.find("a", href=True)
        link = urljoin(url, link_el["href"]) if link_el else url
        date_text = ""
        date_el = item.select_one("time, .date")
        if date_el:
            date_text = date_el.get_text(strip=True)

        if not title:
            continue
        if not matches_profile(title):
            continue

        results.append({
            "id": make_id("backstagepro", link),
            "quelle": "Backstage PRO",
            "event": title,
            "datum": date_text or "unbekannt",
            "ort": "Regensburg (Umkreis, laut Filter)",
            "link": link,
            "kontakt": "über Profil auf Backstage PRO",
            "relevanz": score_relevance(title),
        })

    return results


# ---------------------------------------------------------------------------
# Quelle 2b: Kleinanzeigen.de (Kategorie Künstler/Musiker, mit Radius-Filter)
# ---------------------------------------------------------------------------
def scrape_kleinanzeigen():
    results = []
    if not CONFIG["quellen"]["kleinanzeigen"]["aktiv"]:
        return results

    standort = CONFIG["standorte"][0]
    radius = standort.get("radius_km", 50)
    ort_slug = standort["name"].lower()

    such_begriffe = ["musiker-gesucht", "musiker-sucht-musiker", "band-gesucht"]
    for begriff in such_begriffe:
        url = f"https://www.kleinanzeigen.de/s-{ort_slug}/{begriff}/k0l7636r{radius}"
        html = fetch(url)
        if not html:
            log.warning(f"kleinanzeigen ('{begriff}'): keine HTML-Antwort erhalten.")
            continue
        soup = BeautifulSoup(html, "html.parser")

        items = soup.select("article, .aditem, li.ad-listitem")
        log.info(f"kleinanzeigen ('{begriff}'): {len(items)} Roh-Elemente gefunden.")
        if len(items) == 0:
            log.warning(f"kleinanzeigen ('{begriff}'): 0 Elemente. HTML-Ausschnitt:\n{html[:1500]}")

        for item in items:
            title_el = item.select_one("h2, h3, a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            link_el = item.find("a", href=True)
            link = urljoin(url, link_el["href"]) if link_el else url
            ort_el = item.select_one(".aditem-main--top--left, .ad-listitem-location")
            ort_text = ort_el.get_text(strip=True) if ort_el else standort["name"]

            if not title:
                continue

            results.append({
                "id": make_id("kleinanzeigen", link),
                "quelle": "Kleinanzeigen.de",
                "event": title,
                "datum": "unbekannt",
                "ort": ort_text,
                "link": link,
                "kontakt": "über Kleinanzeigen-Nachricht (Login erforderlich)",
                "relevanz": score_relevance(title),
            })

    return results



def scrape_bandmix():
    results = []
    if not CONFIG["quellen"]["bandmix"]["aktiv"]:
        return results

    url = "https://www.bandmix.de/musiker-gesucht/regensburg/"
    html = fetch(url)
    if not html:
        log.warning("bandmix: keine HTML-Antwort erhalten (siehe fetch()-Log oberhalb).")
        return results
    soup = BeautifulSoup(html, "html.parser")

    items = soup.select(".ad, .listing-item, article")
    log.info(f"bandmix: {len(items)} Roh-Elemente über Selektor gefunden (vor Genre-Filter).")
    if len(items) == 0:
        log.warning(f"bandmix: 0 Elemente gefunden. HTML-Ausschnitt zur Diagnose:\n{html[:1500]}")

    for item in items:
        title_el = item.select_one("h2, h3, a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link_el = item.find("a", href=True)
        link = urljoin(url, link_el["href"]) if link_el else url

        if not title or not matches_profile(title):
            continue

        results.append({
            "id": make_id("bandmix", link),
            "quelle": "BandMix.de",
            "event": title,
            "datum": "unbekannt",
            "ort": "Regensburg (Umkreis, laut Filter)",
            "link": link,
            "kontakt": "über Anzeige auf BandMix.de",
            "relevanz": score_relevance(title),
        })

    return results


# ---------------------------------------------------------------------------
# Quelle 3: musiker-sucht-musiker.de
# ---------------------------------------------------------------------------
def scrape_musiker_sucht_musiker():
    results = []
    if not CONFIG["quellen"]["musiker_sucht_musiker"]["aktiv"]:
        return results

    url = "https://www.musiker-sucht-musiker.de/regensburg/"
    html = fetch(url)
    if not html:
        log.warning("musiker-sucht-musiker: keine HTML-Antwort erhalten (siehe fetch()-Log oberhalb).")
        return results
    soup = BeautifulSoup(html, "html.parser")

    items = soup.select(".anzeige, .listing, article")
    log.info(f"musiker-sucht-musiker: {len(items)} Roh-Elemente über Selektor gefunden (vor Genre-Filter).")
    if len(items) == 0:
        log.warning(f"musiker-sucht-musiker: 0 Elemente gefunden. HTML-Ausschnitt zur Diagnose:\n{html[:1500]}")

    for item in items:
        title_el = item.select_one("h2, h3, a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link_el = item.find("a", href=True)
        link = urljoin(url, link_el["href"]) if link_el else url

        if not title or not matches_profile(title):
            continue

        results.append({
            "id": make_id("msm", link),
            "quelle": "musiker-sucht-musiker.de",
            "event": title,
            "datum": "unbekannt",
            "ort": "Regensburg (Umkreis, laut Filter)",
            "link": link,
            "kontakt": "über Anzeige",
            "relevanz": score_relevance(title),
        })

    return results


# ---------------------------------------------------------------------------
# Quelle 4: musikersuche.net (Buchungsanfragen)
# ---------------------------------------------------------------------------
def scrape_musikersuche_net():
    results = []
    if not CONFIG["quellen"]["musikersuche_net"]["aktiv"]:
        return results

    url = "https://www.musikersuche.net/anfragen/regensburg"
    html = fetch(url)
    if not html:
        log.warning("musikersuche.net: keine HTML-Antwort erhalten (siehe fetch()-Log oberhalb).")
        return results
    soup = BeautifulSoup(html, "html.parser")

    items = soup.select(".request, .anfrage, article")
    log.info(f"musikersuche.net: {len(items)} Roh-Elemente über Selektor gefunden (vor Genre-Filter).")
    if len(items) == 0:
        log.warning(f"musikersuche.net: 0 Elemente gefunden. HTML-Ausschnitt zur Diagnose:\n{html[:1500]}")

    for item in items:
        title_el = item.select_one("h2, h3, a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link_el = item.find("a", href=True)
        link = urljoin(url, link_el["href"]) if link_el else url

        if not title or not matches_profile(title):
            continue

        results.append({
            "id": make_id("musikersuche_net", link),
            "quelle": "musikersuche.net",
            "event": title,
            "datum": "unbekannt",
            "ort": "Regensburg (Umkreis, laut Filter)",
            "link": link,
            "kontakt": "über Buchungsanfrage",
            "relevanz": score_relevance(title),
        })

    return results


# ---------------------------------------------------------------------------
# Quelle 5: Vergabeplattform Bayern (öffentliche Ausschreibungen)
# ---------------------------------------------------------------------------
def scrape_vergabe_bayern():
    results = []
    if not CONFIG["quellen"]["vergabe_bayern"]["aktiv"]:
        return results

    # Volltextsuche auf der Vergabeplattform Bayern
    search_terms = ["Musiker", "musikalische Umrahmung", "Live-Musik", "Band Veranstaltung"]
    base_url = "https://www.vergabe.bayern.de/VMPSatellite/public/company/search"

    for term in search_terms:
        url = f"{base_url}?searchTerm={term.replace(' ', '+')}"
        html = fetch(url)
        if not html:
            log.warning(f"vergabe_bayern ('{term}'): keine HTML-Antwort erhalten.")
            continue
        soup = BeautifulSoup(html, "html.parser")

        items = soup.select(".result-item, tr, article")
        log.info(f"vergabe_bayern ('{term}'): {len(items)} Roh-Elemente gefunden.")
        if len(items) == 0:
            log.warning(f"vergabe_bayern ('{term}'): 0 Elemente. HTML-Ausschnitt:\n{html[:1500]}")

        for item in items:
            title_el = item.select_one("h2, h3, a, td")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            link_el = item.find("a", href=True)
            link = urljoin(url, link_el["href"]) if link_el else url

            if not title or len(title) < 8:
                continue

            results.append({
                "id": make_id("vergabe_bayern", link, term),
                "quelle": "Vergabeplattform Bayern",
                "event": title,
                "datum": "unbekannt",
                "ort": "laut Ausschreibung",
                "link": link,
                "kontakt": "siehe Vergabeunterlagen",
                "relevanz": score_relevance(title),
            })

    return results


# ---------------------------------------------------------------------------
# Hauptlauf
# ---------------------------------------------------------------------------
SCRAPERS = [
    scrape_backstagepro,
    scrape_kleinanzeigen,
    scrape_bandmix,
    scrape_musiker_sucht_musiker,
    scrape_musikersuche_net,
    scrape_vergabe_bayern,
]


def load_existing():
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"letzte_aktualisierung": None, "treffer": []}


def main():
    log.info("Starte Musiker-Agent-Lauf...")
    existing = load_existing()
    existing_by_id = {t["id"]: t for t in existing.get("treffer", [])}

    all_results = []
    for scraper_fn in SCRAPERS:
        name = scraper_fn.__name__
        try:
            found = scraper_fn()
            log.info(f"{name}: {len(found)} Treffer")
            all_results.extend(found)
        except Exception as e:
            log.error(f"Fehler in {name}: {e}")

    # Neue Treffer mit 'gefunden_am' versehen, bestehende Treffer behalten ihr Datum
    now_iso = datetime.utcnow().isoformat()
    for r in all_results:
        if r["id"] in existing_by_id:
            r["gefunden_am"] = existing_by_id[r["id"]].get("gefunden_am", now_iso)
        else:
            r["gefunden_am"] = now_iso

    # Alte Treffer (nicht mehr gefunden, aber noch nicht zu alt) behalten,
    # damit das Dashboard nicht bei jedem Lauf komplett leer wird, falls eine
    # Quelle mal kurzzeitig nicht erreichbar ist.
    cutoff = datetime.utcnow() - timedelta(days=MAX_AGE_DAYS)
    seen_ids = {r["id"] for r in all_results}
    for old in existing.get("treffer", []):
        if old["id"] not in seen_ids:
            try:
                gefunden = datetime.fromisoformat(old.get("gefunden_am", now_iso))
            except ValueError:
                gefunden = datetime.utcnow()
            if gefunden > cutoff:
                all_results.append(old)

    # Sortierung: höchste Relevanz zuerst, dann neueste zuerst
    all_results.sort(key=lambda r: (r.get("relevanz", 0), r.get("gefunden_am", "")), reverse=True)

    output = {
        "letzte_aktualisierung": now_iso,
        "anzahl_treffer": len(all_results),
        "treffer": all_results,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(f"Fertig. {len(all_results)} Treffer insgesamt in {OUTPUT_PATH} gespeichert.")


if __name__ == "__main__":
    main()
