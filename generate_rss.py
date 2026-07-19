import os
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
import re
from dateutil import parser as date_parser
import mimetypes
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

# --- LOGGING KONFIGURATION ---
ENABLE_LOGGING = True  # Auf False setzen, um das Logging auszuschalten
LOG_FILE = "log.txt"
# ------------------------------

# Lokale Zeitzone: Mitteleuropäische Zeit / Sommerzeit (Europe/Berlin)
LOCAL_TZ = ZoneInfo("Europe/Berlin")

# Basis-Pfad für gewünschte Nachrichten-Bilder
NEWS_IMAGE_PATH = '/images/news/'
NEWS_IMAGE_HOST = 'https://lok-report.de'


def parse_german_date(text):
    """Versucht verschiedene Datum-Formate zu parsen und gibt immer ein aware datetime zurück."""
    if not text:
        return None

    months = {
        "Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6,
        "Juli": 7, "August": 8, "September": 9, "Oktober": 10, "November": 11, "Dezember": 12
    }

    try:
        clean_text = text.replace('-', ' ').strip()

        # Erste Strategie: deutsche Monatsnamen ersetzen und parse versuchen
        for de_month, en_month in months.items():
            if de_month in clean_text:
                clean_text_en = clean_text.replace(de_month, en_month)
                try:
                    dt = date_parser.parse(clean_text_en, dayfirst=True, fuzzy=True)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=LOCAL_TZ)
                    return dt
                except Exception:
                    pass

        # Zweiter Versuch: direktes Parsing (fuzzy)
        dt = date_parser.parse(clean_text, dayfirst=True, fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=LOCAL_TZ)
        return dt

    except Exception as e:
        print(f"Fehler beim Parsing von '{text}': {e}")
    return None


def _abs_url(base, link):
    if not link:
        return None
    if link.startswith('http'):
        return link
    return urljoin(base, link)


def fetch_article_metadata(article_url, headers):
    """
    Lädt die Artikel-Seite und versucht:
      - das Veröffentlichungsdatum (meta tags, <time>, date-classes, oder regex im Text)
      - alle Bilder, die im Pfad /images/news/ liegen
    Gibt (image_urls_list, pub_date) zurück. image_urls_list ist eine Liste (kann leer sein).
    """
    try:
        response = requests.get(article_url, headers=headers, timeout=12)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1) Datum suchen: meta property / name
        pub_date = None
        meta_candidates = [
            ('property', re.compile(r'(^|:)published_time$', re.I)),
            ('property', re.compile(r'(^|:)pubdate$', re.I)),
            ('name', re.compile(r'(^|:)date$', re.I)),
            ('itemprop', re.compile(r'datePublished', re.I)),
        ]
        for attr, pattern in meta_candidates:
            meta = soup.find('meta', attrs={attr: pattern})
            if meta and meta.get('content'):
                pub_date = parse_german_date(meta['content'])
                if pub_date:
                    break

        # 2) <time datetime="...">
        if not pub_date:
            time_tag = soup.find('time')
            if time_tag:
                dt_attr = time_tag.get('datetime')
                if dt_attr:
                    pub_date = parse_german_date(dt_attr)
                if not pub_date and time_tag.text:
                    pub_date = parse_german_date(time_tag.text)

        # 3) Klassen/Spans mit date/time/published/datum
        if not pub_date:
            date_elem = soup.find(attrs={'class': re.compile(r'date|time|published|datum', re.I)})
            if date_elem and date_elem.text:
                pub_date = parse_german_date(date_elem.text)

        # 4) Fallback: suche im Text nach typischen Datums-Strings
        if not pub_date:
            text_blob = soup.get_text(separator=' ', strip=True)
            m = re.search(r'\b\d{1,2}\.\s*(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s*\d{4}\b', text_blob, re.I)
            if not m:
                m = re.search(r'\b\d{1,2}\.\d{1,2}\.\d{2,4}\b', text_blob)
            if m:
                pub_date = parse_german_date(m.group(0))

        # Bilder sammeln: nur solche unter /images/news/
        image_urls = []

        # Prüfe meta og:image und link rel=image_src, aber nur wenn sie ins news-Verzeichnis zeigen
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            candidate = _abs_url(NEWS_IMAGE_HOST, og['content'])
            if NEWS_IMAGE_PATH in urlparse(candidate).path:
                image_urls.append(candidate)

        link_img = soup.find('link', rel='image_src')
        if link_img and link_img.get('href'):
            candidate = _abs_url(NEWS_IMAGE_HOST, link_img['href'])
            if NEWS_IMAGE_PATH in urlparse(candidate).path and candidate not in image_urls:
                image_urls.append(candidate)

        # Alle <img>-Tags durchgehen und solche aus /images/news/ sammeln
        imgs = soup.find_all('img', attrs={'src': True})
        for im in imgs:
            src = im.get('src')
            if not src:
                continue
            abs_src = _abs_url(NEWS_IMAGE_HOST, src)
            if NEWS_IMAGE_PATH in urlparse(abs_src).path:
                if abs_src not in image_urls:
                    image_urls.append(abs_src)

        return image_urls, pub_date

    except Exception as e:
        print(f"Fehler beim Laden der Artikel-Seite {article_url}: {e}")
    return [], None


