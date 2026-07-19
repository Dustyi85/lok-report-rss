import os
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
import re
from dateutil import parser as date_parser
import mimetypes
from urllib.parse import urljoin, urlparse

# --- LOGGING KONFIGURATION ---
ENABLE_LOGGING = True  # Auf False setzen, um das Logging auszuschalten
LOG_FILE = "log.txt"
# ------------------------------

# Lokale Zeitzone für naive Datetimes
LOCAL_TZ = datetime.now().astimezone().tzinfo

# Muster für Bildnamen, die wahrscheinlich Icons/Navigation sind und übersprungen werden sollten
SKIP_IMAGE_PATTERNS = re.compile(r'arrow|icon|logo|sprite|favicon|social|button', re.I)


def parse_german_date(text):
    """Versucht verschiedene Datum-Formate zu parsen und gibt immer ein aware datetime zurück."""
    if not text:
        return None

    months = {
        "Januar": "January", "Februar": "February", "März": "March", "April": "April", 
        "Mai": "May", "Juni": "June", "Juli": "July", "August": "August", 
        "September": "September", "Oktober": "October", "November": "November", "Dezember": "December"
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


def fetch_article_metadata(article_url, headers):
    """
    Lädt die Artikel-Seite und versucht:
      - das Veröffentlichungsdatum (meta tags, <time>, date-classes, oder regex im Text)
      - das Bild (og:image, typische img Klassen, src)
    Gibt (image_url, pub_date) zurück, entweder oder beides können None sein.
    """
    try:
        response = requests.get(article_url, headers=headers, timeout=12)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1) Datum suchen: meta property / name
        pub_date = None
        # Meta: article:published_time, og:published_time, article:modified_time
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
                # try datetime attribute first
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

        # 4) Fallback: suche im Text nach typischen Datums-Strings (z.B. "12. Juli 2026" oder "12.07.2026")
        if not pub_date:
            text_blob = soup.get_text(separator=' ', strip=True)
            # kurze regex für "dd. Monat yyyy" oder "dd.mm.yyyy"
            m = re.search(r'\b\d{1,2}\.\s*(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s*\d{4}\b', text_blob, re.I)
            if not m:
                m = re.search(r'\b\d{1,2}\.\d{1,2}\.\d{2,4}\b', text_blob)
            if m:
                pub_date = parse_german_date(m.group(0))

        # 5) Bild extrahieren: og:image, meta, oder erstes relevantes <img>
        image_url = None
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            candidate = og['content']
            # skip obvious icons
            name = os.path.basename(urlparse(candidate).path or '')
            if not SKIP_IMAGE_PATTERNS.search(name):
                image_url = candidate
        if not image_url:
            link_img = soup.find('link', rel='image_src')
            if link_img and link_img.get('href'):
                candidate = link_img['href']
                name = os.path.basename(urlparse(candidate).path or '')
                if not SKIP_IMAGE_PATTERNS.search(name):
                    image_url = candidate
        if not image_url:
            img = soup.find('img', class_=re.compile(r'article|featured|header|main', re.I))
            if not img:
                # find all imgs and pick the first that doesn't match skip patterns
                imgs = soup.find_all('img', attrs={'src': re.compile(r'jpg|png|jpeg', re.I)})
                for im in imgs:
                    src = im.get('src')
                    if not src:
                        continue
                    name = os.path.basename(urlparse(src).path or '')
                    if SKIP_IMAGE_PATTERNS.search(name):
                        continue
                    image_url = src
                    break
            else:
                src = img.get('src')
                if src:
                    name = os.path.basename(urlparse(src).path or '')
                    if not SKIP_IMAGE_PATTERNS.search(name):
                        image_url = src

        # Vollständige URL sicherstellen
        if image_url and not image_url.startswith('http'):
            image_url = urljoin('https://lok-report.de', image_url)

        return image_url, pub_date

    except Exception as e:
        print(f"Fehler beim Laden der Artikel-Seite {article_url}: {e}")
    return None, None


# 1. Webseite abrufen
url = "https://lok-report.de"
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)'}

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
fg.description('Aktuelle Meldungen aus der Eisenbahnwelt mit Bildern')
fg.load_extension('media', atom=False, rss=True)

# Liste für die Log-Einträge vorbereiten
log_entries = []

