# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import re
import time
import urllib.request
import urllib.parse
import ssl
from datetime import datetime

# Enigma2 importi
from Screens.Screen import Screen
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.ScrollLabel import ScrollLabel
from Components.ProgressBar import ProgressBar
from Components.Pixmap import Pixmap
from enigma import eTimer, gFont, RT_HALIGN_LEFT, RT_VALIGN_CENTER

# SSL za neprovjerene certifikate
ssl._create_default_https_context = ssl._create_unverified_context

# === KONSTANTE ===
PLUGIN_PATH = os.path.dirname(__file__)
OPENDIR_FILE = os.path.join(PLUGIN_PATH, "opendir.txt")
TMP_PATH = "/tmp/ciefpvibes_opendir/"
os.makedirs(TMP_PATH, exist_ok=True)


# === PUTANJA ZA ČUVANJE M3U FAJLOVA ===
def get_storage_path():
    """Vraća putanju gdje će se čuvati M3U fajlovi (prvo USB/HDD, onda tmp)"""
    # Provjeri uobičajene lokacije za USB i HDD
    storage_locations = [
        "/media/hdd",  # HDD
        "/media/usb",  # USB
        "/media/usb1",  # USB1
        "/media/usb2",  # USB2
        "/media/sda1",  # SDA1
        "/media/sdb1",  # SDB1
        "/hdd",  # Alternativni HDD
    ]

    for location in storage_locations:
        if os.path.exists(location) and os.path.ismount(location):
            # Provjeri da li je pogon montiran i ima dovoljno prostora
            try:
                stat = os.statvfs(location)
                free_space = stat.f_bavail * stat.f_frsize
                if free_space > 10 * 1024 * 1024:  # Minimalno 10MB slobodno
                    m3u_dir = os.path.join(location, "CiefpVibes_M3U")
                    os.makedirs(m3u_dir, exist_ok=True)
                    print(f"[OpenDir] Using storage: {m3u_dir}")
                    return m3u_dir
            except:
                pass

    # Ako nema USB/HDD, koristi tmp
    tmp_dir = "/tmp/ciefpvibes_opendir/"
    os.makedirs(tmp_dir, exist_ok=True)
    print(f"[OpenDir] Using temp storage: {tmp_dir}")
    return tmp_dir


# Globalna putanja za M3U fajlove
M3U_STORAGE_PATH = get_storage_path()

# Inicijalizuj fajl ako ne postoji
if not os.path.exists(OPENDIR_FILE):
    with open(OPENDIR_FILE, "w") as f:
        f.write("# CiefpVibes OpenDirectory Sources\n")
        f.write("# Jedan URL po liniji\n")
        f.write("http://dora-robo.com/muzyka/70's-80's-90's%20/\n")