# 1. Webseite abrufen
url = "https://lok-report.de"
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

try:
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
except Exception as e:
    print(f"Fehler beim Laden der Seite: {e}")
    soup = None

# 2. RSS-Feed initialisieren
fg = FeedGenerator()
fg.id(url)
fg.title('LOK Report News Premium Feed')
fg.author({'name': 'LOK Report Scraper'})
fg.link(href=url, rel='alternate')
fg.description('Aktuelle Meldungen aus der Eisenbahnwelt mit Bildern aus /images/news/')
fg.load_extension('media', atom=False, rss=True)

# Liste für die Log-Einträge vorbereiten
log_entries = []

# Temporäre Liste zum Sammeln der Artikel bevor Sortierung
collected = []

# 3. HTML-Struktur verarbeiten
if soup:
    titles = soup.select('h2')

    # Fallback: Wenn h2 nicht funktioniert, versuche andere Selektoren
    if not titles:
        titles = soup.select('h3')
    if not titles:
        titles = soup.select('strong')

    print(f"Gefundene Artikel-Titel: {len(titles)}")

    count = 0
    for title_element in titles:
        if count >= 200:  # Sammle mehr, sortiere und beschränke später auf 20
            break

        # Versuche den Link zu finden
        link_element = title_element.find('a')
        if not link_element:
            link_element = title_element.find_parent('a')

        if not link_element or not link_element.get('href'):
            continue

        title_text = link_element.text.strip()
        if not title_text or len(title_text) < 3:
            continue

        link = link_element['href']

        if not link.startswith('http'):
            link = urljoin('https://lok-report.de', link)

        # Filtere unerwünschte Links
        if any(x in link.lower() for x in ["laenderuebersicht", "kontakt", "impressum", "datenschutz"]):
            continue

        desc_text = ""
        pub_date = None
        image_urls = []

        print(f"\nVerarbeite Artikel (übersicht): {title_text[:50]}...")

        # Datum suchen - mehrere Strategien (Übersichtsseite)
        date_element = title_element.find_next_sibling('span', class_=re.compile(r'date|time', re.I))
        if not date_element:
            date_element = title_element.find_next('span', class_=re.compile(r'date|time', re.I))
        if not date_element:
            # Versuche das Datum im nächsten Text zu finden
            next_elem = title_element.find_next(string=re.compile(r'\d{1,2}\.|Januar|Februar|März', re.I))
            if next_elem:
                parent = next_elem.parent
                date_element = parent if parent else None

        if date_element and getattr(date_element, "text", None):
            pub_date = parse_german_date(date_element.text)
            if pub_date:
                print(f"  → Datum gefunden (Übersicht): {pub_date}")
            else:
                print(f"  → Datum-String (Übersicht): '{date_element.text}' (Parsing fehlgeschlagen)")

        # Sammle HTML-Content für Beschreibung (von Übersicht)
        html_block = ""
        next_node = title_element.find_next_sibling()
        node_count = 0
        while next_node and getattr(next_node, 'name', None) not in ('h2', 'h3') and len(html_block) < 5000 and node_count < 10:
            html_block += str(next_node)
            node_count += 1
            # Wenn Übersicht-Bilder im gewünschten Verzeichnis sind, sammeln
            if hasattr(next_node, 'find'):
                imgs = next_node.find_all('img', attrs={'src': True})
                for img in imgs:
                    src = img.get('src')
                    if not src:
                        continue
                    abs_src = _abs_url('https://lok-report.de', src)
                    if NEWS_IMAGE_PATH in urlparse(abs_src).path and abs_src not in image_urls:
                        image_urls.append(abs_src)
                        print(f"  → Bild (Übersicht) hinzugefügt: {abs_src[:60]}...")
            next_node = next_node.find_next_sibling()

        # Wenn kein Datum oder Bild in der Übersicht: hole Metadaten von der Artikel-Seite
        if not pub_date or not image_urls:
            print(f"  → Fetche Metadaten von Artikel-Seite...")
            meta_images, meta_date = fetch_article_metadata(link, headers)
            # meta_images ist eine Liste
            for mi in meta_images:
                if mi not in image_urls:
                    image_urls.append(mi)
                    print(f"  → Bild gefunden (Artikel-Seite): {mi[:60]}...")
            if meta_date and not pub_date:
                pub_date = meta_date
                print(f"  → Datum gefunden (Artikel-Seite): {pub_date}")

        block_soup = BeautifulSoup(html_block, 'html.parser')

        # Extrahiere Text für Beschreibung
        full_text = block_soup.text.strip()
        desc_text = re.sub(r'\s+', ' ', full_text).strip()
        if not desc_text:
            desc_text = title_text

        # Füge Artikel zur temporären Liste hinzu
        collected.append({
            'title': title_text,
            'link': link,
            'pub_date': pub_date,
            'image_urls': image_urls,
            'desc': desc_text,
        })

        count += 1

    print(f"\n✓ Insgesamt {len(collected)} Artikel gesammelt (unzensiert)")

