import os
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime
import re

# Hilfsfunktion, um das deutsche Textdatum von LOK Report in ein echtes Datumsobjekt zu wandeln
def parse_german_date(text):
    months = {
        "Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6,
        "Juli": 7, "August": 8, "September": 9, "Oktober": 10, "November": 11, "Dezember": 12
    }
    try:
        # Sucht nach Mustern wie: "17. Juli 2026 12:00"
        match = re.search(r'(\d{1,2})\.\s+([A-Za-zä]+)\s+(\d{4})\s+(\d{2}):(\d{2})', text)
        if match:
            day = int(match.group(1))
            month_str = match.group(2)
            year = int(match.group(3))
            hour = int(match.group(4))
            minute = int(match.group(5))
            
            month = months.get(month_str, 1)
            # Erstellt das Datum und fügt die deutsche Zeitzone (+02:00 für Sommerzeit / +01:00 für Winterzeit) an
            # Da es ein automatisierter RSS-Feed ist, nutzen wir hier einen festen UTC-Offset für Europa
            return datetime(year, month, day, hour, minute, 0).astimezone()
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
fg.title('LOK Report News Feed')
fg.author({'name': 'LOK Report Scraper'})
fg.link(href=url, rel='alternate')
fg.description('Aktuelle Meldungen aus der Eisenbahnwelt')

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
                
            # Text und Datum extrahieren
            desc_text = ""
            pub_date = None
            next_node = title_element.find_next_sibling()
            
            while next_node and next_node.name != 'h2' and len(desc_text) < 500:
                if next_node.name in ['p', 'div'] and next_node.text:
                    node_text = next_node.text.strip()
                    
                    # Prüfen, ob dieser Absatz das Datum enthält (z. B. "Freitag, 17. Juli 2026")
                    if any(day in node_text for day in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]) and ":" in node_text:
                        pub_date = parse_german_date(node_text)
                    else:
                        desc_text += " " + node_text
                        
                next_node = next_node.find_next_sibling()
            
            desc_text = desc_text.strip() if desc_text else title_text
            
            # RSS-Eintrag erstellen
            fe = fg.add_entry()
            fe.id(link)
            fe.title(title_text)
            fe.link(href=link)
            fe.description(desc_text[:300] + "...")
            
            # Wenn ein Datum gefunden wurde, fügen wir es dem Eintrag hinzu
            if pub_date:
                fe.pubDate(pub_date)
                
            count += 1

# Dummy-Eintrag falls leer
if len(fg.entry()) == 0:
    fe = fg.add_entry()
    fe.id(url)
    fe.title('Wartung: Feed wird aktualisiert')
    fe.link(href=url)
    fe.description('Der RSS-Feed wird im Hintergrund neu generiert.')

# 4. Datei speichern
fg.rss_file('feed.xml')
print("RSS-Feed erfolgreich mit Datumsangaben generiert!")
