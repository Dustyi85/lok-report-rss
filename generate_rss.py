import os
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime
import re

def parse_german_date(text):
    months = {
        "Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6,
        "Juli": 7, "August": 8, "September": 9, "Oktober": 10, "November": 11, "Dezember": 12
    }
    try:
        # Sucht flexibel nach z.B. "17. Juli 2026 12:00" oder "05. März 2026 09:15"
        match = re.search(r'(\d{1,2})\.\s+([A-Za-zä]+)\s+(\d{4})\s+(\d{2}):(\d{2})', text)
        if match:
            day, month_str, year, hour, minute = match.groups()
            month = months.get(month_str, 1)
            return datetime(int(year), month, int(day), int(hour), int(minute), 0).astimezone()
    except Exception:
        pass
    return None

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
fg.description('Aktuelle Meldungen aus der Eisenbahnwelt mit Bildern')
fg.load_extension('media', atom=False, rss=True)

# 3. HTML-Struktur verarbeiten
if soup:
    titles = soup.select('h2')
    
    count = 0
    for title_element in titles:
        if count >= 20:
            break
            
        link_element = title_element.find('a')
        if link_element and link_element.get('href'):
            title_text = link_element.text.strip()
            link = link_element['href']
            
            if not link.startswith('http'):
                link = 'https://lok-report.de' + link
            
            if any(x in link for x in ["laenderuebersicht", "kontakt", "impressum", "datenschutz"]):
                continue
                
            desc_text = ""
            pub_date = None
            image_url = None
            
            # Ganzen HTML-Abschnitt bis zur nächsten H2-Überschrift einsammeln
            html_block = ""
            next_node = title_element.find_next_sibling()
            while next_node and next_node.name != 'h2' and len(html_block) < 3000:
                html_block += str(next_node)
                
                # Bilder einsammeln
                if not image_url:
                    img_element = next_node.find('img') if hasattr(next_node, 'find') else None
                    if img_element and img_element.get('src'):
                        img_src = img_element['src']
                        image_url = img_src if img_src.startswith('http') else 'https://lok-report.de' + img_src
                
                next_node = next_node.find_next_sibling()
            
            # Text aus dem gesammelten HTML-Block sauber extrahieren (ohne HTML-Tags)
            block_soup = BeautifulSoup(html_block, 'html.parser')
            full_text = block_soup.text.strip()
            
            # --- DATUMS-REPARATUR ---
            # Wir suchen gezielt nach Zeilen im Text, die Wochentage und Uhrzeiten enthalten
            for line in full_text.split('\n'):
                line = line.strip()
                if any(day in line for day in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]) and ":" in line:
                    pub_date = parse_german_date(line)
                    if pub_date:
                        # Entfernt die Datumszeile aus der späteren Beschreibung
                        full_text = full_text.replace(line, "")
                        break
            
            # Beschreibung säubern (überschüssige Leerzeichen entfernen)
            desc_text = re.sub(r'\s+', ' ', full_text).strip()
            if not desc_text:
                desc_text = title_text
            
            # RSS-Eintrag erstellen
            fe = fg.add_entry()
            
            # Feedly-Austricksen über eindeutigen Datumslink
            if pub_date:
                fe.id(f"{link}?v={int(pub_date.timestamp())}")
                fe.pubDate(pub_date)
            else:
                fe.id(link)
                fe.pubDate(datetime.now().astimezone())
                
            fe.title(title_text)
            fe.link(href=link)
            
            # Bild einbetten
            if image_url:
                fe.description(f'<img src="{image_url}" style="max-width:100%; height:auto;"/><br/>{desc_text[:300]}...')
                fe.enclosure(image_url, 0, 'image/jpeg')
            else:
                fe.description(desc_text[:300] + "...")
                
            count += 1

if len(fg.entry()) == 0:
    fe = fg.add_entry()
    fe.id(url)
    fe.title('Wartung: Feed wird aktualisiert')
    fe.link(href=url)
    fe.description('Der RSS-Feed wird im Hintergrund neu generiert.')

fg.rss_file('feed.xml')
print("RSS-Feed erfolgreich mit tiefenanalysierten Datumsangaben generiert!")
