# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import json 
import shutil
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.List import List
from Components.ServiceEventTracker import ServiceEventTracker
from Components.ProgressBar import ProgressBar
from Components.FileList import FileList
from Components.Pixmap import Pixmap
from Screens.Screen import Screen
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Tools.Directories import fileExists
from enigma import eServiceReference, eTimer, iPlayableService, gFont, iServiceInformation, RT_HALIGN_LEFT, RT_VALIGN_CENTER
from Plugins.Plugin import PluginDescriptor
from urllib.parse import unquote
import urllib.request

PLUGIN_NAME = "CiefpVibes"
PLUGIN_DESC = "Jukebox play music locally and online"
PLUGIN_VERSION = "1.1" 
PLUGIN_DIR = os.path.dirname(__file__) or "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVibes"
# ✅ СПАЈАМО ФОЛДЕРЕ У ЈЕДАН КЕШ ФОЛДЕР
CACHE_DIR = "/tmp/ciefpvibes_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# ✅ GitHub API URL-ovi
GITHUB_M3U_URL = "https://api.github.com/repos/ciefp/CiefpVibesFiles/contents/M3U"
GITHUB_TV_URL  = "https://api.github.com/repos/ciefp/CiefpVibesFiles/contents/TV"
GITHUB_RADIO_URL = "https://api.github.com/repos/ciefp/CiefpVibesFiles/contents/RADIO"

