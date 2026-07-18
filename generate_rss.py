headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

try:
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
except Exception as e:
    print(f"Fehler beim Laden der Seite: {e}")
    soup = None

log_entries = []

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
                link = 'https://www.lok-report.de' + link
            
            if any(x in link for x in ["laenderuebersicht", "kontakt", "impressum", "datenschutz"]):
                continue
                
            desc_text = ""
            pub_date = None
            image_url = None
            
            # Textblock des Artikels einsammeln
            html_block = ""
            next_node = title_element.find_next_sibling()
            while next_node and next_node.name != 'h2' and len(html_block) < 4000:
                html_block += str(next_node)
                
                if not image_url:
                    img_element = next_node.find('img') if hasattr(next_node, 'find') else None
                    if img_element and img_element.get('src'):
                        img_src = img_element['src']
                        image_url = img_src if img_src.startswith('http') else 'https://www.lok-report.de' + img_src
                
                next_node = next_node.find_next_sibling()
            
            block_soup = BeautifulSoup(html_block, 'html.parser')
            raw_text = block_soup.get_text('\n')
            
            # Zeilenweise Prüfung auf das Datumsmuster
            clean_lines = []
            for line in raw_text.split('\n'):
                line_str = line.strip()
                if not line_str:
                    continue
                
                # Wenn wir einen Wochentag oder Monatsnamen mit Doppelpunkt in der Zeile finden
                if any(m in line_str for m in MONTHS_MAP.keys()) and ":" in line_str:
                    parsed = parse_german_date(line_str)
                    if parsed:
                        pub_date = parsed
                        continue # Datumszeile wird im Vorschautext übersprungen
                
                clean_lines.append(line_str)
            
            desc_text = " ".join(clean_lines)
            desc_text = re.sub(r'\s+', ' ', desc_text).strip()
            if not desc_text:
                desc_text = title_text
            
            # Logeintrag schreiben
            date_str_log = pub_date.strftime('%Y-%m-%d %H:%M:%S %z') if pub_date else "KEIN DATUM GEFUNDEN"
            log_entries.append(f"[{date_str_log}] {title_text}")
            
            # RSS-Eintrag hinzufügen
            fe = fg.add_entry()
            if pub_date:
                fe.id(f"{link}?v={int(pub_date.timestamp())}")
                fe.pubDate(pub_date)
            else:
                fe.id(link)
                fe.pubDate(datetime.now().astimezone())
                
            fe.title(title_text)
            fe.link(href=link)
            
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

if ENABLE_LOGGING:
    current_run = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== LOG DURCHLAUF VOM {current_run} ===\n")
        f.write("\n".join(log_entries))
        f.write("\n")

print("RSS-Feed erfolgreich generiert!")
