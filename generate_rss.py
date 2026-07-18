import os
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime
import re
from dateutil import parser as date_parser

# --- LOGGING KONFIGURATION ---
ENABLE_LOGGING = True  # Auf False setzen, um das Logging auszuschalten
LOG_FILE = "log.txt"
# ------------------------------

def parse_german_date(text):
    """Versucht verschiedene Datum-Formate zu parsen"""
    if not text:
        return None
    
    months = {
        "Januar": "January", "Februar": "February", "März": "March", "April": "April", 
        "Mai": "May", "Juni": "June", "Juli": "July", "August": "August", 
        "September": "September", "Oktober": "October", "November": "November", "Dezember": "December"
    }
    
    try:
        clean_text = text.replace('-', '').strip()
        
        # Zuerst versuchen mit deutschem Datumsformat
        for de_month, en_month in months.items():
            clean_text_en = clean_text.replace(de_month, en_month)
            if clean_text_en != clean_text:
                try:
                    dt = date_parser.parse(clean_text_en, dayfirst=True)
                    return dt.astimezone() if dt.tzinfo else dt
                except:
                    pass
        
        # Fallback: versuche standardmäßiges Parsing
        dt = date_parser.parse(clean_text, dayfirst=True, fuzzy=True)
        return dt.astimezone() if dt.tzinfo else dt
        
    except Exception as e:
        print(f"Fehler beim Parsing von '{text}': {e}")
    return None

def fetch_article_image(article_url, headers):
    """Versucht das Bild direkt von der Artikel-Seite zu fetchen"""
    try:
        response = requests.get(article_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Suche nach verschiedenen häufigen Bild-Klassen
        img = soup.find('img', class_=re.compile(r'article|featured|header|main', re.I))
        if not img:
            img = soup.find('img', attrs={'src': re.compile(r'jpg|png|jpeg', re.I)})
        
        if img and img.get('src'):
            img_src = img['src']
            # Stelle sicher, dass die URL vollständig ist
            if not img_src.startswith('http'):
                if img_src.startswith('/'):
                    img_src = 'https://lok-report.de' + img_src
                else:
                    img_src = 'https://lok-report.de/' + img_src
            return img_src
    except Exception as e:
        print(f"Fehler beim Fetchen von {article_url}: {e}")
    return None

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
        if count >= 20:
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
            link = 'https://lok-report.de' + link
        
        # Filtere unerwünschte Links
        if any(x in link.lower() for x in ["laenderuebersicht", "kontakt", "impressum", "datenschutz"]):
            continue
        
        desc_text = ""
        pub_date = None
        image_url = None
        
        print(f"\nVerarbeite Artikel {count + 1}: {title_text[:50]}...")
        
        # Datum suchen - mehrere Strategien
        date_element = title_element.find_next_sibling('span', class_=re.compile(r'date|time', re.I))
        if not date_element:
            date_element = title_element.find_next('span', class_=re.compile(r'date|time', re.I))
        if not date_element:
            # Versuche das Datum im nächsten Text zu finden
            next_elem = title_element.find_next(string=re.compile(r'\d{1,2}\.|Januar|Februar|März'))
            if next_elem:
                parent = next_elem.parent
                date_element = parent if parent else None
        
        if date_element and date_element.text:
            pub_date = parse_german_date(date_element.text)
            if pub_date:
                print(f"  → Datum gefunden: {pub_date}")
            else:
                print(f"  → Datum-String: '{date_element.text}' (Parsing fehlgeschlagen)")
        
        # Sammle HTML-Content für Beschreibung
        html_block = ""
        next_node = title_element.find_next_sibling()
        node_count = 0
        while next_node and next_node.name != 'h2' and next_node.name != 'h3' and len(html_block) < 5000 and node_count < 10:
            html_block += str(next_node)
            node_count += 1
            if not image_url:
                img_element = next_node.find('img') if hasattr(next_node, 'find') else None
                if img_element and img_element.get('src'):
                    img_src = img_element['src']
                    image_url = img_src if img_src.startswith('http') else 'https://lok-report.de' + img_src
                    print(f"  → Bild gefunden (Sibling): {image_url[:60]}...")
            next_node = next_node.find_next_sibling()
        
        # Wenn kein Bild in den Siblings gefunden: Versuche direkt von der Artikel-Seite zu fetchen
        if not image_url:
            print(f"  → Fetche Bild von Artikel-Seite...")
            image_url = fetch_article_image(link, headers)
            if image_url:
                print(f"  → Bild gefunden (Artikel-Seite): {image_url[:60]}...")
        
        block_soup = BeautifulSoup(html_block, 'html.parser')
        
        # Für das Logging mitschreiben
        date_str_log = pub_date.strftime('%Y-%m-%d %H:%M:%S %z') if pub_date else "KEIN DATUM"
        log_entries.append(f"[{date_str_log}] {title_text} | Bild: {'JA' if image_url else 'NEIN'}")
        
        # Extrahiere Text für Beschreibung
        full_text = block_soup.text.strip()
        desc_text = re.sub(r'\s+', ' ', full_text).strip()
        if not desc_text:
            desc_text = title_text
        
        # Erstelle Feed-Entry
        fe = fg.add_entry()
        if pub_date:
            fe.id(f"{link}?v={int(pub_date.timestamp())}")
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
                fe.enclosure(image_url, 0, 'image/jpeg')
            except:
                pass  # Enklosing ist optional
        else:
            fe.description(desc_content)
        
        count += 1
    
    print(f"\n✓ Insgesamt {count} Artikel verarbeitet")

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