# Temporäre Liste zum Sammeln der Artikel bevor Sortierung
collected = []

# 3. HTML-Struktur verarbeiten
if soup:
    # Versuche verschiedene mögliche Selektoren für Artikel
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
        image_url = None

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
            if not image_url and hasattr(next_node, 'find'):
                img_element = next_node.find('img')
                if img_element and img_element.get('src'):
                    img_src = img_element['src']
                    name = os.path.basename(urlparse(img_src).path or '')
                    if not SKIP_IMAGE_PATTERNS.search(name):
                        image_url = img_src if img_src.startswith('http') else urljoin('https://lok-report.de', img_src)
                        print(f"  → Bild gefunden (Sibling): {image_url[:60]}...")
            next_node = next_node.find_next_sibling()

        # Wenn kein Datum oder Bild in der Übersicht: hole Metadaten von der Artikel-Seite
        if not pub_date or not image_url:
            print(f"  → Fetche Metadaten von Artikel-Seite...")
            meta_image, meta_date = fetch_article_metadata(link, headers)
            if meta_image and not image_url:
                image_url = meta_image
                print(f"  → Bild gefunden (Artikel-Seite): {image_url[:60]}...")
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
            'image_url': image_url,
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

    # Erstelle Feed-Einträge in der gewünschten Reihenfolge
    for item in collected:
        title_text = item['title']
        link = item['link']
        pub_date = item['pub_date']
        image_url = item['image_url']
        desc_text = item['desc']

        # Für das Logging: Bildname extrahieren
        if image_url:
            try:
                image_name = os.path.basename(urlparse(image_url).path) or 'UNKNOWN'
            except Exception:
                image_name = 'UNKNOWN'
        else:
            image_name = 'KEIN_BILD'

        date_str_log = pub_date.strftime('%Y-%m-%d %H:%M:%S %z') if pub_date else "KEIN DATUM"
        log_entries.append(f"[{date_str_log}] {title_text} | Bild: {image_name} | URL: {image_url or 'KEIN_BILD'}")

        # Erstelle Feed-Entry
        fe = fg.add_entry()
        if pub_date:
            try:
                fe.id(f"{link}?v={int(pub_date.timestamp())}")
            except Exception:
                fe.id(link)
            fe.pubDate(pub_date)
        else:
            fe.id(link)
            fe.pubDate(datetime.now().astimezone())

        fe.title(title_text)
        fe.link(href=link)

        # Beschreibung mit oder ohne Bild
        desc_content = desc_text[:300] + "..."
        if image_url:
            fe.description(f'<img src="{image_url}" style="max-width:100%; height:auto;"/><br/><br/>{desc_content}')
            try:
                # Bestimme MIME-Typ aus Dateiendung
                mime, _ = mimetypes.guess_type(image_url)
                mime = mime or 'image/jpeg'
                fe.enclosure(image_url, 0, mime)
            except Exception:
                pass  # Enklosing ist optional
        else:
            fe.description(desc_content)

    print(f"\n✓ Insgesamt {len(collected)} Artikel dem Feed hinzugefügt")

# Fallback: Wenn keine Artikel gefunden wurden
if len(fg.entry()) == 0:
    print("⚠ Keine Artikel gefunden - erstelle Platzhalter")
    fe = fg.add_entry()
    fe.id(url)
    fe.title('Wartung: Feed wird aktualisiert')
    fe.link(href=url)
    fe.description('Der RSS-Feed wird im Hintergrund neu generiert oder die HTML-Struktur der Website hat sich geändert.')

# 4. RSS-Datei speichern
try:
    fg.rss_file('feed.xml')
    print("✓ RSS-Feed erfolgreich generiert!")
except Exception as e:
    print(f"✗ Fehler beim Speichern des RSS-Feeds: {e}")

# 5. Log-Datei schreiben
if ENABLE_LOGGING:
    try:
        current_run = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"=== LOG DURCHLAUF VOM {current_run} ===\n")
            f.write(f"Artikel insgesamt: {len(fg.entry())}\n\n")
            f.write("\n".join(log_entries))
            f.write("\n")
        print(f"✓ Logging geschrieben: {LOG_FILE}")
    except Exception as e:
        print(f"✗ Fehler beim Schreiben des Logs: {e}")