# Sortiere nach Datum: neu -> alt. Artikel ohne Datum zuletzt.
if collected:
    epoch = datetime(1970, 1, 1).replace(tzinfo=LOCAL_TZ)
    collected.sort(key=lambda e: e['pub_date'] or epoch, reverse=True)
    # Beschränke auf 20 Einträge
    collected = collected[:20]

    # --- WICHTIG: Log-Einträge jetzt erstellen (beibehalten neue->alte Reihenfolge) ---
    for item in collected:
        title_text = item['title']
        pub_date = item['pub_date']
        image_urls = item.get('image_urls', [])

        if image_urls:
            image_names = []
            for iu in image_urls:
                try:
                    image_names.append(os.path.basename(urlparse(iu).path) or 'UNKNOWN')
                except Exception:
                    image_names.append('UNKNOWN')
            image_names_str = ','.join(image_names)
            image_urls_str = ','.join(image_urls)
        else:
            image_names_str = 'KEIN_BILD'
            image_urls_str = 'KEIN_BILD'

        date_str_log = pub_date.strftime('%Y-%m-%d %H:%M:%S %z') if pub_date else "KEIN DATUM"
        log_entries.append(f"[{date_str_log}] {title_text} | Bilder: {image_names_str} | URLs: {image_urls_str}")

    # --- Feed-Einträge hinzufügen in umgekehrter Reihenfolge, damit feed.xml neu->alt enthält ---
    for item in reversed(collected):
        title_text = item['title']
        link = item['link']
        pub_date = item['pub_date']
        image_urls = item.get('image_urls', [])
        desc_text = item['desc']

        # Erstelle Feed-Entry
        fe = fg.add_entry()
        if pub_date:
            try:
                # sicherstellen, dass pub_date eine aware datetime in LOCAL_TZ ist
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=LOCAL_TZ)
                else:
                    # konvertiere ggf. in LOCAL_TZ
                    pub_date = pub_date.astimezone(LOCAL_TZ)
                fe.id(f"{link}?v={int(pub_date.timestamp())}")
            except Exception:
                fe.id(link)
            fe.pubDate(pub_date)
        else:
            fe.id(link)
            fe.pubDate(datetime.now(LOCAL_TZ))

        fe.title(title_text)
        fe.link(href=link)

        # Baue Beschreibung: alle gefundenen Bilder einfügen (in Reihenfolge)
        # Plain-text Vorschau (für Reader, die nur Text anzeigen)
        preview_text = re.sub(r'<[^>]+>', '', desc_text)  # HTML-Tags entfernen falls vorhanden
        preview_text = (preview_text[:300].strip() + "...") if preview_text else title_text

        # HTML-Beschreibung (für Reader, die HTML/content:encoded auswerten)
        if image_urls:
            imgs_html = ''.join([f'<img src="{iu}" style="max-width:100%; height:auto;"/><br/>' for iu in image_urls])
            description_html = f'{imgs_html}<br/>{preview_text}'
        else:
            description_html = preview_text

        # Setze mehrere Felder, damit möglichst viele Reader eine Vorschau anzeigen:
        try:
            fe.description(preview_text)                # RSS <description> (plain text)
        except Exception:
            pass
        try:
            fe.summary(preview_text)                    # Atom <summary>
        except Exception:
            pass
        try:
            fe.content(description_html, type='html')   # <content:encoded> / content type="html"
        except Exception:
            # Fallback: wenn content nicht unterstützt wird, ensure description contains HTML
            try:
                fe.description(description_html)
            except Exception:
                pass

        # Enclosure: nur das erste Bild setzen (falls vorhanden)
        if image_urls:
            try:
                first = image_urls[0]
                # Falls first relativ war, make absolute
                first = _abs_url(NEWS_IMAGE_HOST, first)
                mime, _ = mimetypes.guess_type(first)
                mime = mime or 'image/jpeg'
                fe.enclosure(first, 0, mime)
            except Exception:
                pass

    print(f"\n✓ Insgesamt {len(collected)} Artikel dem Feed hinzugefügt")

if len(fg.entry()) == 0:
    fe = fg.add_entry()
    fe.id(url)
    fe.title('Wartung: Feed wird aktualisiert')
    fe.link(href=url)
    fe.description('Der RSS-Feed wird im Hintergrund neu generiert.')

# 4. RSS-Datei speichern
fg.rss_file('feed.xml')

# 5. Log-Datei schreiben (falls aktiviert)
if ENABLE_LOGGING:
    try:
        current_run = datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"=== LOG DURCHLAUF VOM {current_run} ===\n")
            f.write(f"Artikel insgesamt: {len(fg.entry())}\n\n")
            f.write("\n".join(log_entries))
            f.write("\n")
        print(f"✓ Logging geschrieben: {LOG_FILE}")
    except Exception as e:
        print(f"✗ Fehler beim Schreiben des Logs: {e}")
