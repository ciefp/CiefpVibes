# -*- coding: utf-8 -*-
# opendirdownloader.py - OpenDirectory Download Manager for CiefpVibes

import os
import json
import threading
import subprocess
import datetime
import re
import urllib.request
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from enigma import eTimer
from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Label import Label
from Components.Pixmap import Pixmap
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Components.config import ConfigSelection, getConfigListEntry
from Components.ConfigList import ConfigListScreen
from Components.Sources.StaticText import StaticText
from Components.ProgressBar import ProgressBar
from Screens.VirtualKeyBoard import VirtualKeyBoard

# ============= KONFIGURACIJA =============
OPEN_DIR_FILE = "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVibes/opendir.txt"
DOWNLOAD_LOG = "/tmp/ciefpvibes_opendir_downloads.log"
SETTINGS_FILE = "/etc/enigma2/ciefpvibes_opendir_settings.json"
image_path = "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVibes/opendir_info.png"
# Audio ekstenzije koje podržavamo
AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.aac', '.wav', '.ogg', '.m4b')

def get_download_path():
    """Uzima putanju za download iz settings"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                data = json.load(f)
                path = data.get('download_path', '/hdd/movie/CiefpVibes_OpenDirFiles/')
                if not os.path.exists(path):
                    try:
                        os.makedirs(path)
                    except:
                        pass
                return path
    except:
        pass
    
    default_path = '/hdd/movie/CiefpVibes_OpenDirFiles/'
    if not os.path.exists(default_path):
        try:
            os.makedirs(default_path)
        except:
            pass
    return default_path

def save_download_path(path):
    """Čuva putanju za download u settings"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = {}
        
        data['download_path'] = path
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except:
        return False

def log_download(url, title, filepath, success=True, error_msg=""):
    """Loguje download aktivnost"""
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "SUCCESS" if success else "FAILED"
        with open(DOWNLOAD_LOG, 'a') as f:
            f.write(f"\n{'─'*80}\n")
            f.write(f"[{timestamp}] {status}\n")
            f.write(f"TITLE: {title}\n")
            f.write(f"URL: {url}\n")
            if success:
                f.write(f"SAVED: {filepath}\n")
            else:
                f.write(f"ERROR: {error_msg}\n")
            f.write(f"{'─'*80}\n")
    except:
        pass


def get_safe_filename(title):
    """Konvertuje naslov u siguran naziv fajla - bez duplih ekstenzija i sa razmacima"""
    # Prvo ukloni postojeće ekstenzije iz naziva
    clean_title = title
    for ext in AUDIO_EXTENSIONS:
        if clean_title.lower().endswith(ext):
            clean_title = clean_title[:-len(ext)]
            break

    # Zamijeni underscore sa razmacima
    clean_title = clean_title.replace('_', ' ')
    clean_title = clean_title.replace(' - ', ' - ')

    # Ukloni višestruke razmake
    clean_title = re.sub(r'\s+', ' ', clean_title)

    # Trim
    clean_title = clean_title.strip()

    # Ukloni neispravne znakove za filename (dozvoljeni: slova, brojevi, razmak, crtica, tačka)
    safe = "".join([c for c in clean_title if c.isalnum() or c in (' ', '-', '.')]).strip()

    # Zamijeni razmake sa underscore za sigurnost (opciono - može ostati i razmak)
    # safe = safe.replace(' ', '_')  # Ako želiš underscore umjesto razmaka

    # Ograniči dužinu
    if len(safe) > 100:
        safe = safe[:100]

    # Trim trailing space
    safe = safe.rstrip()

    return safe