class CiefpVibesMain(Screen):
    def buildSkin(self):
        bg = getattr(self, "current_bg", "background1.png")
        ib = getattr(self, "current_ib", "infobar1.png")

        return '''<?xml version="1.0" encoding="utf-8"?>
        <screen position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="transparent">
            <ePixmap pixmap="%s/backgrounds/%s" position="0,0" size="1920,1080" alphatest="blend" zPosition="-1"/>
            <widget source="playlist" render="Listbox" position="50,100" size="1150,770" transparent="1" scrollbarMode="showOnDemand" selectionPixmap="skin_default/sel.png" zPosition="2">
                <convert type="TemplatedMultiContent">
                    {"template": [
                        MultiContentEntryText(pos=(20, 5), size=(1080, 36), font=0, flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER, text=0),
                        MultiContentEntryText(pos=(20, 42), size=(1080, 24), font=1, flags=RT_HALIGN_LEFT, text=1)
                    ],
                    "fonts": [gFont("Regular", 30), gFont("Regular", 20)],
                    "itemHeight": 70}
                </convert>
            </widget>
            <ePixmap pixmap="%s/infobars/%s" position="0,880" size="1920,140" alphatest="blend" zPosition="1"/>
            <widget name="poster" position="1220,70" size="650,800" alphatest="on" zPosition="1"/>
            <widget name="nowplaying" position="60,900" size="1800,55" font="Regular;40" foregroundColor="#FFFFFF" transparent="1" zPosition="3"/>
            <widget name="elapsed" position="60,965" size="200,40" font="Regular;32" foregroundColor="#ffffff" transparent="1" zPosition="3"/>
            <!-- Progress bar za stvarno vreme -->
            <widget name="progress_real" position="240,985" size="1150,20" pixmap="skin_default/progress_bg.png" zPosition="2"/>
            <!-- Pulsirajući progress bar (zeleni) -->
            <widget name="progress_vibe" position="240,985" size="1150,20" pixmap="%s/progress_green.png" zPosition="3"/>
            <!-- Label za offline status -->
            <widget name="offline_status" position="240,985" size="1150,20" font="Regular;18" foregroundColor="#ff3333" halign="center" valign="center" transparent="0" backgroundColor="#000000" zPosition="4"/>
            <widget name="remaining" position="1420,965" size="350,40" font="Regular;32" foregroundColor="#ffcc00" halign="right" transparent="1" zPosition="3"/>
            <widget name="key_red"    position="60,1030"  size="260,50" font="Regular;32" foregroundColor="#ff5555" transparent="1" zPosition="3"/>
            <widget name="key_green"  position="350,1030" size="260,50" font="Regular;32" foregroundColor="#55ff55" transparent="1" zPosition="3"/>
            <widget name="key_yellow" position="640,1030" size="300,50" font="Regular;32" foregroundColor="#ffdd55" transparent="1" zPosition="3"/>
            <widget name="key_blue"   position="980,1030" size="260,50" font="Regular;32" foregroundColor="#5599ff" transparent="1" zPosition="3"/>
        </screen>''' % (PLUGIN_DIR, bg, PLUGIN_DIR, ib, PLUGIN_DIR)

    def __init__(self, session):
        self["poster"] = Pixmap()
        self.current_bg = "background1.png"
        self.current_ib = "infobar1.png"
        self.current_poster = "poster1.png"
        self.last_playlist_path = "/etc/enigma2/ciefpvibes_last.txt"
        self.loadConfig()
        self.skin = self.buildSkin()
        Screen.__init__(self, session)
        self.session = session
        self.playlist = []
        self.currentIndex = -1
        self.repeat_mode = "off"
        self.shuffle_enabled = False
        self.network_timeout = 30
        self["playlist"] = List([])
        self["nowplaying"] = Label("🌀 Loading...")
        self["key_red"]    = Label("🔴 EXIT")
        self["key_green"]  = Label("🟢 FOLDER")
        self["key_yellow"] = Label("🟡 SETTINGS")
        self["key_blue"]   = Label("🔵 Online Files")
        
        # Dva progress bara
        self["progress_real"] = ProgressBar()
        self["progress_vibe"] = ProgressBar()
        self["progress_real"].setValue(0)
        self["progress_vibe"].setValue(0)
        
        # DODATO: Offline status label
        self["offline_status"] = Label("")
        self["offline_status"].hide()
        self["remaining"] = Label("+0:00")
        self["elapsed"] = Label("0:00")
        
        # Varijable za detekciju stream statusa
        self.stream_active = False
        self.stream_check_counter = 0
        self.last_audio_data_time = 0
        self.vibe_direction = 1  # 1 = raste, -1 = opada
        self.vibe_value = 0
        
        self["actions"] = ActionMap(["ColorActions", "WizardActions", "DirectionActions"], {
            "ok":       self.playSelected,
            "back":     self.exit,
            "up":       self.up,
            "down":     self.down,
            "red":      self.exit,
            "green":    self.openFileBrowser,
            "yellow":   self.openSettings,
            "blue":     self.openGitHubLists,
        }, -1)
        self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
            iPlayableService.evEOF: self.nextTrack,
            iPlayableService.evUpdatedInfo: self.updateProgress,
            iPlayableService.evStart: self.resetProgress,
            iPlayableService.evUser+10: self.onAudioData  # Detekcija audio podataka
        })
        self.progress_timer = eTimer()
        self.progress_timer.callback.append(self.updateProgress)
        self.vibe_timer = eTimer()
        self.vibe_timer.callback.append(self.updateVibeProgress)
        # DODATO: Timer za proveru statusa streama
        self.stream_check_timer = eTimer()
        self.stream_check_timer.callback.append(self.checkStreamStatus)
        
        self.current_duration = 0
        self.current_position = 0
        self.onFirstExecBegin.append(self.loadLastOrDefault)
        self.current_song_info = {"artist": "", "title": ""}
        self.onLayoutFinish.append(self.showDefaultPoster)

    def showDefaultPoster(self):
        """Prikaži default poster pri pokretanju"""
        default_poster = os.path.join(PLUGIN_DIR, "posters", self.current_poster)
        self.showPoster(default_poster)

    def loadConfig(self):
        cfg_path = "/etc/enigma2/ciefpvibes.cfg"
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, "r") as f:
                    for line in f:
                        if line.startswith("bg="):
                            self.current_bg = line[3:].strip() or "background1.png"
                        elif line.startswith("poster="):
                            self.current_poster = line[7:].strip() or "poster1.png"
                        elif line.startswith("ib="):
                            self.current_ib = line[3:].strip() or "infobar1.png"
                        elif line.startswith("repeat="):
                            self.repeat_mode = line[7:].strip() or "off"
                        elif line.startswith("shuffle="):
                            self.shuffle_enabled = line[8:].strip().lower() == "true"
                        elif line.startswith("timeout="):
                            try:
                                self.network_timeout = int(line[8:].strip())
                            except:
                                pass
            except:
                pass

    def saveConfig(self):
        cfg_path = "/etc/enigma2/ciefpvibes.cfg"
        try:
            with open(cfg_path, "w") as f:
                f.write(f"bg={self.current_bg}\n")
                f.write(f"ib={self.current_ib}\n")
                f.write(f"poster={self.current_poster}\n")
                f.write(f"repeat={self.repeat_mode}\n")
                f.write(f"shuffle={self.shuffle_enabled}\n")
                f.write(f"timeout={self.network_timeout}\n")
        except:
            pass

    def saveLastPlaylist(self, filepath=None, display_name=""):
        if filepath:
            try:
                with open(self.last_playlist_path, "w") as f:
                    f.write(f"{filepath}\n{display_name}")
            except:
                pass

    def loadLastOrDefault(self):
        if os.path.isfile(self.last_playlist_path):
            try:
                with open(self.last_playlist_path, "r") as f:
                    lines = f.read().strip().split("\n")
                    if len(lines) >= 2:
                        path, name = lines[0], lines[1]
                        if os.path.isfile(path):
                            self.fileBrowserClosed((path, name))
                            return
            except:
                pass
        self.loadPlaylist()

    def showPoster(self, path):
        if not path:
            return

        # Proveri da li fajl postoji
        if not os.path.isfile(path):
            print(f"[CiefpVibes] Poster not found: {path}")
            # Pokaži default poster
            default_poster = os.path.join(PLUGIN_DIR, "posters", self.current_poster)
            if os.path.isfile(default_poster):
                path = default_poster
            else:
                return

        try:
            # Load the pixmap
            from enigma import loadPic
            self["poster"].instance.setPixmap(loadPic(path))
            self["poster"].show()
            print(f"[CiefpVibes] Showing poster: {path}")
        except Exception as e:
            print(f"[CiefpVibes] Error showing poster: {e}")
            # Fallback na loadPic
            try:
                self["poster"].instance.setPixmapFromFile(path)
                self["poster"].show()
            except:
                pass

    def openFileBrowser(self, initial_dir="/tmp"):
        self.session.openWithCallback(self.fileBrowserClosed, CiefpFileBrowser, initial_dir)

    def fileBrowserClosed(self, result):
        if result:
            filepath, display_name = result
            print(f"[CiefpVibes] Učitavanje fajla: '{filepath}'")
            if not os.path.isfile(filepath):
                self.session.open(MessageBox, f"File does not exist:\n{filepath}", MessageBox.TYPE_ERROR)
                return
            self.loadPlaylistFromFile(filepath, display_name)

    def loadPlaylistFromFile(self, filepath, display_name="Lista"):
        self.playlist = []
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".tv" or ext == ".radio": 
            self.parseTVBouquet(filepath)
        elif ext in (".m3u", ".m3u8"):
            self.parseM3U(filepath)
        else:
            self.session.open(MessageBox, "Only .tv .radio and .m3u files!", MessageBox.TYPE_ERROR)
            return

        if not self.playlist:
            self["nowplaying"].setText("Nema pesama")
            self.session.open(MessageBox, "The file is empty or in an invalid format!", MessageBox.TYPE_WARNING)
            return

        self["playlist"].list = self.playlist
        self["playlist"].index = 0
        self.currentIndex = 0
        self["nowplaying"].setText(f"📁 {display_name} • {len(self.playlist)} pesama")
        self.saveLastPlaylist(filepath, display_name)
        self.playCurrent()

    def parseTVBouquet(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f.readlines()]
        except Exception as e:
            print("[CiefpVibes] Greška pri čitanju .tv ili .radio:", e)
            return

        try:
            from urllib.parse import unquote
        except ImportError:
            from urllib import unquote

        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("#SERVICE 4097:"):
                try:
                    parts = line[9:].split(":")
                    if len(parts) >= 11:
                        # Ekstrakcija URL-a i imena
                        if len(parts) > 11:
                            url_encoded = ":".join(parts[10:-1])
                            name = parts[-1].strip()
                        else:
                            url_encoded = parts[10]
                            name = None

                        url = unquote(url_encoded).strip()

                        # Učitaj ime iz #DESCRIPTION ako postoji
                        if not name and i + 1 < len(lines) and lines[i + 1].startswith("#DESCRIPTION"):
                            name = lines[i + 1][13:].strip()
                            i += 1

                        # Čišćenje imena
                        name = name or "Unknown"
                        name = name.replace(" external stream link", "").strip()
                        name = name.replace(".mp3", "").replace(".flac", "").strip()

                        # 🔍 Detekcija audio streama – proširena
                        audio_indicators = [
                            ".mp3", ".flac", ".aac", ".ogg", ".wav", ".m3u8", ".m3u", ".pls", ".nsv",
                            "/stream", "/;", "/live", "/audio", "/radio", "/listen",
                            "rtmp://", "rtsp://", "http://", "https://"
                        ]
                        is_audio = any(ind in url.lower() for ind in audio_indicators)

                        # ❌ Izuzeci – izbegavamo video streamove
                        video_indicators = [".ts", ".mp4", ".mkv", ".avi", ".mov", "/video", "video=", "?video"]
                        is_video = any(ind in url.lower() for ind in video_indicators)

                        if is_audio and not is_video:
                            self.playlist.append((name, url))
                            print(f"[CiefpVibes] Radio dodat: {name} → {url}")

                except Exception as ex:
                    print("[CiefpVibes] Greška u obradi linije:", ex)
                i += 1
            else:
                i += 1

    def parseM3U(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f.readlines()]
        except Exception as e:
            print("[CiefpVibes] Greška pri čitanju .m3u:", e)
            return

        current_title = ""
        for line in lines:
            if line.startswith("#EXTINF:"):
                if "," in line:
                    current_title = line.split(",", 1)[1].strip()
            elif line.startswith("http") and (".mp3" in line.lower() or ".flac" in line.lower()):
                title = (current_title or os.path.basename(line)).replace(".mp3", "").replace(".flac", "").strip()
                self.playlist.append((title, line))
                current_title = ""
            elif line and not line.startswith("#") and (".mp3" in line.lower() or ".flac" in line.lower()):
                title = os.path.basename(line).replace(".mp3", "").replace(".flac", "").strip()
                self.playlist.append((title, line))

    def loadPlaylist(self):
        welcome_url = "https://raw.githubusercontent.com/ciefp/CiefpVibesFiles/main/TV/userbouquet.ciefpvibes_welcome.tv"
        tmp_path = "/tmp/ciefpvibes_welcome.tv"
        self["nowplaying"].setText("🌐 Loading welcome playlist...")

        # Preuzmi fajl sa GitHub-a
        try:
            urllib.request.urlretrieve(welcome_url, tmp_path)
            print(f"[CiefpVibes] Downloaded welcome playlist to {tmp_path}")
        except Exception as e:
            print(f"[CiefpVibes] Download error: {e}")
            self["nowplaying"].setText("⚠ Download failed")
            self.session.open(MessageBox, f"Can't download welcome playlist:\n{e}", MessageBox.TYPE_ERROR)
            return

        # Pročitaj preuzeti fajl
        try:
            with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"[CiefpVibes] File read error: {e}")
            self["nowplaying"].setText("⚠ File error")
            return

        entries = []  # OVO JE BITNO DODATI!
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("#SERVICE"):
                try:
                    parts = line[9:].split(":")
                    if len(parts) >= 11:
                        # Dekodiraj URL
                        url_encoded = ":".join(parts[10:-1]) if len(parts) > 11 else parts[10]
                        url = unquote(url_encoded)
                        name = "Unknown"

                        # Pročitaj ime iz #DESCRIPTION ako postoji
                        if i + 1 < len(lines) and lines[i + 1].strip().startswith("#DESCRIPTION"):
                            name = lines[i + 1].strip()[13:].replace(".mp3", "").replace(".flac", "").strip()
                            i += 1
                        else:
                            # Probaj iz poslednjeg dela URL-a
                            name = parts[-1].replace(".mp3", "").replace(".flac", "").strip()

                        # Dodaj samo muzičke fajlove
                        if ".mp3" in url.lower() or ".flac" in url.lower():
                            clean_name = name if name != "Unknown" else os.path.basename(url)
                            entries.append((clean_name, url))
                            print(f"[CiefpVibes] Added: {clean_name}")
                except Exception as ex:
                    print(f"[CiefpVibes] Error parsing line: {ex}")
            i += 1

        # Postavi playlistu
        self.playlist = entries
        self["playlist"].list = self.playlist

        if self.playlist:
            self.currentIndex = 0
            self["playlist"].index = 0
            self["nowplaying"].setText(f"🎵 Welcome Playlist • {len(self.playlist)} songs")
            print(f"[CiefpVibes] Loaded {len(self.playlist)} songs from welcome playlist")
            # Automatski pokreni prvu pesmu
            self.playCurrent()
        else:
            self["nowplaying"].setText("⚠ Empty playlist")
            self.session.open(MessageBox, "Welcome playlist is empty or contains no music files!",
                              MessageBox.TYPE_WARNING)

    def fetchAlbumCover(self, artist, title):
        """Preuzmi album cover za artist/title kombinaciju"""

        # DEBUG
        print(f"[CiefpVibes] Searching cover for: Artist='{artist}', Title='{title}'")

        # Ako nemamo ni artist ni title, ne možemo da tražimo
        if not artist and not title:
            print(f"[CiefpVibes] No artist/title for cover search")
            return None

        # Čišćenje stringova
        def clean_string(text):
            if not text:
                return ""
            # Ukloni nedozvoljene karaktere i trim
            import re
            text = re.sub(r'[<>:"/\\|?*]', '', text)
            text = text.strip()
            return text

        clean_artist = clean_string(artist)
        clean_title = clean_string(title)

        # Generiši keš ime
        if clean_artist and clean_title:
            cache_name = f"{clean_artist}_{clean_title}.jpg".replace(' ', '_')
        elif clean_title:
            cache_name = f"{clean_title}.jpg".replace(' ', '_')
        else:
            return None

        cache_path = os.path.join(CACHE_DIR, cache_name)

        # Proveri keš
        if os.path.isfile(cache_path):
            print(f"[CiefpVibes] Cover found in cache: {cache_path}")
            return cache_path

        # Formiraj query za pretragu
        import urllib.parse

        # Prioritetne strategije pretrage:
        queries = []

        # 1. Artist + Title (najbolje)
        if clean_artist and clean_title:
            queries.append(f"{clean_artist} {clean_title}")

        # 2. Samo Title (ako nema artist)
        if clean_title and not clean_artist:
            queries.append(clean_title)

        # 3. Samo Artist (ako nema title)
        if clean_artist and not clean_title:
            queries.append(clean_artist)

        # Prolazak kroz sve strategije
        for query in queries:
            if not query:
                continue

            encoded_query = urllib.parse.quote(query)
            url = f"https://itunes.apple.com/search?term={encoded_query}&media=music&limit=1&country=US"

            print(f"[CiefpVibes] iTunes query: {query}")

            try:
                import socket
                socket.setdefaulttimeout(5)

                with urllib.request.urlopen(url) as response:
                    data = json.loads(response.read().decode("utf-8"))

                if data.get("resultCount", 0) > 0:
                    result = data["results"][0]

                    # Uzmi najbolju dostupnu sliku
                    img_url = result.get("artworkUrl100", "")
                    if not img_url:
                        continue

                    # Poboljšaj kvalitetu
                    img_url = img_url.replace("100x100", "600x600")

                    # Pokušaj da preuzmeš
                    urllib.request.urlretrieve(img_url, cache_path)

                    if os.path.getsize(cache_path) > 1024:
                        print(f"[CiefpVibes] Cover downloaded: {cache_path}")
                        return cache_path
                    else:
                        os.unlink(cache_path)

            except Exception as e:
                print(f"[CiefpVibes] iTunes error for '{query}': {e}")
                continue

        print(f"[CiefpVibes] No cover found for {artist} - {title}")
        return None

    def getCacheSize(self):
        """Vraća ukupnu veličinu cache foldera u MB"""
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(CACHE_DIR):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.isfile(fp):
                        total_size += os.path.getsize(fp)
            return round(total_size / (1024 * 1024), 1)  # U MB
        except:
            return 0

    def clearCache(self):
        """Obriši sav sadržaj cache foldera"""
        try:
            # Obriši sve fajlove u cache folderu
            for filename in os.listdir(CACHE_DIR):
                file_path = os.path.join(CACHE_DIR, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"[CiefpVibes] Error deleting {file_path}: {e}")
            
            # Vrati potvrdu i veličinu (0 MB)
            return True, self.getCacheSize()
        except Exception as e:
            print(f"[CiefpVibes] Error clearing cache: {e}")
            return False, self.getCacheSize()

    def playCurrent(self):
        if not self.playlist or not (0 <= self.currentIndex < len(self.playlist)):
            return

        name, url = self.playlist[self.currentIndex]

        # Resetuj status streama
        self.stream_active = True
        self.stream_check_counter = 0
        self.last_audio_data_time = 0
        self.vibe_value = 0
        self.vibe_direction = 1
        
        # Sakrij offline status i pokaži progress barove
        self["offline_status"].hide()
        self["progress_real"].show()
        self["progress_vibe"].show()

        # Resetuj metapodatke
        self.current_song_info = {"artist": "", "title": ""}

        # Postavi osnovni tekst
        self["nowplaying"].setText(f"▶ {name}")

        # Prikaži default poster na početku
        self.showDefaultPoster()

        # ✅ Koristi 4097 za sve IP streamove (podržava ICY metadata)
        ref = eServiceReference(4097, 0, url)
        ref.setName(name)
        self.session.nav.playService(ref)

        # ✅ Eksplicitno pokreni playback — ključno za RTMP/HLS/ICY
        service = self.session.nav.getCurrentService()
        if service:
            pauseable = service.pause()
            if pauseable:
                pauseable.unpause()

        # Pokreni timere
        self.resetProgress()
        self.progress_timer.start(200, False)
        self.vibe_timer.start(200, False)
        # Pokreni timer za proveru streama (svakih 2 sekunde)
        self.stream_check_timer.start(2000, False)

    def playSelected(self):
        idx = self["playlist"].index
        if 0 <= idx < len(self.playlist):
            self.currentIndex = idx
            self.playCurrent()

    def nextTrack(self):
        if not self.playlist:
            return
        if self.repeat_mode == "one":
            pass  # replay same
        else:
            self.currentIndex = (self.currentIndex + 1) % len(self.playlist)
            self["playlist"].index = self.currentIndex
        self.playCurrent()

    def up(self):    self["playlist"].selectPrevious()
    def down(self):  self["playlist"].selectNext()

    def resetProgress(self):
        self.current_duration = 0
        self.current_position = 0
        self["progress_real"].setValue(0)
        self["progress_vibe"].setValue(0)
        self["remaining"].setText("+0:00")
        self.progress_timer.start(1000, False)

    def onAudioData(self):
        """Poziva se kada primi audio podatke - označava da je stream aktivan"""
        import time
        self.last_audio_data_time = time.time()
        self.stream_active = True
        self.stream_check_counter = 0

    def checkStreamStatus(self):
        """Proveri da li je stream aktivan"""
        import time
        
        if not self.stream_active:
            return
            
        self.stream_check_counter += 1
        
        # Ako nismo primili audio podatke u poslednjih 10 sekundi
        if self.last_audio_data_time > 0 and time.time() - self.last_audio_data_time > 10:
            self.stream_active = False
            self.showOfflineStatus()
        
        # Ako nema progress update u duže vreme
        elif self.stream_check_counter > 10:  # 20 sekundi bez promene
            service = self.session.nav.getCurrentService()
            if service:
                seek = service.seek()
                if seek:
                    pos = seek.getPlayPosition()
                    if pos[0]:
                        # Proveri da li se pozicija menja
                        if self.current_position == pos[1] and self.current_position > 0:
                            self.stream_active = False
                            self.showOfflineStatus()
                        else:
                            self.current_position = pos[1]
                            self.stream_check_counter = 0
        
        # Ponovo pokreni timer
        self.stream_check_timer.start(2000, False)

    def showOfflineStatus(self):
        """Prikaži offline status"""
        self["offline_status"].setText("OFFLINE")
        self["offline_status"].show()
        self["progress_vibe"].hide()
        self.vibe_timer.stop()
        
        # Ažuriraj tekst za sadašnju pesmu sa OFFLINE oznakom
        if self.playlist and 0 <= self.currentIndex < len(self.playlist):
            name = self.playlist[self.currentIndex][0]
            self["nowplaying"].setText(f"⭕ {name} [OFFLINE]")

    def updateProgress(self):
        service = self.session.nav.getCurrentService()
        if not service:
            # Ako nema servisa, možda je stream mrtav
            if self.stream_active:
                self.stream_active = False
                self.showOfflineStatus()
            return

        # ✅ Čitanje metapodataka
        info = service.info()
        if info:
            raw_title = info.getInfoString(iServiceInformation.sTagTitle).strip()

            # Ako postoji ICY metadata
            if raw_title:
                if raw_title.startswith("ICY: "):
                    raw_title = raw_title[5:].strip()

                # Parsiraj artist i title KORISTEĆI POBOLJŠANU METODU
                artist, title = self.parseArtistTitle(raw_title)

                # DEBUG: Ispis za proveru
                print(f"[CiefpVibes DEBUG] Raw: '{raw_title}'")
                print(f"[CiefpVibes DEBUG] Parsed: Artist='{artist}', Title='{title}'")

                # Sačuvaj samo ako smo uspeli da parsirajemo
                if title:  # Bar title treba da postoji
                    self.current_song_info["artist"] = artist
                    self.current_song_info["title"] = title

                    # Ažuriraj poster odmah kada dobijemo nove metapodatke
                    self.updatePosterFromMetadata()

                    # AŽURIRAJ TEKST! Ovo je ključno
                    self.updateNowPlayingText()

            # Proveri i standardne tagove
            artist_tag = info.getInfoString(iServiceInformation.sTagArtist)
            if artist_tag and artist_tag.strip():
                self.current_song_info["artist"] = artist_tag.strip()
                self.updateNowPlayingText()  # Ažuriraj tekst

            title_tag = info.getInfoString(iServiceInformation.sTagTitle)
            if title_tag and title_tag.strip() and not self.current_song_info["title"]:
                # Parsiraj samo ako već nema title
                if " • " in title_tag:
                    parts = title_tag.split(" • ", 1)
                    if len(parts) > 1:
                        artist, title = self.parseArtistTitle(parts[1])
                        self.current_song_info["artist"] = artist
                        self.current_song_info["title"] = title
                        self.updateNowPlayingText()  # Ažuriraj tekst

        # Standardna logika za progress bar
        seek = service.seek()
        if not seek:
            return
        pos = seek.getPlayPosition()
        dur = seek.getLength()
        if pos[0] and dur[0]:
            self.current_position = pos[1]
            self.current_duration = dur[1]
            if self.current_duration > 0:
                percentage = int((self.current_position * 100) / self.current_duration)
                self["progress_real"].setValue(percentage)
                elapsed_sec = self.current_position // 1000
                emin, esec = divmod(elapsed_sec, 60)
                self["elapsed"].setText(f"{emin}:{esec:02d}")
                remaining_sec = (self.current_duration - self.current_position) // 1000
                mins, secs = divmod(remaining_sec, 60)
                self["remaining"].setText(f"-{mins}:{secs:02d}")

    def updateNowPlayingText(self):
        """Ažuriraj samo tekstualni prikaz (bez postera)"""
        if not self.playlist or self.currentIndex < 0:
            return

        name = self.playlist[self.currentIndex][0] if self.playlist else "Radio"
        display = f"▶ {name}"
        artist = self.current_song_info["artist"]
        title = self.current_song_info["title"]

        if artist and title:
            display += f" • {artist} - {title}"
        elif title:
            display += f" • {title}"

        self["nowplaying"].setText(display)
        print(f"[CiefpVibes] Display updated: {display}")

    def updatePosterFromMetadata(self):
        """Ažuriraj poster na osnovu trenutnih metapodataka"""
        artist = self.current_song_info["artist"]
        title = self.current_song_info["title"]

        # DEBUG
        print(f"[CiefpVibes] Updating poster for: Artist='{artist}', Title='{title}'")

        # Ako nemamo dovoljno informacija, koristi default poster
        if not artist and not title:
            self.showDefaultPoster()
            return

        # Pokušaj da preuzmeš poster
        cover = self.fetchAlbumCover(artist, title)

        if cover and os.path.isfile(cover):
            self.showPoster(cover)
            print(f"[CiefpVibes] Showing downloaded poster: {cover}")
        else:
            # Fallback na default poster
            self.showDefaultPoster()
            print(f"[CiefpVibes] Using default poster (no cover found)")

    def onMetaUpdate(self):
        service = self.session.nav.getCurrentService()
        if not service:
            return
        info = service.info()
        if not info:
            return

        raw_title = info.getInfoString(iServiceInformation.sTagTitle).strip()
        if not raw_title:
            return

        # Ukloni "ICY: " prefix ako postoji
        if raw_title.startswith("ICY: "):
            raw_title = raw_title[5:].strip()

        # Razdvoji "Artist - Title"
        artist, title = self.parseArtistTitle(raw_title)
        self.current_song_info["artist"] = artist
        self.current_song_info["title"] = title
        self.updateNowPlaying()

        print(f"[CiefpVibes DEBUG] Metapodaci: '{artist}' - '{title}'")

    def parseArtistTitle(self, text):
        """
        Parsira string u formatu: 'naziv_streama • artist - title' ili 'artist - title'
        Vraća (artist, title)
        """
        if not text:
            return "", ""

        print(f"[CiefpVibes PARSING] Input text: '{text}'")

        # 1. Prvo pokušaj da parsiraš format: "Awesome-80-s • Rick Astley - Together Forever"
        if " • " in text:
            parts = text.split(" • ", 1)
            stream_part = parts[0].strip()
            artist_title_part = parts[1].strip()

            print(f"[CiefpVibes PARSING] Stream part: '{stream_part}'")
            print(f"[CiefpVibes PARSING] Artist/Title part: '{artist_title_part}'")

            # Sada parsiraj artist - title
            separators = [" - ", " – ", " | ", " :: ", " › ", " / ", " ~ "]
            for sep in separators:
                if sep in artist_title_part:
                    artist_title = artist_title_part.split(sep, 1)
                    artist = artist_title[0].strip()
                    title = artist_title[1].strip()
                    print(f"[CiefpVibes PARSING] Found with separator '{sep}': Artist='{artist}', Title='{title}'")
                    return artist, title

            # Ako nema separatora, možda je samo title
            print(f"[CiefpVibes PARSING] No separator found, using as title: '{artist_title_part}'")
            return "", artist_title_part

        # 2. Ako nema " • ", probaj direktno artist - title
        separators = [" - ", " – ", " | ", " :: ", " › ", " / ", " ~ "]
        for sep in separators:
            if sep in text:
                parts = text.split(sep, 1)
                artist = parts[0].strip()
                title = parts[1].strip()
                print(f"[CiefpVibes PARSING] Direct parsing with '{sep}': Artist='{artist}', Title='{title}'")
                return artist, title

        # 3. Ako ništa ne radi, vrati ceo tekst kao title
        print(f"[CiefpVibes PARSING] No parsing possible, using as title: '{text}'")
        return "", text.strip()

    def updatePosterFromMetadata(self):
        """Ažuriraj poster na osnovu trenutnih metapodataka"""
        artist = self.current_song_info["artist"]
        title = self.current_song_info["title"]

        # DEBUG
        print(f"[CiefpVibes POSTER] Updating poster for: Artist='{artist}', Title='{title}'")

        # Ako nemamo dovoljno informacija, koristi default poster
        if not artist and not title:
            print(f"[CiefpVibes POSTER] No metadata, using default")
            self.showDefaultPoster()
            return

        # Pokušaj da preuzmeš poster
        cover = self.fetchAlbumCover(artist, title)

        if cover and os.path.isfile(cover):
            print(f"[CiefpVibes POSTER] Showing downloaded poster: {cover}")
            self.showPoster(cover)
        else:
            # Fallback na default poster
            print(f"[CiefpVibes POSTER] No cover found, using default")
            self.showDefaultPoster()

    def updateNowPlaying(self):
        """Zastarela metoda - koristite updateNowPlayingText umesto nje"""
        # Ovo sada samo poziva novu metodu za kompatibilnost
        self.updateNowPlayingText()

    def updateVibeProgress(self):
        """Ažuriraj pulsirajući progress bar samo ako je stream aktivan"""
        if not self.stream_active:
            return
            
        # Animacija pulsiranja (napred-nazad)
        self.vibe_value += self.vibe_direction * 5
        
        if self.vibe_value >= 70:
            self.vibe_value = 70
            self.vibe_direction = -1  # Sada ide nazad
        elif self.vibe_value <= 0:
            self.vibe_value = 0
            self.vibe_direction = 1   # Sada ide napred
            
        self["progress_vibe"].setValue(self.vibe_value)

    def exit(self):
        self.session.nav.stopService()
        self.progress_timer.stop()
        self.vibe_timer.stop()
        self.stream_check_timer.stop()
        self.saveConfig()
        self.close()

    def showAbout(self):
        self.session.open(MessageBox, f"{PLUGIN_NAME} v{PLUGIN_VERSION}\n\n✅ Funkcije:\n• .tv & .m3u\n• Repeat / Shuffle\n• 5 background-a\n• 5 infobar-a\n• Auto-reload poslednje", MessageBox.TYPE_INFO)

    # === SETTINGS ===
    def openSettings(self):
        # Добиј тренутну величину кеша
        cache_size = self.getCacheSize()
        
        from Screens.ChoiceBox import ChoiceBox
        self.session.openWithCallback(
            self.settingsCategorySelected,
            ChoiceBox,
            title=f"🔧 Settings • Cache: ({cache_size}MB)",
            list=[
                ("▶ Playback", "playback"),
                ("🌐 Network", "network"),
                ("🎨 Background", "background"),
                ("🖼️ Poster", "poster"),
                ("📊 Infobar", "infobar"),
                ("🧹 Clear Cache", "clear_cache"),  # НОВА ОПЦИЈА
                ("💾 Save & Load", "save")
            ]
        )

    def settingsCategorySelected(self, choice):
        if not choice:
            return
        key = choice[1]
        if key == "playback":
            self.session.openWithCallback(
                self.playbackSettingChosen,
                ChoiceBox,
                title="▶ Playback",
                list=[
                    ("🔁 Repeat: Off", "repeat_off"),
                    ("🔁 Repeat: One", "repeat_one"),
                    ("🔁 Repeat: All", "repeat_all"),
                    ("🔀 Shuffle: Off", "shuffle_off"),
                    ("🔀 Shuffle: On", "shuffle_on"),
                ]
            )
        elif key == "network":
            self.session.openWithCallback(
                self.networkSettingChosen,
                ChoiceBox,
                title="🌐 Network",
                list=[
                    ("⏱ Timeout: 10s", "timeout_10"),
                    ("⏱ Timeout: 20s", "timeout_20"),
                    ("⏱ Timeout: 30s", "timeout_30"),
                    ("⏱ Timeout: 60s", "timeout_60"),
                    ("📥 Učitaj iz URL-a", "load_url"),
                ]
            )
        elif key == "background":
            self.session.openWithCallback(
                self.backgroundChosen,
                ChoiceBox,
                title="🎨 Background",
                list=[
                    ("Background 1", "bg1"),
                    ("Background 2", "bg2"),
                    ("Background 3", "bg3"),
                    ("Background 4", "bg4"),
                    ("Background 5", "bg5"),
                    ("Background 6", "bg6"),
                    ("Background 7", "bg7"),
                    ("Background 8", "bg8"),
                    ("Background 9", "bg9"),
                    ("Background 10", "bg10"),
                ]
            )
        elif key == "poster":
            self.session.openWithCallback(
                self.posterChosen,
                ChoiceBox,
                title="🖼️ Poster",
                list=[
                    ("Poster 1", "poster1"),
                    ("Poster 2", "poster2"),
                    ("Poster 3", "poster3"),
                    ("Poster 4", "poster4"),
                    ("Poster 5", "poster5"),
                    ("Poster 6", "poster6"),
                    ("Poster 7", "poster7"),
                    ("Poster 8", "poster8"),
                    ("Poster 9", "poster9"),
                    ("Poster 10", "poster10"),
                ]
            )
        elif key == "infobar":
            self.session.openWithCallback(
                self.infobarChosen,
                ChoiceBox,
                title="📊 Infobar",
                list=[
                    ("Infobar 1", "ib1"),
                    ("Infobar 2", "ib2"),
                    ("Infobar 3", "ib3"),
                    ("Infobar 4", "ib4"),
                    ("Infobar 5", "ib5"),
                    ("Infobar 6", "ib6"),
                    ("Infobar 7", "ib7"),
                    ("Infobar 8", "ib8"),
                    ("Infobar 9", "ib9"),
                    ("Infobar 10", "ib10"),
                ]
            )
        elif key == "clear_cache":  # НОВА ОПЦИЈА ЗА ЧИШЋЕЊЕ КЕША
            cache_size = self.getCacheSize()
            self.session.openWithCallback(
                self.clearCacheConfirmed,
                MessageBox,
                f"🧹 Clear all cached files?\n\nCurrent cache size: {cache_size}MB\n\nThis will delete:\n• All downloaded album covers\n• All downloaded playlist files\n• All temporary files",
                MessageBox.TYPE_YESNO
            )
        elif key == "save":
            self.saveConfig()
            self.saveLastPlaylist()
            self.session.open(MessageBox, "💾 Configuration and list saved.", MessageBox.TYPE_INFO)

    def clearCacheConfirmed(self, result):
        """Потврда за брисање кеша"""
        if result:
            success, new_size = self.clearCache()
            if success:
                self.session.open(MessageBox, f"✅ Cache cleared successfully!\n\nNew cache size: {new_size}MB", MessageBox.TYPE_INFO)
            else:
                self.session.open(MessageBox, "❌ Error clearing cache!", MessageBox.TYPE_ERROR)

    def playbackSettingChosen(self, choice):
        if not choice: return
        key = choice[1]
        if key == "repeat_off": self.repeat_mode = "off"
        elif key == "repeat_one": self.repeat_mode = "one"
        elif key == "repeat_all": self.repeat_mode = "all"
        elif key == "shuffle_off": self.shuffle_enabled = False
        elif key == "shuffle_on": self.shuffle_enabled = True

    def networkSettingChosen(self, choice):
        if not choice: return
        key = choice[1]
        if key.startswith("timeout_"):
            self.network_timeout = int(key.split("_")[1])
        elif key == "load_url":
            self.session.openWithCallback(self.urlEntered, VirtualKeyBoard, title="Enter .m3u URL", text="http://")

    def urlEntered(self, url):
        if url and (".m3u" in url.lower() or ".m3u8" in url.lower()):
            tmp_path = os.path.join(CACHE_DIR, "url_playlist.m3u")
            try:
                urllib.request.urlretrieve(url, tmp_path)
                self.fileBrowserClosed((tmp_path, "URL Playlist"))
            except Exception as e:
                self.session.open(MessageBox, f"❌ Error:\n{e}", MessageBox.TYPE_ERROR)

    def backgroundChosen(self, choice):
        if not choice: return
        bg_map = {
            "bg1": "background1.png",
            "bg2": "background2.png",
            "bg3": "background3.png",
            "bg4": "background4.png",
            "bg5": "background5.png",
            "bg6": "background6.png",
            "bg7": "background7.png",
            "bg8": "background8.png",
            "bg9": "background9.png",
            "bg10": "background10.png",
        }
        bg = bg_map.get(choice[1], "background1.png")
        bg_path = os.path.join(PLUGIN_DIR, "backgrounds", bg)
        if os.path.isfile(bg_path):
            self.current_bg = bg
            self.saveConfig()
            # Osveži poster pri promeni pozadine
            self.showDefaultPoster()
            # Restart ekran da primeni skin
            self.session.open(CiefpVibesMain)
            self.close()

        else:
            self.session.open(MessageBox, f"❗ Missing:\n{bg_path}", MessageBox.TYPE_ERROR)

    def posterChosen(self, choice):
        if not choice: return
        poster_map = {
            "poster1": "poster1.png",
            "poster2": "poster2.png",
            "poster3": "poster3.png",
            "poster4": "poster4.png",
            "poster5": "poster5.png",
            "poster6": "poster6.png",
            "poster7": "poster7.png",
            "poster8": "poster8.png",
            "poster9": "poster9.png",
            "poster10": "poster10.png",
        }
        poster = poster_map.get(choice[1], "poster1.png")
        poster_path = os.path.join(PLUGIN_DIR, "posters", poster)
        if os.path.isfile(poster_path):
            self.current_poster = poster
            self.saveConfig()
            # Prikaži novi poster odmah
            self.showDefaultPoster()
            self.session.open(CiefpVibesMain)
            self.close()
        else:
            self.session.open(MessageBox, f"❗ Missing:\n{poster_path}", MessageBox.TYPE_ERROR)

    def infobarChosen(self, choice):
        if not choice: return
        ib_map = {
            "ib1": "infobar1.png",
            "ib2": "infobar2.png",
            "ib3": "infobar3.png",
            "ib4": "infobar4.png",
            "ib5": "infobar5.png",
            "ib6": "infobar6.png",
            "ib7": "infobar7.png",
            "ib8": "infobar8.png",
            "ib9": "infobar9.png",
            "ib10": "infobar10.png"
        }
        ib = ib_map.get(choice[1], "infobar-fhd1.png")
        ib_path = os.path.join(PLUGIN_DIR, "infobars", ib)
        if os.path.isfile(ib_path):
            self.current_ib = ib
            self.saveConfig()
            self.session.open(CiefpVibesMain)
            self.close()
        else:
            self.session.open(MessageBox, f"❗ Nedostaje:\n{ib_path}", MessageBox.TYPE_ERROR)


    # ✅ Nova metoda: Online Files (plavo dugme)
    def openGitHubLists(self):
        self.session.openWithCallback(
            self.githubCategorySelected,
            ChoiceBox,
            title="📥 Online Files",
            list=[
                ("🎶 M3U Playlists", "M3U"),
                ("📺 .tv Bouquets", "TV"),
                ("📻 Radio Lists", "RADIO"),  # DODAJ OVO
            ]
        )

    def githubCategorySelected(self, choice):
        if not choice:
            return
        cat = choice[1]
        if cat == "M3U":
            url = GITHUB_M3U_URL
        elif cat == "TV":
            url = GITHUB_TV_URL
        elif cat == "RADIO":  # DODAJ OVO
            url = GITHUB_RADIO_URL
        else:
            return

        items = self.fetchGitHubLists(url, cat)
        if not items:
            self.session.open(MessageBox, f"There is no list in {cat} category.", MessageBox.TYPE_INFO)
            return
        self.session.openWithCallback(
            self.githubListSelected,
            ChoiceBox,
            title=f"📥 Choose {cat} list",
            list=[(display, (dl_url, filename)) for display, dl_url, filename in items]
        )
    def fetchGitHubLists(self, url, category):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", f"{PLUGIN_NAME}/{PLUGIN_VERSION}")
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read())
                items = []
                for item in data:
                    if item.get("type") == "file":
                        name = item.get("name", "")
                        dl_url = item.get("download_url")
                        # DODAJ .radio u proveru ekstenzije
                        if dl_url and name.lower().endswith((".m3u", ".m3u8", ".tv", ".radio")):
                            clean = name
                            if clean.startswith("userbouquet."):
                                clean = clean[12:]
                            clean = clean.replace("IPTV_OPD_", "").replace("IPTV ", "")
                            clean = clean.replace("_mp3", "").replace("_flac", "")
                            for date in [" 08.11.2025", "_08112025", "_03112025", "_29112025", "_0909_1"]:
                                clean = clean.replace(date, "")
                            clean = clean.replace("_", " ").replace(".", " ").strip()
                            # DODAJ .radio u zamene
                            clean = clean.replace(".tv", "").replace(".radio", "").replace(".m3u", "").replace(".m3u8", "")
                            words = []
                            for w in clean.split():
                                if w.upper() == "VA":
                                    words.append("VA")
                                else:
                                    words.append(w.capitalize())
                            display = " ".join(words)
                            items.append((display, dl_url, name))
                return sorted(items, key=lambda x: x[0].lower())
        except Exception as e:
            print("[CiefpVibes] GitHub %s error: %s" % (category, e))
            return []

    def githubListSelected(self, choice):
        if not choice:
            return
        dl_url, filename = choice[1]
        display_name = choice[0]
        # Сачувај у cache директоријум
        tmp_path = os.path.join(CACHE_DIR, filename)
        try:
            urllib.request.urlretrieve(dl_url, tmp_path)
            self.fileBrowserClosed((tmp_path, display_name))
        except Exception as e:
            self.session.open(MessageBox, f"❌ Error while downloading:{e}", MessageBox.TYPE_ERROR)

    # ✅ Zadrži postojeću showAbout metodu (možeš je koristiti ako želiš preko drugog menija)
        def showAbout(self):
            self.session.open(MessageBox,
                              f"""{PLUGIN_NAME} v{PLUGIN_VERSION}
    ✅ Funkcije:
    • .tv, .radio & .m3u
    • Repeat / Shuffle
    • 5 background-a
    • 5 infobar-a
    • 5 postera
    • Auto-reload poslednje
    • 🔵 Online Files""",
                              MessageBox.TYPE_INFO
                              )

