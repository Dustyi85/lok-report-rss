import os
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

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

# 3. HTML-Struktur nach Überschriften trennen
if soup:
    # LOK Report nutzt <h2> für die einzelnen News-Titel
    titles = soup.select('h2')
    
    count = 0
    for title_element in titles:
        if count >= 20:  # Maximal 20 Einträge in den Feed aufnehmen
            break
            
        link_element = title_element.find('a')
        if link_element and link_element.get('href'):
            title_text = link_element.text.strip()
            link = link_element['href']
            
            # Relative Links korrigieren
            if not link.startswith('http'):
                link = 'https://www.lok-report.de' + link
            
            # Unwichtige Seiten oder Navigationselemente herausfiltern
            if any(x in link for x in ["laenderuebersicht", "kontakt", "impressum", "datenschutz"]):
                continue
                
            # Den dazugehörigen Text (liegt meist im nächsten Element nach der Überschrift) herausfinden
            desc_text = ""
            next_node = title_element.find_next_sibling()
            
            # Holt den Text aus den Absätzen direkt unter der Überschrift bis zur nächsten News
            while next_node and next_node.name != 'h2' and len(desc_text) < 400:
                if next_node.name in ['p', 'div'] and next_node.text:
                    desc_text += " " + next_node.text.strip()
                next_node = next_node.find_next_sibling()
            
            # Falls kein Text gefunden wurde, Titel als Beschreibung nutzen
            desc_text = desc_text.strip() if desc_text else title_text
            
            # Neuen, sauberen RSS-Eintrag anlegen
            fe = fg.add_entry()
            fe.id(link)
            fe.title(title_text)
            fe.link(href=link)
            fe.description(desc_text[:300] + "...")  # Kürzt den Text für eine saubere Vorschau
            count += 1

# Sicherheits-Dummy falls die Seite komplett leer sein sollte
if len(fg.entry()) == 0:
    fe = fg.add_entry()
    fe.id(url)
    fe.title('Wartung: Feed wird aktualisiert')
    fe.link(href=url)
    fe.description('Der RSS-Feed wird im Hintergrund neu generiert.')

# 4. Datei speichern
fg.rss_file('feed.xml')
print("RSS-Feed erfolgreich mit getrennten Artikeln generiert!")