class OpenDirSettingsScreen(ConfigListScreen, Screen):
    """Screen za podešavanje download putanje"""
    skin = """
    <screen position="center,center" size="1920,1080" title="OpenDirectory Downloader Settings" backgroundColor="#014d16" flags="wfNoBorder">
        <eLabel position="0,0" size="1920,80" backgroundColor="#0f0f0f" zPosition="1" />
        <eLabel text="..:: OpenDirectory Downloader Settings ::.." position="40,20" size="800,45" font="Regular;32" foregroundColor="#ffcc00" backgroundColor="#00000000" transparent="1" zPosition="2" />

        <eLabel position="40,110" size="900,50" backgroundColor="#2a2a2a" zPosition="1" />
        <eLabel text="DOWNLOAD CONFIGURATION" position="60,120" size="400,30" font="Regular;24" foregroundColor="#00ffcc" backgroundColor="#00000000" transparent="1" zPosition="2" />

        <widget name="config" position="40,160" size="900,400" scrollbarMode="showOnDemand" itemHeight="40" font="Regular;26" secondfont="Regular;26" foregroundColor="#ffffff" backgroundColor="#0f0f0f" transparent="1" zPosition="2" />

        <widget name="info_text" position="40,250" size="900,500" font="Regular;24" foregroundColor="#cccccc" backgroundColor="#00000000" transparent="1" valign="top" zPosition="2" />

        <widget name="settings_image" position="980,160" size="900,750" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/CiefpVibes/ciefpsettings.png" scale="1" alphatest="on" zPosition="1" />

        <widget name="HelpWindow" position="0,0" size="1,1" zPosition="-1" transparent="1" />

        <eLabel position="0,960" size="1920,120" backgroundColor="#0f0f0f" zPosition="1" />

        <eLabel position="40,1000" size="30,30" backgroundColor="#ff1111" zPosition="2" />
        <widget source="key_red" render="Label" position="85,1000" size="300,35" font="Regular;26" foregroundColor="#ffffff" backgroundColor="#00000000" transparent="1" zPosition="2" halign="left" />

        <eLabel position="420,1000" size="30,30" backgroundColor="#11ff11" zPosition="2" />
        <widget source="key_green" render="Label" position="465,1000" size="300,35" font="Regular;26" foregroundColor="#ffffff" backgroundColor="#00000000" transparent="1" zPosition="2" halign="left" />

        <eLabel position="800,1000" size="30,30" backgroundColor="#ffff11" zPosition="2" />
        <widget source="key_yellow" render="Label" position="845,1000" size="350,35" font="Regular;26" foregroundColor="#ffffff" backgroundColor="#00000000" transparent="1" zPosition="2" halign="left" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        self["settings_image"] = Pixmap()
        self["info_text"] = Label("")

        self.onLayoutFinish.append(self.setSettingsImage)
        self.onLayoutFinish.append(self.setInfoText)

        # Učitavanje podešavanja
        self.current_settings = {}
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    self.current_settings = json.load(f)
            except:
                pass

        self.saved_path = self.current_settings.get('download_path', '/hdd/movie/CiefpVibes_OpenDirFiles/')

        self.path_choices = [
            ("/hdd/movie/CiefpVibes_OpenDirFiles/", "HDD - /hdd/movie/CiefpVibes_OpenDirFiles/"),
            ("/hdd/OpenDirFiles/", "HDD - /hdd/OpenDirFiles/"),
            ("/usb/movie/OpenDirFiles/", "USB - /usb/movie/OpenDirFiles/"),
            ("/media/hdd/OpenDirFiles/", "Media HDD - /media/hdd/OpenDirFiles/")
        ]

        is_predefined = False
        for choice in self.path_choices:
            if choice[0] == self.saved_path:
                is_predefined = True
                break

        if not is_predefined:
            self.path_choices.append((self.saved_path, "Custom: " + self.saved_path))

        self.path_selector = ConfigSelection(choices=self.path_choices, default=self.saved_path)

        self.list = []
        ConfigListScreen.__init__(self, self.list, session=self.session)

        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Save"))
        self["key_yellow"] = StaticText(_("Custom Path"))

        self["setupActions"] = ActionMap(["SetupActions", "ColorActions"], {
            "red": self.keyCancel,
            "cancel": self.keyCancel,
            "green": self.keySave,
            "ok": self.keySave,
            "yellow": self.openCustomKeyboard
        }, -1)

        self.createSetup()

    def setSettingsImage(self):
        """Postavlja sliku nakon što je widget kreiran"""
        try:
            image_path = "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVibes/ciefpsettings.png"
            if os.path.exists(image_path) and self["settings_image"].instance:
                self["settings_image"].instance.setPixmapFromFile(image_path)
                self["settings_image"].show()
            else:
                self["settings_image"].hide()
        except Exception as e:
            print(f"[OpenDirDownloader] Error setting settings image: {e}")
            self["settings_image"].hide()

    def setInfoText(self):
        """Postavlja info tekst na lijevoj strani"""
        info_message = (
            "Download Path Settings:\n\n"
            "Use LEFT/RIGHT arrows to change\n"
            "between predefined paths\n\n"
            "Press YELLOW button for\n"
            "custom path (Virtual Keyboard)\n\n"
            "Recommendation: Use\n"
            "'New Virtual Keyboard' plugin\n"
            "for better typing experience\n\n"
            "Selected path will be used for\n"
            "all future downloads\n\n"
            "..:: CiefpVibes OpenDirectory ::.."
        )
        self["info_text"].setText(info_message)

    def createSetup(self):
        self.list = []
        self.list.append(getConfigListEntry(_("Download Path:"), self.path_selector))
        self["config"].list = self.list
        self["config"].l.setList(self.list)

    def openCustomKeyboard(self):
        current_val = self.path_selector.value
        self.session.openWithCallback(self.virtualKeyBoardCallback, VirtualKeyBoard,
                                      title=_("Enter Custom Download Path:"), text=current_val)

    def virtualKeyBoardCallback(self, callback):
        if callback:
            new_path = callback
            if not new_path.endswith('/'):
                new_path += '/'

            self.path_choices = [
                ("/hdd/movie/CiefpVibes_OpenDirFiles/", "HDD - /hdd/movie/CiefpVibes_OpenDirFiles/"),
                ("/hdd/OpenDirFiles/", "HDD - /hdd/OpenDirFiles/"),
                ("/usb/movie/OpenDirFiles/", "USB - /usb/movie/OpenDirFiles/"),
                ("/media/hdd/OpenDirFiles/", "Media HDD - /media/hdd/OpenDirFiles/"),
                (new_path, "Custom: " + new_path)
            ]
            self.path_selector.setChoices(self.path_choices)
            self.path_selector.value = new_path
            self.createSetup()

    def keySave(self):
        final_path = self.path_selector.value
        if final_path and not final_path.endswith('/'):
            final_path += '/'

        settings_data = {}
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    settings_data = json.load(f)
            except:
                pass

        settings_data['download_path'] = final_path

        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings_data, f, indent=4)
            print(f"[OpenDirDownloader] Settings saved. Path: {final_path}")
        except Exception as e:
            print(f"[OpenDirDownloader] Error saving settings: {e}")

        self.close(True)

    def keyCancel(self):
        self.close(False)

class OpenDirectoryBrowser:
    """Klasa za browsing OpenDirectory strukture"""
    
    def __init__(self):
        self.current_url = ""
        self.current_items = []
        self.breadcrumb = []
        self.session = None
        
    def load_urls_from_file(self):
        """Učitava URL adrese iz opendir.txt fajla"""
        urls = []
        if os.path.exists(OPEN_DIR_FILE):
            try:
                with open(OPEN_DIR_FILE, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            urls.append(line)
            except Exception as e:
                print(f"[OpenDirDownloader] Error reading {OPEN_DIR_FILE}: {e}")
        
        # Default test URL ako je fajl prazan
        if not urls:
            urls = ["http://www.example.com/opendir/"]
        
        return urls
    
    def browse_url(self, url):
        """Učitava sadržaj URL-a i parsira linkove"""
        self.current_url = url
        self.current_items = []
        
        try:
            # Dodaj / na kraj ako nema
            if not url.endswith('/'):
                url += '/'
            
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', errors='ignore')
                
            # Parsiraj HTML za linkove
            soup = BeautifulSoup(html, 'html.parser')
            
            # Pronađi sve a linkove
            for link in soup.find_all('a'):
                href = link.get('href', '')
                if href and href not in ('/', '../', '?', '#', ''):
                    # Izbjegni parent directory
                    if href == '../':
                        continue
                    
                    full_url = urljoin(url, href)
                    name = href.rstrip('/').split('/')[-1] if href.endswith('/') else href.split('/')[-1]
                    if not name:
                        name = href
                    
                    # Dekodiraj URL enkodirane karaktere
                    try:
                        name = urllib.parse.unquote(name)
                    except:
                        pass
                    
                    # Da li je folder (završava se sa /)
                    is_dir = href.endswith('/')
                    
                    # Da li je audio fajl
                    is_audio = False
                    if not is_dir:
                        ext = os.path.splitext(name)[1].lower()
                        is_audio = ext in AUDIO_EXTENSIONS
                    
                    self.current_items.append({
                        'name': name,
                        'url': full_url,
                        'is_dir': is_dir,
                        'is_audio': is_audio
                    })
            
            # Sortiraj: folderi prvo, pa fajlovi
            self.current_items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
            
            return True
            
        except Exception as e:
            print(f"[OpenDirDownloader] Error browsing {url}: {e}")
            self.current_items = [{'name': f'Error: {str(e)}', 'url': None, 'is_dir': False, 'is_audio': False}]
            return False
    
    def go_into(self, item):
        """Ulazi u folder ili selektuje fajl"""
        if item['is_dir']:
            self.breadcrumb.append(self.current_url)
            self.browse_url(item['url'])
            return 'folder'
        elif item['is_audio']:
            return 'file'
        else:
            return 'skip'
    
    def go_back(self):
        """Vraća se na prethodni folder"""
        if self.breadcrumb:
            prev_url = self.breadcrumb.pop()
            self.browse_url(prev_url)
            return True
        return False


class OpenDirDownloaderScreen(Screen):
    """Glavni ekran za OpenDirectory download menadžer"""
    
    skin = """
        <screen position="center,center" size="1920,1080" title="OpenDirectory Downloader" backgroundColor="#014d16" flags="wfNoBorder">
            <eLabel position="0,0" size="1920,80" backgroundColor="#0f0f0f" zPosition="1" />
            <widget name="title" position="40,20" size="900,45" font="Regular;32" foregroundColor="#ffcc00" backgroundColor="#00000000" transparent="1" zPosition="2" />

            <eLabel position="40,110" size="900,50" backgroundColor="#2a2a2a" zPosition="1" />
            <eLabel text="OPENDIRECTORY BROWSER" position="60,120" size="400,30" font="Regular;24" foregroundColor="#00ffcc" backgroundColor="#00000000" transparent="1" zPosition="2" />
            <widget name="left_list" position="40,160" size="900,600" scrollbarMode="showOnDemand" itemHeight="40" font="Regular;24" foregroundColor="#ffffff" backgroundColor="#0f0f0f" zPosition="2" />

            <eLabel position="980,110" size="900,50" backgroundColor="#2a2a2a" zPosition="1" />
            <eLabel text="SELECTED FILES" position="1000,120" size="400,30" font="Regular;24" foregroundColor="#00ffcc" backgroundColor="#00000000" transparent="1" zPosition="2" />
            <widget name="right_list" position="980,160" size="900,600" scrollbarMode="showOnDemand" itemHeight="40" font="Regular;24" foregroundColor="#ffffff" backgroundColor="#0f0f0f" zPosition="2" />

            <widget name="current_path" position="40,780" size="1800,35" font="Regular;22" foregroundColor="#FFFFFF" backgroundColor="#00000000" transparent="1" zPosition="2" />

            <eLabel position="40,820" size="1840,120" backgroundColor="#2a2a2a" zPosition="1" />

            <widget name="progress_bar" position="60,830" size="1800,20" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/CiefpVibes/icons/progress.png" backgroundColor="#0d0c0c" zPosition="3" />

            <widget name="status_line1" position="60,865" size="1300,35" font="Regular;24" foregroundColor="#dbfc00" backgroundColor="#00000000" transparent="1" halign="left" zPosition="4" />
            <widget name="status_line2" position="60,900" size="1300,30" font="Regular;22" foregroundColor="#00ff0d" backgroundColor="#00000000" transparent="1" halign="left" zPosition="4" />

            <widget name="info" position="1380,865" size="480,35" font="Regular;24" halign="right" foregroundColor="#ffcc00" backgroundColor="#00000000" transparent="1" zPosition="4" />
            
            <!-- SLIKA na desnoj strani -->
            <widget name="info_image" position="1600,960" size="200,120"  pixmap="/usr/lib/enigma2/python/Plugins/Extensions/CiefpVibes/opendir_info.png" scale="1" alphatest="on" zPosition="2" />
           
            <eLabel position="0,960" size="1920,120" backgroundColor="#0f0f0f" zPosition="1" />

            <eLabel position="40,1000" size="30,30" backgroundColor="#ff1111" zPosition="2" />
            <widget source="key_red" render="Label" position="85,1000" size="300,35" font="Regular;26" foregroundColor="#ffffff" backgroundColor="#00000000" transparent="1" zPosition="2" halign="left" />

            <eLabel position="420,1000" size="30,30" backgroundColor="#11ff11" zPosition="2" />
            <widget source="key_green" render="Label" position="465,1000" size="300,35" font="Regular;26" foregroundColor="#ffffff" backgroundColor="#00000000" transparent="1" zPosition="2" halign="left" />

            <eLabel position="820,1000" size="30,30" backgroundColor="#ffff11" zPosition="2" />
            <widget source="key_yellow" render="Label" position="865,1000" size="300,35" font="Regular;26" foregroundColor="#ffffff" backgroundColor="#00000000" transparent="1" zPosition="2" halign="left" />

            <eLabel position="1220,1000" size="30,30" backgroundColor="#1111ff" zPosition="2" />
            <widget source="key_blue" render="Label" position="1265,1000" size="400,35" font="Regular;26" foregroundColor="#ffffff" backgroundColor="#00000000" transparent="1" zPosition="2" halign="left" />
        </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.selected_files = []
        self.is_downloading = False
        self.focus = "left"
        
        # Inicijalizacija browsera
        self.browser = OpenDirectoryBrowser()
        self.root_urls = self.browser.load_urls_from_file()
        self.current_url_list = self.root_urls
        self.current_mode = "root"  # root ili browse
        
        # Menu liste
        self.left_menu_list = []
        self.right_menu_list = []
        
        # Download manager
        self.download_manager = None
        self.download_queue = []
        self.current_download_index = 0
        self.total_downloads = 0
        self.completed_downloads = 0
        
        # Timer za UI update tokom downloada
        self.update_timer = eTimer()
        self.update_timer.callback.append(self.update_download_status)
        
        # Definisanje Enigma2 komponenti
        self["left_list"] = MenuList(self.left_menu_list)
        self["right_list"] = MenuList(self.right_menu_list)
        self["title"] = Label(_("..:: OpenDirectory Downloader ::.."))
        self["current_path"] = Label("")
        self["info"] = Label("")
        self["info_image"] = Pixmap()
        self["progress_bar"] = ProgressBar()
        self["status_line1"] = Label(_("Ready. Select files from OpenDirectory."))
        self["status_line2"] = Label("")
        
        # Dugmići
        self["key_red"] = StaticText(_("Exit"))
        self["key_green"] = StaticText(_("Settings"))
        self["key_yellow"] = StaticText(_("Download"))
        self["key_blue"] = StaticText(_("Select All"))
        
        # Akcije tastera
        self["actions"] = ActionMap(["SetupActions", "ColorActions", "DirectionActions"], {
            "cancel": self.exit,
            "ok": self.select_item,
            "red": self.exit,
            "green": self.open_settings,
            "yellow": self.download_selected,
            "blue": self.select_all_files,
            "left": self.focus_left,
            "right": self.focus_right,
            "up": self.move_up,
            "down": self.move_down,
            "menu": self.go_back
        }, -1)
        
        self.onLayoutFinish.append(self.layoutFinished)
    
    def layoutFinished(self):
        self.load_root_urls()
        self.refresh_right_panel()
        self.update_info()
        self.setInfoImage()

    def setInfoImage(self):
        """Postavlja sliku na desnoj strani"""
        try:
            image_path = "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVibes/opendir_info.png"
            if os.path.exists(image_path) and self["info_image"].instance:
                self["info_image"].instance.setPixmapFromFile(image_path)
                self["info_image"].show()
            else:
                self["info_image"].hide()
                print(f"[OpenDirDownloader] Info image not found: {image_path}")
        except Exception as e:
            print(f"[OpenDirDownloader] Error setting info image: {e}")
            self["info_image"].hide()
    
    def load_root_urls(self):
        """Učitava početne URL adrese iz fajla"""
        self.current_mode = "root"
        self.current_url_list = self.root_urls
        
        menu_list = []
        for idx, url in enumerate(self.root_urls):
            # Skrati URL za prikaz
            display_url = url[:70] + "..." if len(url) > 70 else url
            menu_list.append((f"🌐 {display_url}", {'type': 'url', 'url': url, 'idx': idx}))
        
        if not menu_list:
            menu_list = [("No URLs found in opendir.txt", None)]
        
        self["left_list"].setList(menu_list)
        self["current_path"].setText("OpenDirectory Sources")
    
    def browse_directory(self, url, display_name=""):
        """Učitava sadržaj direktorijuma"""
        self.current_mode = "browse"
        self["status_line1"].setText(f"Loading: {url[:60]}...")
        
        success = self.browser.browse_url(url)
        
        if success:
            menu_list = []
            # Dodaj "Go Back" opciju
            menu_list.append(("📁 .. (Go Back)", {'type': 'back'}))
            
            for item in self.browser.current_items:
                if item['is_dir']:
                    icon = "📁"
                    item_type = 'folder'
                elif item['is_audio']:
                    icon = "🎵"
                    item_type = 'audio'
                else:
                    icon = "📄"
                    item_type = 'other'
                
                name = item['name'][:60] if len(item['name']) > 60 else item['name']
                menu_list.append((f"{icon} {name}", {
                    'type': item_type,
                    'name': item['name'],
                    'url': item['url'],
                    'is_dir': item['is_dir'],
                    'is_audio': item['is_audio']
                }))
            
            self["left_list"].setList(menu_list)
            self["current_path"].setText(url[:80] + "..." if len(url) > 80 else url)
            self["status_line1"].setText(_("Browse mode. Use OK to enter folders or select files."))
        else:
            self["status_line1"].setText(_("Error loading directory!"))
            self.load_root_urls()
    
    def select_item(self):
        """Selektuje stavku - OK dugme"""
        if self.is_downloading:
            return
        
        if self.focus == "left":
            current = self["left_list"].getCurrent()
            if not current:
                return
            
            value = current[1]
            if not value:
                return
            
            # Root URL mod
            if value.get('type') == 'url':
                url = value.get('url')
                display = current[0].replace("🌐 ", "")[:50]
                self.browser.breadcrumb = []
                self.browse_directory(url, display)
                return
            
            # Browse mod
            item_type = value.get('type')
            
            if item_type == 'back':
                self.go_back()
                return
            
            if value.get('is_dir'):
                # Folder - uđi u njega
                self.browser.go_into({
                    'is_dir': True,
                    'url': value.get('url'),
                    'name': value.get('name')
                })
                self.browse_directory(value.get('url'), value.get('name'))
                return
            
            if value.get('is_audio'):
                # Audio fajl - selektuj ga
                file_info = {
                    'name': value.get('name'),
                    'url': value.get('url'),
                    'size': value.get('size', 0)
                }
                
                # Proveri da li već postoji u listi
                exists = False
                for f in self.selected_files:
                    if f.get('url') == file_info['url']:
                        exists = True
                        break
                
                if not exists:
                    self.selected_files.append(file_info)
                    self.refresh_right_panel()
                    self.update_info()
                    self["status_line1"].setText(f"Added: {file_info['name'][:50]}")
                else:
                    self["status_line1"].setText(f"Already in list: {file_info['name'][:50]}")
                return
        
        elif self.focus == "right":
            current = self["right_list"].getCurrent()
            if current and current[1] is not None:
                if current[1] == "clear":
                    self.selected_files = []
                    self.refresh_right_panel()
                    self.update_info()
                    self["status_line1"].setText(_("All files cleared from selection"))
                elif isinstance(current[1], int):
                    idx = current[1]
                    if idx < len(self.selected_files):
                        removed = self.selected_files.pop(idx)
                        self.refresh_right_panel()
                        self.update_info()
                        self["status_line1"].setText(f"Removed: {removed.get('name', 'Unknown')[:50]}")

    def select_all_files(self):
        """Selektuje sve audio fajlove u trenutno otvorenom folderu"""
        if self.is_downloading:
            self.session.open(MessageBox, _("Download in progress! Cannot select files."), MessageBox.TYPE_INFO)
            return

        if self.focus != "left":
            self.focus_left()

        # Provjeri da li smo u browse modu (ne u root-u)
        if self.current_mode != "browse":
            self.session.open(MessageBox, _("Please open a folder first!"), MessageBox.TYPE_INFO)
            return

        # Sakupi sve audio fajlove iz trenutne liste
        audio_files = []
        current_list = self["left_list"].getList()

        if not current_list:
            return

        for item in current_list:
            value = item[1]
            if value and isinstance(value, dict):
                if value.get('is_audio') and value.get('type') == 'audio':
                    audio_files.append({
                        'name': value.get('name'),
                        'url': value.get('url')
                    })

        if not audio_files:
            self.session.open(MessageBox, _("No audio files found in this folder!"), MessageBox.TYPE_INFO)
            return

        # Dodaj sve fajlove koji nisu već u listi
        existing_urls = {f.get('url') for f in self.selected_files}
        new_count = 0

        for audio_file in audio_files:
            if audio_file.get('url') not in existing_urls:
                self.selected_files.append(audio_file)
                new_count += 1

        self.refresh_right_panel()
        self.update_info()

        if new_count > 0:
            self["status_line1"].setText(_("Added {} audio file(s) from current folder").format(new_count))
            self["status_line2"].setText(_("Total selected: {} files").format(len(self.selected_files)))
        else:
            self["status_line1"].setText(_("All files already selected!"))

    def refresh_right_panel(self):
        """Osvježava desni panel sa selektovanim fajlovima"""
        if not self.selected_files:
            self["right_list"].setList([("No files selected", None)])
            return

        menu_list = []
        for idx, file_info in enumerate(self.selected_files):
            # Prikaži ljepše ime (bez underscore)
            name = file_info.get('name', 'Unknown')
            # Očisti za prikaz
            display_name = name.replace('_', ' ')
            display_name = display_name.replace('_-_', ' - ')
            display_name = re.sub(r'\s+', ' ', display_name).strip()
            # Ukloni ekstenziju za prikaz
            for ext in AUDIO_EXTENSIONS:
                if display_name.lower().endswith(ext):
                    display_name = display_name[:-len(ext)]
                    break
            display_name = display_name[:55]
            menu_list.append((f"[{idx + 1}] {display_name}", idx))

        menu_list.append(("-" * 40, "separator"))
        menu_list.append(("🗑️ Clear all selected", "clear"))

        self["right_list"].setList(menu_list)

    def download_selected(self):
        """Pokreće download selektovanih fajlova"""
        if not self.selected_files:
            self.session.open(MessageBox, _("No files selected! Use OK to add files from OpenDirectory."), MessageBox.TYPE_INFO)
            return
        
        if self.is_downloading:
            self.session.open(MessageBox, _("Download already in progress! Please wait."), MessageBox.TYPE_INFO)
            return
        
        # Potvrda za download
        self.session.openWithCallback(
            self.confirm_download,
            MessageBox,
            _("Start downloading {} file(s)?\n\nDestination: {}").format(len(self.selected_files), get_download_path()),
            MessageBox.TYPE_YESNO
        )
    
    def confirm_download(self, result):
        if not result:
            return
        
        self.start_download()
    
    def start_download(self):
        """Pokreće download queue"""
        self.is_downloading = True
        self.total_downloads = len(self.selected_files)
        self.completed_downloads = 0
        self.current_download_index = 0
        self.download_queue = self.selected_files.copy()
        
        self["progress_bar"].setValue(0)
        self["status_line1"].setText(_("Starting downloads..."))
        self["status_line2"].setText(_("0 of {} files").format(self.total_downloads))
        
        # Pokreni prvi download
        self.start_next_download()
    
    def start_next_download(self):
        """Pokreće sledeći download u queue-u"""
        if self.current_download_index >= len(self.download_queue):
            # Svi downloadi završeni
            self.download_complete()
            return
        
        file_info = self.download_queue[self.current_download_index]
        url = file_info.get('url')
        name = file_info.get('name', 'Unknown')
        
        percent = int((self.current_download_index / self.total_downloads) * 100) if self.total_downloads > 0 else 0
        self["progress_bar"].setValue(percent)
        self["status_line1"].setText(_("Downloading: {}").format(name[:60]))
        self["status_line2"].setText(_("File {}/{} ({:.0f}%)").format(self.current_download_index + 1, self.total_downloads, percent))
        
        # Pokreni download u threadu
        thread = threading.Thread(target=self.download_file, args=(url, name, self.current_download_index), daemon=True)
        thread.start()

    def download_file(self, url, filename, index):
        """Skida jedan fajl - ispravljeno dupliranje ekstenzije i lepši naziv"""
        download_path = get_download_path()

        # Prvo očisti filename (ukloni underscore, duple ekstenzije)
        clean_name = filename

        # Ukloni postojeće ekstenzije iz naziva
        for ext in AUDIO_EXTENSIONS:
            if clean_name.lower().endswith(ext):
                clean_name = clean_name[:-len(ext)]
                break

        # Zamijeni underscore sa razmacima za ljepši naziv
        clean_name = clean_name.replace('_', ' ')
        clean_name = clean_name.replace('_-_', ' - ')
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()

        # Sada napravi safe filename (bez ekstenzije)
        safe_name = get_safe_filename(clean_name)

        # Odredi ekstenziju (prvo iz URL-a, onda iz filename, onda default)
        url_path = url.split('?')[0]
        ext = os.path.splitext(url_path)[1].lower()

        if not ext or ext not in AUDIO_EXTENSIONS:
            # Pokušaj iz originalnog filename-a
            for check_ext in AUDIO_EXTENSIONS:
                if filename.lower().endswith(check_ext):
                    ext = check_ext
                    break

        if not ext or ext not in AUDIO_EXTENSIONS:
            ext = '.mp3'

        # Konačna putanja - samo JEDNA ekstenzija!
        output_filename = safe_name + ext
        output_path = os.path.join(download_path, output_filename)

        # Ako fajl već postoji, dodaj broj
        counter = 1
        while os.path.exists(output_path):
            output_filename = f"{safe_name}_{counter}{ext}"
            output_path = os.path.join(download_path, output_filename)
            counter += 1

        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

            with urllib.request.urlopen(req, timeout=60) as response:
                with open(output_path, 'wb') as f:
                    f.write(response.read())

            # Loguj uspešan download
            log_download(url, filename, output_path, success=True)

            # Ažuriraj UI iz main threada
            from twisted.internet import reactor
            reactor.callFromThread(self.download_finished, index, True, output_path)

        except Exception as e:
            error_msg = str(e)[:100]
            print(f"[OpenDirDownloader] Download error: {error_msg}")
            log_download(url, filename, "", success=False, error_msg=error_msg)

            from twisted.internet import reactor
            reactor.callFromThread(self.download_finished, index, False, error_msg)

    def download_finished(self, index, success, result):
        """Povratni poziv nakon završetka downloada"""
        self.completed_downloads += 1
        self.current_download_index += 1
        
        percent = int((self.completed_downloads / self.total_downloads) * 100) if self.total_downloads > 0 else 0
        self["progress_bar"].setValue(percent)
        
        if success:
            self["status_line1"].setText(_("Completed: {}").format(os.path.basename(result)[:50]))
            self["status_line2"].setText(_("{}/{} files ({:.0f}%)").format(self.completed_downloads, self.total_downloads, percent))
        else:
            self["status_line1"].setText(_("Failed: {}").format(result[:50] if result else "Unknown error"))
            self["status_line2"].setText(_("{}/{} files completed").format(self.completed_downloads, self.total_downloads))
        
        # Pokreni sledeći download
        self.start_next_download()
    
    def download_complete(self):
        """Svi downloadi završeni"""
        self.is_downloading = False
        self["progress_bar"].setValue(100)
        self["status_line1"].setText(_("ALL DOWNLOADS COMPLETED!"))
        self["status_line2"].setText(_("Successfully downloaded {} file(s) to {}").format(self.total_downloads, get_download_path()))
        
        # Opcija za brisanje selektovanih fajlova nakon downloada
        self.session.openWithCallback(
            self.clear_after_download,
            MessageBox,
            _("Downloads completed!\n\nClear selected files list?"),
            MessageBox.TYPE_YESNO
        )
    
    def clear_after_download(self, result):
        if result:
            self.selected_files = []
            self.refresh_right_panel()
            self.update_info()
    
    def update_download_status(self):
        """Timer callback za update UI tokom downloada (ako je potrebno)"""
        pass
    
    def move_up(self):
        """Kretanje gore u listi"""
        if self.focus == "left":
            self["left_list"].up()
        else:
            self["right_list"].up()
    
    def move_down(self):
        """Kretanje dole u listi"""
        if self.focus == "left":
            self["left_list"].down()
        else:
            self["right_list"].down()
    
    def focus_left(self):
        self.focus = "left"
        self.update_info()
    
    def focus_right(self):
        self.focus = "right"
        self.update_info()
    
    def go_back(self):
        """Vraća se nazad u hijerarhiji"""
        if self.current_mode == "browse":
            if self.browser.go_back():
                self.browse_directory(self.browser.current_url)
            else:
                self.load_root_urls()
    
    def open_settings(self):
        """Otvara settings screen"""
        if self.is_downloading:
            self.session.open(MessageBox, _("Cannot change settings while downloading!"), MessageBox.TYPE_ERROR)
            return
        
        self.session.openWithCallback(self.settings_callback, OpenDirSettingsScreen)
    
    def settings_callback(self, changed=False):
        if changed:
            self.update_info()
            self["status_line1"].setText(_("Settings saved. Download path updated."))
    
    def update_info(self):
        """Ažurira info labelu"""
        count = len(self.selected_files)
        focus_text = "◀ LEFT" if self.focus == "left" else "RIGHT ▶"
        download_path = get_download_path()
        short_path = download_path.split('/')[-2] if download_path.endswith('/') else download_path.split('/')[-1]
        self["info"].setText(f"{focus_text} | {short_path} | {count} file(s)")
    
    def exit(self):
        """Izlaz iz plugina"""
        if self.is_downloading:
            self.session.openWithCallback(
                self.confirm_exit,
                MessageBox,
                _("Download in progress! Are you sure you want to exit?"),
                MessageBox.TYPE_YESNO
            )
        else:
            self.close()
    
    def confirm_exit(self, answer):
        if answer:
            self.close()


# ============= PLUGIN ENTRY POINT =============
def main(session, **kwargs):
    """Glavna funkcija za pokretanje plugina"""
    session.open(OpenDirDownloaderScreen)