# === FILE BROWSER (nepromenjen) ===
class CiefpFileBrowser(Screen):
    skin = '''
    <screen position="center,140" size="1600,800" title="..:: Choose a playlist ::..">
        <widget name="filelist" position="10,10" size="1180,620" scrollbarMode="showOnDemand"/>
        <widget name="background" position="1200,0" size="400,800" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/CiefpVibes/fileexplorer.png" zPosition="-1" alphatest="on" />
        <widget name="curr_dir" position="10,650" size="1180,40" font="Regular;30" halign="center"/>
        <widget name="key_red"   position="150,700" size="400,50" font="Regular;32" halign="center" backgroundColor="#300000" foregroundColor="#ff5555"/>
        <widget name="key_green" position="650,700" size="400,50" font="Regular;32" halign="center" backgroundColor="#003000" foregroundColor="#55ff55"/>
    </screen>
    '''
    def __init__(self, session, initial_dir="/tmp"):
        Screen.__init__(self, session)
        self["background"] = Pixmap()
        self["filelist"] = FileList(initial_dir, showDirectories=True, showFiles=True)
        self["curr_dir"] = Label(initial_dir)
        self["key_red"] = Label("Cancel")
        self["key_green"] = Label("Izaberi")
        self["actions"] = ActionMap(["WizardActions", "DirectionActions", "ColorActions"], {
            "ok": self.ok,
            "cancel": self.cancel,
            "red": self.cancel,
            "green": self.ok,
            "up": self.up,
            "down": self.down,
            "pageUp": self["filelist"].pageUp,
            "pageDown": self["filelist"].pageDown,
        }, -1)
        self.onLayoutFinish.append(self.updateDir)
    def updateDir(self):
        self["curr_dir"].setText(self["filelist"].getCurrentDirectory() or "/")
    def up(self):
        self["filelist"].up()
        self.updateDir()
    def down(self):
        self["filelist"].down()
        self.updateDir()
    def ok(self):
        if self["filelist"].canDescent():
            self["filelist"].descent()
            self.updateDir()
        else:
            selection = self["filelist"].getSelection()
            if selection and selection[0]:
                path = selection[0]
                fn = os.path.basename(path)
                # DODAJ .radio u proveru
                if fn.lower().endswith((".tv", ".radio", ".m3u", ".m3u8")):
                    self.close((path, fn))
                else:
                    self.session.open(MessageBox, "Only .tv, .radio and .m3u files!", MessageBox.TYPE_WARNING)
            else:
                self.session.open(MessageBox, "No file selected!", MessageBox.TYPE_WARNING)

    def cancel(self):
        self.close(None)

# === PLUGIN ENTRY ===
def main(session, **kwargs):
    session.open(CiefpVibesMain)
def Plugins(**kwargs):
    return [PluginDescriptor(
        name=f"{PLUGIN_NAME} v{PLUGIN_VERSION}",
        description=PLUGIN_DESC,
        where=PluginDescriptor.WHERE_PLUGINMENU,
        icon="plugin.png",
        fnc=main
    )]