# =================================== GLAVNI EKRAN ===================================
class OpenDirectoryMain(Screen):
    """Glavni ekran za OpenDirectory - lista sačuvanih izvora"""

    def buildSkin(self):
        return '''
        <screen position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="transparent">

            <!-- Pozadina -->
            <ePixmap pixmap="%s/backgrounds/background7.png" position="0,0" size="1920,1080" alphatest="blend" zPosition="-1"/>

            <!-- Naslov -->
            <widget name="title" position="50,50" size="1150,60"
                font="Regular;42" foregroundColor="#FFFFFF"
                transparent="1" zPosition="4" text="🌐 OpenDirectory Sources"/>

            <!-- Lista izvora -->
            <widget source="sources_list" render="Listbox"
                position="50,120" size="1150,750"
                transparent="1" scrollbarMode="showOnDemand" zPosition="2">

                <convert type="TemplatedMultiContent">
                    {"template": [
                        MultiContentEntryText(
                            pos=(20, 8),
                            size=(1080, 40),
                            font=0,
                            flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER,
                            text=0
                        )
                    ],
                    "fonts": [gFont("Regular", 32)],
                    "itemHeight": 52}
                </convert>
            </widget>

            <!-- Slika desno -->
            <ePixmap pixmap="%s/opendir.png" position="1220,120" size="650,750" alphatest="on" zPosition="1"/>

            <!-- Status -->
            <widget name="status" position="50,890" size="1150,40"
                font="Regular;28" foregroundColor="#00ff00"
                transparent="1" zPosition="4"/>

            <!-- Infobar -->
            <ePixmap pixmap="%s/infobars/infobar7.png" position="0,880" size="1920,140" alphatest="blend" zPosition="1"/>

            <!-- Dugmad -->
            <widget name="key_red" position="60,950" size="260,50"
                font="Regular;32" foregroundColor="#ff5555"
                transparent="1" zPosition="3" text="🔴 Back"/>

            <widget name="key_green" position="350,950" size="260,50"
                font="Regular;32" foregroundColor="#55ff55"
                transparent="1" zPosition="3" text="🟢 Add"/>

            <widget name="key_yellow" position="640,950" size="300,50"
                font="Regular;32" foregroundColor="#ffdd55"
                transparent="1" zPosition="3" text="🟡 Edit/Delete"/>

            <widget name="key_blue" position="980,950" size="300,50"
                font="Regular;32" foregroundColor="#5599ff"
                transparent="1" zPosition="3" text="🔵 Scrape All"/>

        </screen>''' % (PLUGIN_PATH, PLUGIN_PATH, PLUGIN_PATH)


    def __init__(self, session, main_screen):
        self.skin = self.buildSkin()
        Screen.__init__(self, session)
        self.session = session
        self.main = main_screen
        
        self.sources = []
        
        self["title"] = Label("")
        from Components.Sources.List import List
        self["sources_list"] = List([])
        self["status"] = Label("")
        self["key_red"] = Label("")
        self["key_green"] = Label("")
        self["key_yellow"] = Label("")
        self["key_blue"] = Label("")
        
        self["actions"] = ActionMap(["ColorActions", "OkCancelActions", "DirectionActions"], {
            "red": self.close,
            "green": self.add_source,
            "yellow": self.edit_delete_menu,
            "blue": self.scrape_selected_source,
            "ok": self.browse_selected,
            "cancel": self.close,
            "up": self.up,
            "down": self.down,
        }, -1)
        
        self.load_sources()
        self.onLayoutFinish.append(self.update_status)
    
    def up(self):
        self["sources_list"].up()
    
    def down(self):
        self["sources_list"].down()

    def load_sources(self):
        """Učitava URL-ove iz fajla - SAMO ZA PRIKAZ dekodira nazive"""
        self.sources = []
        try:
            with open(OPENDIR_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    if '|' in line:
                        name, url = line.split("|", 1)
                        name = urllib.parse.unquote(name.strip())  # DEKODIRAJ SAMO ZA PRIKAZ
                        self.sources.append((name, url.strip()))
                    elif line.startswith(('http://', 'https://')):
                        url = line
                        # DEKODIRAJ SAMO ZA PRIKAZ (URL ostaje originalan)
                        name = url.rstrip('/').split('/')[-1]
                        name = urllib.parse.unquote(name)
                        if not name:
                            name = url.replace('http://', '').replace('https://', '').split('/')[0]
                        self.sources.append((name, url))  # url ostaje originalan!
        except Exception as e:
            print(f"[OpenDir] Load error: {e}")

        display_list = [f"📁 {name}" for name, url in self.sources]
        if not display_list:
            display_list = ["[No sources. Press GREEN to add]"]
        self["sources_list"].setList(display_list)

    def update_status(self):
        count = len(self.sources)
        self["status"].setText(f"Total sources: {count}")
    
    def add_source(self):
        """Dodaje novi OpenDirectory URL"""
        def enter_url(url):
            if not url or not url.strip():
                return
            url = url.strip().rstrip('/') + '/'
            if not url.startswith(('http://', 'https://')):
                self.session.open(MessageBox, "Invalid URL! Must start with http:// or https://", MessageBox.TYPE_ERROR)
                return
            name = url.rstrip('/').split('/')[-1]
            if not name:
                name = url.replace('http://', '').replace('https://', '').split('/')[0]
            self.sources.append((name, url))
            self.save_sources()
            self.load_sources()
            self.update_status()
            self["status"].setText(f"Added: {name}")
        self.session.openWithCallback(enter_url, VirtualKeyBoard, title="Enter OpenDirectory URL:", text="http://")
    
    def save_sources(self):
        """Čuva URL-ove u fajl"""
        try:
            with open(OPENDIR_FILE, "w") as f:
                f.write("# CiefpVibes OpenDirectory Sources\n")
                f.write("# Jedan URL po liniji\n")
                for name, url in self.sources:
                    f.write(f"{url}\n")
        except Exception as e:
            print(f"[OpenDir] Save error: {e}")
    
    def edit_delete_menu(self):
        """Meni za editovanje ili brisanje izvora"""
        idx = self["sources_list"].getSelectedIndex()
        if idx < 0 or idx >= len(self.sources):
            self.session.open(MessageBox, "No source selected!", MessageBox.TYPE_WARNING)
            return
        
        name, url = self.sources[idx]
        choices = [
            ("Edit URL", "edit_url"),
            ("Delete Source", "delete"),
        ]
        
        def callback(choice):
            if not choice:
                return
            action = choice[1]
            if action == "edit_url":
                self.edit_source_url(idx, url)
            elif action == "delete":
                self.delete_source(idx, name)
        
        self.session.openWithCallback(callback, ChoiceBox, title=f"Options for: {name}", list=choices)
    
    def edit_source_url(self, idx, old_url):
        """Mijenja URL izvora"""
        def callback(new_url):
            if new_url and new_url.strip():
                new_url = new_url.strip().rstrip('/') + '/'
                if not new_url.startswith(('http://', 'https://')):
                    self.session.open(MessageBox, "Invalid URL!", MessageBox.TYPE_ERROR)
                    return
                self.sources[idx] = (self.sources[idx][0], new_url)
                self.save_sources()
                self["status"].setText(f"URL updated for: {self.sources[idx][0]}")
        self.session.openWithCallback(callback, VirtualKeyBoard, title="Edit URL:", text=old_url)
    
    def delete_source(self, idx, name):
        """Briše izvor nakon potvrde"""
        def confirm(answer):
            if answer:
                del self.sources[idx]
                self.save_sources()
                self.load_sources()
                self.update_status()
                self["status"].setText(f"Deleted: {name}")
        self.session.openWithCallback(confirm, MessageBox, f"Delete source '{name}'?", MessageBox.TYPE_YESNO)

    # Dodaj novu metodu:
    def scrape_selected_source(self):
        """Pokreće scrape cijelog odabranog izvora"""
        idx = self["sources_list"].getSelectedIndex()
        if idx < 0 or idx >= len(self.sources):
            self.session.open(MessageBox, "No source selected!", MessageBox.TYPE_WARNING)
            return

        name, url = self.sources[idx]

        # Pitaj korisnika za potvrdu (jer može dugo trajati)
        def confirm(answer):
            if answer:
                self.session.open(OpenDirectoryScrape, self.main, url, name)

        self.session.openWithCallback(confirm, MessageBox,
                                      f"⚠️ Scraping entire source can take a long time!\n\n"
                                      f"Source: {name}\n\n"
                                      f"Continue?",
                                      MessageBox.TYPE_YESNO)

    def browse_selected(self):
        """Otvori ContentScreen za odabrani izvor"""
        idx = self["sources_list"].getSelectedIndex()
        if idx < 0 or idx >= len(self.sources):
            self.session.open(MessageBox, "No source selected!", MessageBox.TYPE_WARNING)
            return
        
        name, url = self.sources[idx]
        self.session.open(OpenDirectoryContent, self.main, url, name)


# =================================== CONTENT EKRAN ===================================
class OpenDirectoryContent(Screen):
    """Prikazuje sadržaj OpenDirectory (foldere i audio fajlove)"""

    def buildSkin(self):
        return '''
        <screen position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="transparent">

            <!-- Pozadina -->
            <ePixmap pixmap="%s/backgrounds/background7.png" position="0,0" size="1920,1080" alphatest="blend" zPosition="-1"/>

            <!-- Putanja -->
            <widget name="path_label" position="50,50" size="1820,40"
                font="Regular;30" foregroundColor="#00ff00"
                transparent="1" zPosition="4"/>

            <!-- Lista sadržaja -->
            <widget source="content_list" render="Listbox"
                position="50,100" size="1150,700"
                transparent="1" scrollbarMode="showOnDemand" zPosition="2">

                <convert type="TemplatedMultiContent">
                    {"template": [
                        MultiContentEntryText(
                            pos=(20, 8),
                            size=(1080, 40),
                            font=0,
                            flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER,
                            text=0
                        )
                    ],
                    "fonts": [gFont("Regular", 32)],
                    "itemHeight": 52}
                </convert>
            </widget>

            <!-- Selektovani fajlovi -->
            <widget name="selected_list" position="1220,100" size="650,700"
                font="Regular;26" scrollbarMode="showOnDemand"
                transparent="1" zPosition="2"/>

            <!-- Status -->
            <widget name="status" position="1220,820" size="650,40"
                font="Regular;28" halign="right"
                foregroundColor="#ffff00" transparent="1" zPosition="4"/>

            <!-- Infobar -->
            <ePixmap pixmap="%s/infobars/infobar7.png" position="0,880" size="1920,140" alphatest="blend" zPosition="1"/>

            <!-- Dugmad -->
            <widget name="key_red" position="60,950" size="260,50"
                font="Regular;32" foregroundColor="#ff5555"
                transparent="1" zPosition="3" text="🔴 Back"/>

            <widget name="key_green" position="350,950" size="300,50"
                font="Regular;32" foregroundColor="#55ff55"
                transparent="1" zPosition="3" text="🟢 Play Selected"/>

            <widget name="key_yellow" position="680,950" size="300,50"
                font="Regular;32" foregroundColor="#ffdd55"
                transparent="1" zPosition="3" text="🟡 Load Folder"/>

            <widget name="key_blue" position="1010,950" size="300,50"
                font="Regular;32" foregroundColor="#5599ff"
                transparent="1" zPosition="3" text="🔵 Scrape Folder"/>

        </screen>''' % (PLUGIN_PATH, PLUGIN_PATH)

    def __init__(self, session, main_screen, base_url, source_name):
        self.skin = self.buildSkin()
        Screen.__init__(self, session)
        self.session = session
        self.main = main_screen
        self.base_url = base_url.rstrip('/') + '/'
        self.source_name = source_name
        self.current_url = self.base_url
        self.history = [self.current_url]
        self.content_items = []
        self.selected_files = []  # Lista URL-ova za brzu provjeru
        
        self["path_label"] = Label(self.current_url)
        from Components.Sources.List import List
        self["content_list"] = List([])
        self["selected_list"] = ScrollLabel("")
        self["status"] = Label("")
        self["key_red"] = Label("")
        self["key_green"] = Label("")
        self["key_yellow"] = Label("")
        self["key_blue"] = Label("")
        
        self["actions"] = ActionMap(["ColorActions", "OkCancelActions", "DirectionActions"], {
            "red": self.go_back,
            "green": self.play_selected,
            "yellow": self.load_current_folder,
            "blue": self.scrape_selected_folder,
            "ok": self.toggle_selection,
            "cancel": self.go_back,
            "up": self.up,
            "down": self.down,
        }, -1)
        
        self.load_content()
    
    def up(self):
        self["content_list"].up()
    
    def down(self):
        self["content_list"].down()
    
    def load_content(self):
        """Učitava sadržaj trenutnog URL-a"""
        self["content_list"].setList(["Loading..."])
        self.content_items = []
        
        items = self._parse_directory(self.current_url)
        
        items.sort(key=lambda x: (x[2] != 'folder', x[0].lower()))
        self.content_items = items
        
        display_list = []
        for name, url, typ in items:
            if typ == 'folder':
                display_list.append(f"📁 {name}")
            else:
                # Označi selektovane fajlove
                if (name, url) in self.selected_files:
                    display_list.append(f"✅ {name}")
                else:
                    display_list.append(f"🎵 {name}")
        
        if not display_list:
            display_list = ["[Empty directory]"]
        
        self["content_list"].setList(display_list)
        self["path_label"].setText(f"📂 {self.source_name}: {self.current_url}")
        self.update_selected_list()

    def _parse_directory(self, directory_url):
        """Parsira OpenDirectory i vraća listu (name, url, type)"""
        items = []
        try:
            req = urllib.request.Request(directory_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response = urllib.request.urlopen(req, timeout=15)
            html = response.read().decode('utf-8', errors='ignore')

            links = re.findall(r'<a\s+(?:[^>]*?\s+)?href="([^"]+)"(?:[^>]*?)>(.*?)</a>', html,
                               re.IGNORECASE | re.DOTALL)

            audio_formats = ('.mp3', '.flac', '.m4a', '.aac', '.wav', '.ogg')

            for href, raw_name in links:
                href = href.strip()
                raw_name = raw_name.strip()

                if href.startswith(('?', '#', 'mailto:', 'javascript:')):
                    continue

                # Očisti href (ukloni ? i # dijelove)
                href_clean = href.split('?')[0].split('#')[0]
                if not href_clean or href_clean in ('../', './'):
                    continue

                full_url = urllib.parse.urljoin(directory_url, href_clean)

                display_name = re.sub(r'<[^>]+>', '', raw_name).strip()
                if not display_name or display_name == '..' or '&gt;' in display_name:
                    display_name = urllib.parse.unquote(os.path.basename(href_clean))

                # === POPRAVLJENA LOGIKA ZA PREPOZNAVANJE ===
                # 1. Prvo provjeri da li je audio fajl (po ekstenziji)
                is_audio_file = False
                for fmt in audio_formats:
                    if href_clean.lower().endswith(fmt) or display_name.lower().endswith(fmt):
                        is_audio_file = True
                        break

                # 2. Zatim provjeri da li ima tačku u imenu (možda fajl bez ekstenzije)
                has_extension = '.' in href_clean and not href_clean.endswith('/')

                # 3. Ako je audio fajl - tretiraj kao fajl
                if is_audio_file:
                    # Ukloni / na kraju ako slučajno postoji
                    if full_url.endswith('/'):
                        full_url = full_url[:-1]
                    clean_name = display_name.replace("&amp;", "&").strip()
                    items.append((clean_name, full_url, 'file'))
                # 4. Ako završava sa / - to je folder
                elif href_clean.endswith('/') or full_url.endswith('/'):
                    folder_name = display_name.rstrip('/')
                    if folder_name and folder_name not in ('.', '..'):
                        # Osiguraj da URL za folder završava sa /
                        if not full_url.endswith('/'):
                            full_url += '/'
                        items.append((folder_name, full_url, 'folder'))
                # 5. Ako ima tačku u imenu, možda je fajl (ali ne podržan format)
                elif has_extension:
                    # Preskoči, nije audio
                    pass
                # 6. Inače, tretiraj kao folder
                else:
                    folder_name = display_name.rstrip('/')
                    if folder_name and folder_name not in ('.', '..'):
                        if not full_url.endswith('/'):
                            full_url += '/'
                        items.append((folder_name, full_url, 'folder'))

        except Exception as e:
            print(f"[OpenDir] Parse error: {e}")
            self.session.open(MessageBox, f"Cannot load:\n{directory_url}", MessageBox.TYPE_ERROR, timeout=5)

        return items

    def toggle_selection(self):
        """Toggle selektovanje fajla - dodaje ako nije selektovan, brise ako jeste"""
        idx = self["content_list"].getSelectedIndex()
        if idx < 0 or idx >= len(self.content_items):
            return
        
        name, url, typ = self.content_items[idx]
        
        if typ == 'folder':
            # Folder - uđi u njega
            self.current_url = url
            self.history.append(self.current_url)
            self.load_content()
        elif typ == 'file':
            # Toggle selekciju
            item = (name, url)
            if item in self.selected_files:
                # Ako već postoji, ukloni
                self.selected_files.remove(item)
                self["status"].setText(f"🗑️ Removed: {name[:50]}")
            else:
                # Ako ne postoji, dodaj
                self.selected_files.append(item)
                self["status"].setText(f"✓ Added: {name[:50]}")
            
            # Osvježi prikaz
            self.update_selected_list()
            self.refresh_content_list()
    
    def refresh_content_list(self):
        """Osvježava prikaz liste (da ažurira ✅ oznake)"""
        if not self.content_items:
            return
        
        display_list = []
        for name, url, typ in self.content_items:
            if typ == 'folder':
                display_list.append(f"📁 {name}")
            else:
                if (name, url) in self.selected_files:
                    display_list.append(f"✅ {name}")
                else:
                    display_list.append(f"🎵 {name}")
        
        self["content_list"].setList(display_list)
    
    def update_selected_list(self):
        """Ažurira prikaz selektovanih fajlova"""
        if not self.selected_files:
            self["selected_list"].setText("No files selected.\nPress OK to select files.")
            return
        
        text = f"Selected files ({len(self.selected_files)}):\n" + "-" * 30 + "\n"
        for name, url in self.selected_files[-15:]:
            text += f"✓ {name[:55]}\n"
        
        if len(self.selected_files) > 15:
            text += f"\n... and {len(self.selected_files) - 15} more"
        
        text += "\n\n📌 Press OK again to remove"
        
        self["selected_list"].setText(text)

    def play_selected(self):
        """Reprodukuje selektovane fajlove i čuva M3U na USB/HDD ako je dostupno"""
        if not self.selected_files:
            self.session.open(MessageBox, "No files selected!", MessageBox.TYPE_WARNING)
            return

        # Dekodiraj naziv source-a (%20 → razmak) za prikaz, ali za fajl zamijeni razmake sa _
        safe_name = urllib.parse.unquote(self.source_name)
        safe_name = safe_name.replace(' ', '_')
        safe_name = re.sub(r'[^\w\s-]', '', safe_name).strip()
        safe_name = re.sub(r'[-\s]+', '-', safe_name)

        date_str = datetime.now().strftime("%d.%m.%Y")
        filename = f"{safe_name}_{date_str}.m3u"
        filepath = os.path.join(M3U_STORAGE_PATH, filename)

        file_exists = os.path.exists(filepath)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for name, url in self.selected_files:
                clean_name = name.replace("_", " ").replace(".mp3", "").replace(".flac", "").strip()
                f.write(f"#EXTINF:-1,{clean_name}\n")
                f.write(f"{url}\n")

        storage_type = "USB/HDD" if M3U_STORAGE_PATH.startswith("/media") else "TMP"
        if file_exists:
            self["status"].setText(f"📁 Updated: {filename} ({storage_type})")
        else:
            self["status"].setText(f"📁 Saved: {filename} ({storage_type})")

        display_name = f"OpenDir: {self.source_name} ({len(self.selected_files)} songs)"
        self.main.loadPlaylistFromFile(filepath, display_name)
        self.close()

    def load_current_folder(self):
        """Učitava ceo trenutni folder (sve audio fajlove)"""
        audio_files = []
        for name, url, typ in self.content_items:
            if typ == 'file':
                audio_files.append((name, url))

        if not audio_files:
            self.session.open(MessageBox, "No audio files in this folder!", MessageBox.TYPE_WARNING)
            return

        # Dekodiraj naziv foldera za prikaz, ali za fajl zamijeni razmake sa _
        folder_name_raw = os.path.basename(self.current_url.rstrip('/')) or self.source_name
        safe_name = urllib.parse.unquote(folder_name_raw)
        safe_name = safe_name.replace(' ', '_')
        safe_name = re.sub(r'[^\w\s-]', '', safe_name).strip()
        safe_name = re.sub(r'[-\s]+', '-', safe_name)

        date_str = datetime.now().strftime("%d.%m.%Y")
        filename = f"{safe_name}_{date_str}.m3u"
        filepath = os.path.join(M3U_STORAGE_PATH, filename)

        file_exists = os.path.exists(filepath)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for name, url in audio_files:
                clean_name = name.replace("_", " ").replace(".mp3", "").replace(".flac", "").strip()
                f.write(f"#EXTINF:-1,{clean_name}\n")
                f.write(f"{url}\n")

        storage_type = "USB/HDD" if M3U_STORAGE_PATH.startswith("/media") else "TMP"
        if file_exists:
            self["status"].setText(f"📁 Updated: {filename} ({storage_type})")
        else:
            self["status"].setText(f"📁 Saved: {filename} ({storage_type})")

        display_name = f"OpenDir: {folder_name_raw} ({len(audio_files)} songs)"
        self.main.loadPlaylistFromFile(filepath, display_name)
        self.close()

    # Dodaj novu metodu za scrape odabranog foldera:
    def scrape_selected_folder(self):
        """Scrapuje samo odabrani folder (ne cijeli source)"""
        idx = self["content_list"].getSelectedIndex()
        if idx < 0 or idx >= len(self.content_items):
            self.session.open(MessageBox, "No folder selected!", MessageBox.TYPE_WARNING)
            return

        name, url, typ = self.content_items[idx]

        if typ != 'folder':
            self.session.open(MessageBox, "Please select a FOLDER to scrape!", MessageBox.TYPE_WARNING)
            return

        # Pitaj korisnika za dubinu
        def depth_callback(choice):
            if not choice:
                return
            depth = int(choice[0])
            self.session.open(OpenDirectoryScrape, self.main, url, name, max_depth=depth)

        choices = [
            ("1", "1 level (this folder only)"),
            ("2", "2 levels"),
            ("3", "3 levels"),
            ("5", "5 levels"),
            ("0", "Unlimited (may take long)"),
        ]
        self.session.openWithCallback(depth_callback, ChoiceBox,
                                      title=f"Scrape depth for:\n{name}",
                                      list=choices)

    def go_back(self):
        """Vraća se nazad kroz historiju"""
        if len(self.history) > 1:
            self.history.pop()
            self.current_url = self.history[-1]
            self.load_content()
        else:
            self.close()

# =================================== SCRAPE EKRAN ===================================
class OpenDirectoryScrape(Screen):
    """Screen za rekurzivno skeniranje OpenDirectory"""

    def buildSkin(self):
        return '''
        <screen position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="transparent">
            <ePixmap pixmap="%s/backgrounds/background7.png" position="0,0" size="1920,1080" alphatest="blend" zPosition="-1"/>

            <widget name="info" position="50,50" size="1820,50" font="Regular;32" halign="center" foregroundColor="#00ff00" transparent="1" zPosition="4"/>

            <widget name="progress" position="200,150" size="1520,30" zPosition="2"/>
            <widget name="progress_text" position="200,200" size="1520,40" font="Regular;28" halign="center" transparent="1" zPosition="4"/>

            <widget name="percentage" position="200,250" size="1520,40" font="Regular;26" halign="center" foregroundColor="#ffff00" transparent="1" zPosition="4"/>

            <widget name="current_folder" position="200,300" size="1520,40" font="Regular;24" halign="center" foregroundColor="#00ff00" transparent="1" zPosition="4"/>

            <widget name="stats" position="200,360" size="1520,460" font="Regular;22" scrollbarMode="showOnDemand" transparent="1" zPosition="2"/>

            <ePixmap pixmap="%s/infobars/infobar7.png" position="0,880" size="1920,140" alphatest="blend" zPosition="1"/>

            <widget name="key_red" position="60,950" size="260,50" font="Regular;32" foregroundColor="#ff5555" transparent="1" zPosition="3" text="🔴 Cancel"/>
        </screen>''' % (PLUGIN_PATH, PLUGIN_PATH)

    def __init__(self, session, main_screen, start_url, source_name, max_depth=10):
        self.skin = self.buildSkin()
        Screen.__init__(self, session)
        self.session = session
        self.main = main_screen
        self.start_url = start_url
        self.source_name = source_name
        self.max_depth = max_depth
        self.found_files = []
        self.scanned_folders = 0
        self.total_folders = 0
        self.stop = False
        self.counting_phase = True
        self.folders_to_count = []
        self.temp_folders = []
        self.folders_to_scan = []

        self["info"] = Label(f"🔍 Scraping: {source_name}")
        self["progress"] = ProgressBar()
        self["progress_text"] = Label("Starting...")
        self["percentage"] = Label("")
        self["current_folder"] = Label("")
        self["stats"] = ScrollLabel("")
        self["key_red"] = Label("")

        self["actions"] = ActionMap(["ColorActions", "OkCancelActions"], {
            "red": self.cancel_scrape,
            "cancel": self.cancel_scrape,
        }, -1)

        # Pokreni brojanje foldera
        self.count_timer = eTimer()
        self.count_timer.callback.append(self.count_next)
        self.start_counting()

    def start_counting(self):
        """Počinje brojanje foldera"""
        self["progress_text"].setText("Counting folders...")
        self.folders_to_count = [(self.start_url, 0)]
        self.temp_folders = []
        self.counted_urls = set()  # <-- DODAJ OVO
        self.counting_phase = True
        self.count_timer.start(50, True)

    def count_next(self):
        """Broji sljedeći folder - ali samo ako sadrži audio fajlove"""
        if self.stop:
            self.count_timer.stop()
            return

        if not self.folders_to_count:
            self.total_folders = len(self.temp_folders)
            self.folders_to_scan = self.temp_folders.copy()
            self.count_timer.stop()
            self.start_scan()
            return

        url, depth = self.folders_to_count.pop(0)

        if not hasattr(self, 'counted_urls'):
            self.counted_urls = set()

        if url in self.counted_urls:
            self.count_timer.start(50, True)
            return

        self.counted_urls.add(url)

        if depth <= self.max_depth:
            # Prvo provjeri da li folder ima audio fajlove
            has_audio = self.folder_has_audio_files(url)

            # Dodaj folder samo ako ima audio fajlove ili ako je plitak (depth 0-1)
            if has_audio or depth <= 1:
                self.temp_folders.append((url, depth))

            # Uvijek traži podfoldere (možda oni imaju audio)
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                response = urllib.request.urlopen(req, timeout=10)
                html = response.read().decode('utf-8', errors='ignore')
                links = re.findall(r'<a\s+(?:[^>]*?\s+)?href="([^"]+)"', html, re.IGNORECASE)
                for href in links:
                    href = href.strip().split('?')[0].split('#')[0]
                    if href and href.endswith('/') and href not in ('../', './', '/', '#'):
                        full_url = urllib.parse.urljoin(url, href)
                        full_url = full_url.rstrip('/') + '/'
                        if full_url not in self.counted_urls:
                            self.folders_to_count.append((full_url, depth + 1))
            except:
                pass

        self.count_timer.start(50, True)

    def folder_has_audio_files(self, url):
        """Provjerava da li folder sadrži audio fajlove (MP3, FLAC, M4A, AAC, WAV, OGG)"""
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=10)
            html = response.read().decode('utf-8', errors='ignore')

            audio_formats = ('.mp3', '.flac', '.m4a', '.aac', '.wav', '.ogg')
            links = re.findall(r'<a\s+(?:[^>]*?\s+)?href="([^"]+)"', html, re.IGNORECASE)

            for href in links:
                href = href.strip().lower()
                for fmt in audio_formats:
                    if href.endswith(fmt) or href.endswith(fmt + '/'):
                        return True
            return False
        except:
            return False

    def start_scan(self):
        """Počinje stvarno skeniranje"""
        self.scanned_folders = 0
        self.found_files = []
        self.scanned_urls = set()
        self.empty_folder_count = 0  # <-- DODAJ OVO
        self.counting_phase = False
        self.update_stats()

        # Pokreni skeniranje
        self.scan_timer = eTimer()
        self.scan_timer.callback.append(self.scan_folder)
        self.scan_timer.start(50, True)

    def update_stats(self):
        """Ažurira statistiku sa procentima"""
        # Ako imamo total_folders, koristi to
        if self.total_folders > 0 and not self.counting_phase and hasattr(self, 'folders_to_scan'):
            # Izračunaj preostale foldere
            remaining_folders = len(self.folders_to_scan)
            total_processed = self.scanned_folders
            total_expected = total_processed + remaining_folders

            if total_expected > 0:
                percent = int((total_processed / total_expected) * 100)
                # Ograniči procenat na 0-100
                percent = min(100, max(0, percent))
                self["progress"].setValue(percent)
                self["percentage"].setText(f"Progress: {percent}% ({total_processed}/{total_expected} folders)")
            else:
                self["progress"].setValue(0)
                self["percentage"].setText(f"Scanned: {self.scanned_folders} folders")
        elif self.counting_phase:
            self["progress"].setValue(0)
            self["percentage"].setText(f"Counting folders... ({len(self.temp_folders)} found)")
        else:
            # Ako nemamo total_folders, prikaži samo skenirane
            self["progress"].setValue(0)
            self["percentage"].setText(f"Scanned: {self.scanned_folders} folders")

        text = f"Source: {self.source_name}\n"
        text += f"Found audio files: {len(self.found_files)}\n\n"
        text += f"Folders scanned: {self.scanned_folders}\n"

        if hasattr(self, 'folders_to_scan'):
            text += f"Folders in queue: {len(self.folders_to_scan)}\n"

        if hasattr(self, 'empty_folder_count'):
            text += f"Empty folders in row: {self.empty_folder_count}\n\n"

        text += f"Recent files:\n"
        for name, url in self.found_files[-10:]:
            text += f"  • {name[:60]}\n"
        self["stats"].setText(text)

    def scan_folder(self):
        """Skenira jedan folder i dodaje nove u red - optimizovano za audio fajlove"""
        if self.stop:
            self.finish_scan()
            return

        if not self.folders_to_scan:
            self.finish_scan()
            return

        url, depth = self.folders_to_scan.pop(0)

        # Provjeri da li smo već skenirali ovaj folder
        if hasattr(self, 'scanned_urls') and url in self.scanned_urls:
            if not self.stop:
                self.scan_timer.start(50, True)
            return

        # Zabilježi da smo skenirali ovaj URL
        if not hasattr(self, 'scanned_urls'):
            self.scanned_urls = set()
        self.scanned_urls.add(url)

        self.scanned_folders += 1
        self["current_folder"].setText(f"📁 Scanning: {url[:100]}")
        self.update_stats()

        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=15)
            html = response.read().decode('utf-8', errors='ignore')

            # Pronađi sve linkove
            links = re.findall(r'<a\s+(?:[^>]*?\s+)?href="([^"]+)"', html, re.IGNORECASE)

            # Podržani audio formati
            audio_formats = ('.mp3', '.flac', '.m4a', '.aac', '.wav', '.ogg')

            for href in links:
                href = href.strip()
                if not href or href in ('../', './', '/', '#'):
                    continue

                # Očisti href (ukloni ? i # dijelove)
                href_clean = href.split('?')[0].split('#')[0].strip()
                if not href_clean or href_clean in ('../', './'):
                    continue

                full_url = urllib.parse.urljoin(url, href_clean)

                # === PREPOZNAVANJE FOLDERI I FAJLOVA ===
                # Prvo provjeri da li je audio fajl (po ekstenziji)
                is_audio = False
                for fmt in audio_formats:
                    if href_clean.lower().endswith(fmt):
                        is_audio = True
                        break
                    # Neki serveri dodaju / na kraju i za fajlove
                    if href_clean.lower().endswith(fmt + '/'):
                        is_audio = True
                        href_clean = href_clean.rstrip('/')
                        full_url = full_url.rstrip('/')
                        break

                if is_audio:
                    # Ovo je audio fajl
                    name = urllib.parse.unquote(os.path.basename(href_clean))
                    # Ukloni ekstenziju za prikaz
                    clean_name = name
                    for fmt in audio_formats:
                        if clean_name.lower().endswith(fmt):
                            clean_name = clean_name[:-len(fmt)]
                            break
                    clean_name = clean_name.replace("_", " ").replace("-", " - ").strip()
                    clean_name = clean_name.replace("&amp;", "&").strip()

                    if (clean_name, full_url) not in self.found_files:
                        self.found_files.append((clean_name, full_url))
                        if len(self.found_files) % 10 == 0:
                            self.update_stats()
                elif href_clean.endswith('/') or full_url.endswith('/'):
                    # Ovo je folder - dodaj u red ako nije već skeniran
                    if depth < self.max_depth - 1:
                        # Normalizuj URL za folder (mora imati / na kraju)
                        if not full_url.endswith('/'):
                            full_url += '/'

                        # Provjeri da li već nije u redu ili skeniran
                        if full_url not in self.scanned_urls:
                            already_queued = False
                            for queued_url, q_depth in self.folders_to_scan:
                                if queued_url == full_url:
                                    already_queued = True
                                    break
                            if not already_queued:
                                self.folders_to_scan.append((full_url, depth + 1))
                # Ako nije audio i nije folder, preskoči (slike, zip, pdf...)

        except Exception as e:
            print(f"[OpenDir] Scan error on {url}: {e}")

        if not self.stop:
            self.scan_timer.start(50, True)

    def finish_scan(self):
        """Završava skeniranje i nudi kreiranje playliste"""
        if hasattr(self, 'scan_timer'):
            self.scan_timer.stop()
        if hasattr(self, 'count_timer'):
            self.count_timer.stop()

        self["progress"].setValue(100)
        self["percentage"].setText("Progress: 100% - Complete!")
        self["progress_text"].setText("✅ Scan complete!")
        self["current_folder"].setText("")
        self.update_stats()

        if self.found_files:
            def create_playlist(answer):
                if answer:
                    self.create_playlist()
                else:
                    self.close()

            self.session.openWithCallback(
                create_playlist,
                MessageBox,
                f"✅ Scan complete!\n\n"
                f"Folders scanned: {self.scanned_folders}\n"
                f"Audio files found: {len(self.found_files)}\n\n"
                f"Create playlist?",
                MessageBox.TYPE_YESNO
            )
        else:
            self.session.open(MessageBox, "No audio files found!", MessageBox.TYPE_INFO, timeout=3)
            self.close()

    def create_playlist(self):
        """Kreira playlistu od pronađenih fajlova"""
        # Dekodiraj naziv source-a (%20 → razmak)
        safe_name = urllib.parse.unquote(self.source_name)
        # Zamijeni razmake sa _ za naziv fajla
        safe_name = safe_name.replace(' ', '_')
        # Ukloni specijalne karaktere
        safe_name = re.sub(r'[^\w\s-]', '', safe_name).strip()
        safe_name = re.sub(r'[-\s]+', '-', safe_name)

        date_str = datetime.now().strftime("%d.%m.%Y_%H%M")
        filename = f"{safe_name}_scrape_{date_str}.m3u"
        filepath = os.path.join(M3U_STORAGE_PATH, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for name, url in self.found_files:
                f.write(f"#EXTINF:-1,{name}\n")
                f.write(f"{url}\n")

        storage_type = "USB/HDD" if M3U_STORAGE_PATH.startswith("/media") else "TMP"
        self.session.open(MessageBox,
                          f"✅ Scrape complete!\n\n"
                          f"Files found: {len(self.found_files)}\n"
                          f"Saved: {filename}\n"
                          f"Location: {storage_type}",
                          MessageBox.TYPE_INFO, timeout=5)

        display_name = f"OpenDir Scrape: {self.source_name} ({len(self.found_files)} songs)"
        self.main.loadPlaylistFromFile(filepath, display_name)
        self.close()

    def cancel_scrape(self):
        """Prekida skeniranje i nudi čuvanje pronađenih fajlova"""
        self.stop = True
        if hasattr(self, 'scan_timer'):
            self.scan_timer.stop()
        if hasattr(self, 'count_timer'):
            self.count_timer.stop()

        # Ako je pronađeno nekoliko fajlova, pitaj korisnika da li želi sačuvati
        if len(self.found_files) > 0:
            def save_partial(answer):
                if answer:
                    self.create_partial_playlist()
                else:
                    self.close()

            self.session.openWithCallback(
                save_partial,
                MessageBox,
                f"⚠️ Scan interrupted!\n\n"
                f"Folders scanned: {self.scanned_folders}\n"
                f"Audio files found: {len(self.found_files)}\n\n"
                f"Do you want to save the already found files as a playlist?",
                MessageBox.TYPE_YESNO
            )
        else:
            self.session.open(MessageBox, "No files found. Scan cancelled.", MessageBox.TYPE_INFO, timeout=3)
            self.close()

    def create_partial_playlist(self):
        """Kreira playlistu od pronađenih fajlova (djelimični rezultat)"""
        if not self.found_files:
            self.close()
            return

        # Dekodiraj naziv source-a (%20 → razmak)
        safe_name = urllib.parse.unquote(self.source_name)
        # Zamijeni razmake sa _ za naziv fajla
        safe_name = safe_name.replace(' ', '_')
        safe_name = re.sub(r'[^\w\s-]', '', safe_name).strip()
        safe_name = re.sub(r'[-\s]+', '-', safe_name)

        date_str = datetime.now().strftime("%d.%m.%Y_%H%M")
        filename = f"{safe_name}_partial_{date_str}.m3u"
        filepath = os.path.join(M3U_STORAGE_PATH, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for name, url in self.found_files:
                f.write(f"#EXTINF:-1,{name}\n")
                f.write(f"{url}\n")

        storage_type = "USB/HDD" if M3U_STORAGE_PATH.startswith("/media") else "TMP"
        self.session.open(MessageBox,
                          f"⚠️ Partial scan saved!\n\n"
                          f"Files found: {len(self.found_files)}\n"
                          f"Saved: {filename}\n"
                          f"Location: {storage_type}",
                          MessageBox.TYPE_INFO, timeout=5)

        # Pitaj korisnika da li želi učitati djelimičnu playlistu
        def load_partial(answer):
            if answer:
                display_name = f"OpenDir Partial: {self.source_name} ({len(self.found_files)} songs)"
                self.main.loadPlaylistFromFile(filepath, display_name)
            self.close()

        self.session.openWithCallback(
            load_partial,
            MessageBox,
            f"Do you want to play the partial playlist now?",
            MessageBox.TYPE_YESNO
        )

        def load_partial(answer):
            if answer:
                display_name = f"OpenDir Partial: {self.source_name} ({len(self.found_files)} songs)"
                self.main.loadPlaylistFromFile(filepath, display_name)
            self.close()

        self.session.openWithCallback(
            load_partial,
            MessageBox,
            f"Do you want to play the partial playlist now?",
            MessageBox.TYPE_YESNO
        )
