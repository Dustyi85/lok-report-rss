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
        # Sucht nach dem Muster: "17. Juli 2026 12:00"
        match = re.search(r'(\d{1,2})\.\s+([A-Za-zä]+)\s+(\d{4})\s+(\d{2}):(\d{2})', text)
        if match:
            day, month_str, year, hour, minute = match.groups()
            month = months.get(month_str, 1)
            # Erstellt das echte Datum mit deutscher Zeitzone
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
            
            # Text, Datum und Bilder direkt unter der Überschrift suchen
            next_node = title_element.find_next_sibling()
            while next_node and next_node.name != 'h2' and len(desc_text) < 600:
                if next_node.name in ['p', 'div'] and next_node.text:
                    node_text = next_node.text.strip()
                    
                    # Hier wird die Zeile mit dem Datum (z.B. "Freitag, 17. Juli...") abgefangen
                    if any(day in node_text for day in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]) and ":" in node_text:
                        pub_date = parse_german_date(node_text)
                    else:
                        desc_text += " " + node_text
                
                # Bild extrahieren
                img_element = next_node.find('img') if hasattr(next_node, 'find') else None
                if img_element and img_element.get('src'):
                    img_src = img_element['src']
                    if not img_src.startswith('http'):
                        image_url = 'https://lok-report.de' + img_src
                    else:
                        image_url = img_src
                        
                next_node = next_node.find_next_sibling()
            
            desc_text = desc_text.strip() if desc_text else title_text
            
            fe = fg.add_entry()
            
            # TRICK FÜR FEEDLY: Wenn ein Datum da ist, hängen wir den Zeitstempel an die ID. 
            # Das zwingt Feedly, den Eintrag komplett neu mit der echten Uhrzeit zu berechnen.
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

# Als feed.xml speichern
fg.rss_file('feed.xml')
print("RSS-Feed erfolgreich mit Echtzeit-Datums-IDs generiert!")
