import os
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

# 1. Webseite abrufen
url = "https://lok-report.de"
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, 'html.parser')

# 2. RSS-Feed initialisieren
fg = FeedGenerator()
fg.id(url)
fg.title('LOK Report News')
fg.author({'name': 'LOK Report Scraper'})
fg.link(href=url, rel='alternate')
fg.description('Inoffizieller RSS-Feed für die LOK Report News')

# 3. HTML-Struktur der LOK-Report-Seite parsen
# Hinweis: Artikel liegen meist in Elementen mit der Klasse "item" oder "article"
articles = soup.select('.item, .article-list-item, article') 

for article in articles[:15]: # Die neuesten 15 Artikel
    title_element = article.select_one('h2 a, h3 a, .title a')
    desc_element = article.select_one('.introtext, .text, p')
    
    if title_element:
        title = title_element.text.strip()
        link = title_element['href']
        if not link.startswith('http'):
            link = 'https://lok-report.de' + link
            
        desc = desc_element.text.strip() if desc_element else title
        
        fe = fg.add_entry()
        fe.id(link)
        fe.title(title)
        fe.link(href=link)
        fe.description(desc)

# 4. Datei speichern
fg.rss_file('feed.xml')
