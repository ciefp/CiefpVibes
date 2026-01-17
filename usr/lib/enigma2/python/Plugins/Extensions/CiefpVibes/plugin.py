# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import json 
import shutil
import subprocess
import logging
import urllib.request
import uuid
import time
import urllib.parse
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
from enigma import eServiceReference, eTimer, iPlayableService, gFont, iServiceInformation, RT_HALIGN_LEFT, RT_VALIGN_CENTER, eConsoleAppContainer
from Plugins.Plugin import PluginDescriptor
from urllib.parse import unquote

PLUGIN_NAME = "CiefpVibes"
PLUGIN_DESC = "Jukebox play music locally and online"
PLUGIN_VERSION = "1.6"  # POVECANA VERZIJA
PLUGIN_DIR = os.path.dirname(__file__) or "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVibes"
CACHE_DIR = "/tmp/ciefpvibes_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# === UPDATE SYSTEM VARIABLES ===
UPDATE_VERSION_URL = "https://raw.githubusercontent.com/ciefp/CiefpVibes/main/version.txt"
UPDATE_COMMAND = "wget -q --no-check-certificate https://raw.githubusercontent.com/ciefp/CiefpVibes/main/installer.sh -O - | /bin/sh"
BACKUP_FILE = "/tmp/ciefpvibes_backup.txt"

# Setup logging for updates
LOG_FILE = "/tmp/ciefpvibes_update.log"
def setup_update_logging():
    logger = logging.getLogger("CiefpVibesUpdate")
    logger.propagate = False
    if logger.handlers:
        logger.handlers.clear()
    
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    try:
        handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    except Exception as e:
        pass
    
    return logger

update_logger = setup_update_logging()
# === END UPDATE SYSTEM ===

# MREŽNI MOUNT POINT
NETWORK_MOUNT = "/media/network"
os.makedirs(NETWORK_MOUNT, exist_ok=True)

# GitHub URL-ovi
GITHUB_M3U_URL = "https://api.github.com/repos/ciefp/CiefpVibesFiles/contents/M3U"
GITHUB_TV_URL = "https://api.github.com/repos/ciefp/CiefpVibesFiles/contents/TV"
GITHUB_RADIO_URL = "https://api.github.com/repos/ciefp/CiefpVibesFiles/contents/RADIO"

class CiefpVibesMain(Screen):
    def buildSkin(self):
        bg = getattr(self, "current_bg", "background1.png")
        ib = getattr(self, "current_ib", "infobar5.png")

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
            <widget name="nowplaying" position="60,900" size="1600,55" font="Regular;40" foregroundColor="#FFFFFF" transparent="1" zPosition="4"/>
            <widget name="time" position="1600,900" size="200,40" font="Regular;32" halign="center" valign="center" foregroundColor="#ffffff" transparent="1" zPosition="3"/>
            <widget name="elapsed" position="60,965" size="200,40" font="Regular;32" foregroundColor="#ffffff" transparent="1" zPosition="3"/>
            <widget name="progress_real" position="240,985" size="1150,20" pixmap="skin_default/progress_bg.png" zPosition="2"/>
            <widget name="progress_vibe" position="240,985" size="1150,20" pixmap="%s/progress_green.png" zPosition="3"/>
            <widget name="offline_status" position="240,985" size="1150,20" font="Regular;18" foregroundColor="#ff3333" halign="center" valign="center" transparent="0" backgroundColor="#000000" zPosition="4"/>
            <widget name="remaining" position="1420,965" size="350,40" font="Regular;32" foregroundColor="#ffcc00" halign="right" transparent="1" zPosition="3"/>
            <widget name="key_red"    position="60,1030"  size="260,50" font="Regular;32" foregroundColor="#ff5555" transparent="1" zPosition="3"/>
            <widget name="key_green"  position="350,1030" size="260,50" font="Regular;32" foregroundColor="#55ff55" transparent="1" zPosition="3"/>
            <widget name="key_yellow" position="640,1030" size="300,50" font="Regular;32" foregroundColor="#ffdd55" transparent="1" zPosition="3"/>
            <widget name="key_blue"   position="980,1030" size="260,50" font="Regular;32" foregroundColor="#5599ff" transparent="1" zPosition="3"/>
            <!-- DODAJTE OVAJ WIDGET ZA UPDATE STATUS -->
            <widget name="update_status" position="1250,1030" size="400,40" font="Regular;28" foregroundColor="#ffffff" halign="right" transparent="1" zPosition="3"/>
        </screen>''' % (PLUGIN_DIR, bg, PLUGIN_DIR, ib, PLUGIN_DIR)

    def __init__(self, session):
        self["poster"] = Pixmap()
        self.current_bg = "background1.png"
        self.current_ib = "infobar1.png"
        self.current_poster = "poster1.png"
        self.last_playlist_path = "/etc/enigma2/ciefpvibes_last.txt"
        self.loadConfig()

        self.metadata_history = []  # Čuva poslednjih 5 naslova
        self.metadata_change_counter = 0

        # Update sistem varijable
        self.version_check_in_progress = False
        self.version_buffer = b''
        self.container = eConsoleAppContainer()
        self.container.appClosed.append(self.command_finished)
        self.container.dataAvail.append(self.version_data_avail)

        # Dodaj ove varijable za kontrolu postera
        self.current_poster_path = ""  # Putanja trenutno prikazanog postera
        self.poster_locked = False  # Da li je poster zaključan (ne menjati)
        self.poster_change_count = 0  # Broj promena postera za ovu pesmu
        self.max_poster_changes = 3  # Maksimalno dozvoljeno promena
        self.last_poster_change = 0  # Vreme poslednje promene postera
        self.folderCoverCache = {}

        # DODAJTE OVE NOVE VARIJABLE:
        # U __init__ metodi:
        self.poster_search_timer = eTimer()  # Timer za odloženo traženje
        self.poster_setup_timer = eTimer()  # Novi timer za postavljanje callback-a
        self.poster_setup_timer.callback.append(self.setupPosterTimer)
        self.poster_setup_timer.start(100, True)  # 100ms kasnije

        self.is_current_stream_online = False  # Već postoji, samo potvrda
        self.last_displayed_title = ""  # Za praćenje promene na infobaru
        self.poster_search_delay = 10  # sekundi za online radio
        self.last_title_change_time = 0  # Kada je poslednji put promenjen naslov
        self.auto_title_update_timer = eTimer()

        # Timer za force refresh
        self.force_refresh_timer = eTimer()
        self.force_refresh_timer.callback.append(self.forceRefreshMetadata)

        # Timer za zaključavanje postera
        self.lock_timer = eTimer()
        self.lock_timer.callback.append(self.lockCurrentPoster)

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
        self["key_red"] = Label("🔴 EXIT")
        self["key_green"] = Label("🟢 FOLDER")
        self["key_yellow"] = Label("🟡 SETTINGS")
        self["key_blue"] = Label("🔵 Online Files")

        # Dodajte ovo u __init__ metodi, negde posle ostalih widget definicija:
        self["update_status"] = Label("")
        self["progress_real"] = ProgressBar()
        self["progress_vibe"] = ProgressBar()
        self["progress_real"].setValue(0)
        self["progress_vibe"].setValue(0)
        # Automatski proveri update 4 sekunde posle starta
        self.update_timer = eTimer()
        self.update_timer.callback.append(self.check_for_updates)
        self.update_timer.start(4000, True)  # jednokratno

        
        self["offline_status"] = Label("")
        self["offline_status"].hide()
        self["time"] = Label("")
        self["remaining"] = Label("+0:00")
        self["elapsed"] = Label("0:00")
        self["selected_folder"] = Label("")
        self.current_source_name = ""

        self.stream_active = False
        self.stream_check_counter = 0
        self.last_audio_data_time = 0
        self.vibe_direction = 1
        self.vibe_value = 0
        
        self["actions"] = ActionMap(["ColorActions", "WizardActions", "DirectionActions", "MenuActions"], {
            "ok":       self.playSelected,
            "back":     self.exit,
            "up":       self.up,
            "down":     self.down,
            "red":      self.exit,
            "green":    self.openFileBrowser,
            "yellow":   self.openSettings,
            "blue":     self.openGitHubLists,
            "menu":     self.openNetworkMenu,
        }, -1)
        
        self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
            iPlayableService.evEOF: self.nextTrack,
            iPlayableService.evUpdatedInfo: self.updateProgress,
            iPlayableService.evStart: self.resetProgress,
            iPlayableService.evUser+10: self.onAudioData
        })
        
        self.time_update_timer = eTimer()
        self.time_update_timer.callback.append(self.updateTime)
        self.time_update_timer.start(1000)
        self.onClose.append(self.time_update_timer.stop)
        
        self.progress_timer = eTimer()
        self.progress_timer.callback.append(self.updateProgress)
        self.vibe_timer = eTimer()
        self.vibe_timer.callback.append(self.updateVibeProgress)
        self.stream_check_timer = eTimer()
        self.stream_check_timer.callback.append(self.checkStreamStatus)

        self.current_duration = 0
        self.current_position = 0
        self.onFirstExecBegin.append(self.loadLastOrDefault)
        self.current_song_info = {"artist": "", "title": ""}
        self.onLayoutFinish.append(self.showDefaultPoster)

    def updateTime(self):
        try:
            import time
            t = time.strftime("%H:%M:%S")
            self["time"].setText(t)
        except:
            pass
            
    def setupPosterTimer(self):
        """Postavi callback za poster timer (zamenjeno od ranije)"""
        print(f"[CiefpVibes] Poster timer setup")
        # Postavi callback za timer ako nije već postavljen
        if not self.poster_search_timer.callback:
            self.poster_search_timer.callback.append(self.delayedPosterSearch)

    # === UPDATE SYSTEM METHODS ===
    def startVersionCheck(self):
        if self.version_check_in_progress:
            return
        print("[CiefpVibes-UPDATE] Checking for updates...")
        self.version_check_in_progress = True
        self.version_buffer = b''
        self.container.execute(f"wget -q --no-check-certificate -O - {UPDATE_VERSION_URL}")

    def showUpdateStatus(self, text="", color="#ffcc00"):
        """Prikazuje tekst u update_status labelu na dnu ekrana"""
        if "update_status" in self:
            if text:
                self["update_status"].setText(text)
                self["update_status"].show()
                print(f"[CiefpVibes-UPDATE] Status shown: {text}")
            else:
                self["update_status"].setText("")
                self["update_status"].hide()

    def check_for_updates(self):
        """Proveri da li postoji nova verzija plugina"""
        try:
            if self.version_check_in_progress:
                return

            self.version_check_in_progress = True
            self.showUpdateStatus("Checking update...", "#ffcc00")

            update_logger.info("Starting version check")
            self.version_buffer = b''
            self.container.execute(f"wget -q --no-check-certificate -O - {UPDATE_VERSION_URL}")

        except Exception as e:
            self.version_check_in_progress = False
            update_logger.error(f"Error starting update check: {str(e)}")
            self.showUpdateStatus("Update error", "#ff5555")

    def version_data_avail(self, data):
        if not self.version_check_in_progress:
            return

        self.version_buffer += data

        # Ako dobijemo kraj (version.txt ima samo jednu liniju)
        if b'\n' in data or len(self.version_buffer) > 20:
            try:
                remote_version = self.version_buffer.decode('utf-8').strip()
                print(f"[CiefpVibes-UPDATE] Remote: '{remote_version}' | Local: '{PLUGIN_VERSION}'")

                if remote_version and remote_version > PLUGIN_VERSION:  # Nova verzija?
                    self.showUpdateStatus(f"Update: v{remote_version}", "#ffaa00")
                    # Pokreni MessageBox za update (pretpostavljam da već imaš ovo)
                    self.session.openWithCallback(
                        self.doUpdateCallback,
                        MessageBox,
                        f"New version: v{remote_version}\nCurrent: v{PLUGIN_VERSION}\n\nUpdate now?",
                        MessageBox.TYPE_YESNO
                    )
                else:
                    # Sve OK – prikaži status
                    self.showUpdateStatus("Up to date ✓", "#55ff55")

            except Exception as e:
                print(f"[CiefpVibes-UPDATE] Error: {e}")
                self.showUpdateStatus("Check failed", "#ff5555")

            finally:
                self.version_check_in_progress = False
                self.version_buffer = b''

    def command_finished(self, retval):
        """Obradi završetak wget komande za proveru verzije ili update"""
        if not hasattr(self, 'version_check_in_progress') or not self.version_check_in_progress:
            # Ako je ovo kraj update komande (ne provere)
            if retval == 0:
                self.update_completed(0)
            else:
                self.update_completed(retval)
            return

        self.version_check_in_progress = False

        if retval == 0:
            try:
                remote_version = self.version_buffer.decode('utf-8').strip()
                update_logger.info(f"Remote version: {remote_version}, Local: {PLUGIN_VERSION}")

                if remote_version and remote_version != PLUGIN_VERSION:
                    self.showUpdateStatus(f"Update v{remote_version}!", "#ffaa00")
                    self.session.openWithCallback(
                        self.start_update,
                        MessageBox,
                        f"📥 New version available!\n\n"
                        f"Current: v{PLUGIN_VERSION}\n"
                        f"Available: v{remote_version}\n\n"
                        f"Install now?",
                        MessageBox.TYPE_YESNO
                    )
                else:
                    self.showUpdateStatus("Up to date ✓", "#55ff55")
                    update_logger.info("Plugin is up to date")

            except Exception as e:
                update_logger.error(f"Error parsing version: {str(e)}")
                self.showUpdateStatus("Version error", "#ff5555")
        else:
            update_logger.error(f"Version check failed (retval: {retval})")
            self.showUpdateStatus("No internet", "#ff5555")

    def start_update(self, answer):
        """Pokreni update ako je korisnik potvrdio"""
        if answer:
            try:
                update_logger.info("User accepted update")
                
                # Backup config fajla
                config_file = "/etc/enigma2/ciefpvibes.cfg"
                if os.path.exists(config_file):
                    shutil.copy2(config_file, BACKUP_FILE)
                    update_logger.info(f"Backed up config to {BACKUP_FILE}")
                
                # Prikaži status
                if hasattr(self, "update_status"):
                    self["update_status"].setText("Updating...")
                
                # Pokreni update komandu
                self.container.execute(UPDATE_COMMAND)
                
            except Exception as e:
                update_logger.error(f"Error starting update: {str(e)}")
                if hasattr(self, "update_status"):
                    self["update_status"].setText("Update error")
                self.session.open(
                    MessageBox,
                    f"❌ Error starting update:\n{str(e)[:100]}",
                    MessageBox.TYPE_ERROR
                )

    def update_completed(self, retval):
        """Obradi završetak update-a"""
        try:
            # Restore backup ako postoji
            if os.path.exists(BACKUP_FILE):
                config_file = "/etc/enigma2/ciefpvibes.cfg"
                shutil.move(BACKUP_FILE, config_file)
                update_logger.info(f"Restored config from backup")
            
            if retval == 0:
                update_logger.info("Update completed successfully")
                
                # Prikaži poruku i ponudi restart
                self.session.openWithCallback(
                    self.restart_plugin,
                    MessageBox,
                    "✅ Update successful!\n\nRestart plugin now?",
                    MessageBox.TYPE_YESNO
                )
            else:
                update_logger.error(f"Update failed with retval: {retval}")
                if hasattr(self, "update_status"):
                    self["update_status"].setText("Update failed")
                
                self.session.open(
                    MessageBox,
                    "❌ Update failed!\n\nPlease try again later.",
                    MessageBox.TYPE_ERROR
                )
                
        except Exception as e:
            update_logger.error(f"Error in update_completed: {str(e)}")

    def restart_plugin(self, answer):
        """Restartuje plugin ako je korisnik potvrdio"""
        if answer:
            # Zatvori trenutni ekran i ponovo otvori plugin
            self.close()
            self.session.openWithCallback(
                lambda x: None,
                CiefpVibesMain
            )
        else:
            if hasattr(self, "update_status"):
                self["update_status"].setText("Restart needed")

    def showUpdateStatus(self, text="", color="#ffcc00"):
        """Prikazuje tekst u donjem desnom uglu (update status)"""
        if "update_status" not in self:
            return

        if text:
            self["update_status"].setText(text)
            self["update_status"].show()
            print(f"[CiefpVibes-UPDATE] Status shown: {text}")
        else:
            self["update_status"].setText("")
            self["update_status"].hide()
                
    # === MREŽNE METODE ===
    
    def openNetworkMenu(self):
        """Otvori meni za mrežne opcije"""
        from Screens.ChoiceBox import ChoiceBox
        
        self.session.openWithCallback(
            self.networkMenuSelected,
            ChoiceBox,
            title="🌐 Network Options",
            list=[
                ("💻 Connect to Laptop (SMB)", "connect_laptop"),
                ("📡 Browse Network", "browse_network"),
                ("➕ Add Network Share", "add_share"),
                ("🔌 Disconnect All", "disconnect"),
                ("🔍 Auto-Scan", "autoscan"),
            ]
        )
    
    def networkMenuSelected(self, choice):
        if not choice:
            return
        
        if choice[1] == "connect_laptop":
            self.connectToLaptop()
        elif choice[1] == "browse_network":
            self.browseNetworkShares()
        elif choice[1] == "add_share":
            self.addNetworkShare()
        elif choice[1] == "disconnect":
            self.disconnectNetwork()
        elif choice[1] == "autoscan":
            self.autoScanNetwork()
    
    def connectToLaptop(self):
        """Poveži se sa laptop-om"""
        from Screens.VirtualKeyBoard import VirtualKeyBoard
        
        self.session.openWithCallback(
            self.laptopIPEntered,
            VirtualKeyBoard,
            title="Enter Laptop IP Address",
            text="192.168.1."
        )
    
    def laptopIPEntered(self, ip_address):
        if not ip_address:
            return
        
        self.session.openWithCallback(
            lambda share_name: self.mountLaptopShare(ip_address, share_name),
            VirtualKeyBoard,
            title="Enter Share Name (or leave empty for default)",
            text=""
        )
    
    def mountLaptopShare(self, ip_address, share_name=""):
        """Mount-uj SMB share sa laptop-a"""
        mount_point = os.path.join(NETWORK_MOUNT, "laptop")
        os.makedirs(mount_point, exist_ok=True)
        
        if share_name:
            smb_path = f"//{ip_address}/{share_name}"
        else:
            smb_path = f"//{ip_address}"
        
        self["nowplaying"].setText(f"🔗 Connecting to {ip_address}...")
        
        if self.mountSMBShare(smb_path, mount_point):
            self.session.open(
                MessageBox,
                f"✅ Successfully connected!\n\nPath: {mount_point}",
                MessageBox.TYPE_INFO
            )
            self.session.openWithCallback(
                self.fileBrowserClosed,
                CiefpFileBrowser,
                initial_dir=mount_point
            )
        else:
            self.session.open(
                MessageBox,
                f"❌ Cannot connect!\n\nTry:\n1. Check IP\n2. Enable sharing\n3. Check share name",
                MessageBox.TYPE_ERROR
            )
    
    def mountSMBShare(self, smb_path, mount_point):
        """Mount SMB/CIFS share"""
        try:
            if os.path.ismount(mount_point):
                subprocess.run(["umount", "-l", mount_point], capture_output=True)
            
            cmd = [
                "mount", "-t", "cifs",
                smb_path,
                mount_point,
                "-o", "ro,guest,iocharset=utf8"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"[CiefpVibes] SMB mount successful")
                return True
            else:
                cmd2 = [
                    "mount", "-t", "cifs",
                    smb_path,
                    mount_point,
                    "-o", "ro,user=guest,password="
                ]
                result2 = subprocess.run(cmd2, capture_output=True, text=True)
                return result2.returncode == 0
                
        except Exception as e:
            print(f"[CiefpVibes] Mount error: {e}")
            return False
    
    def browseNetworkShares(self):
        """Pregled postojećih mrežnih deljenja"""
        mounted_shares = []
        
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    if "cifs" in line or "nfs" in line or NETWORK_MOUNT in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            mounted_shares.append(parts[1])
        
            if mounted_shares:
                choices = []
                for share in mounted_shares:
                    choices.append((f"📂 {share}", share))
                
                choices.append(("➕ Add New Share", "add_new"))
                
                self.session.openWithCallback(
                    self.shareSelected,
                    ChoiceBox,
                    title="🌐 Network Shares",
                    list=choices
                )
            else:
                self.session.open(
                    MessageBox,
                    "No network shares found!",
                    MessageBox.TYPE_INFO
                )
                self.connectToLaptop()
                
        except Exception as e:
            print(f"[CiefpVibes] Error reading mounts: {e}")
    
    def shareSelected(self, choice):
        if not choice:
            return
        
        if choice[1] == "add_new":
            self.connectToLaptop()
        else:
            self.session.openWithCallback(
                self.fileBrowserClosed,
                CiefpFileBrowser,
                initial_dir=choice[1]
            )
    
    def addNetworkShare(self):
        """Dodaj ručno mrežni share"""
        from Screens.ChoiceBox import ChoiceBox
        
        self.session.openWithCallback(
            self.shareTypeSelected,
            ChoiceBox,
            title="➕ Add Network Share",
            list=[
                ("💻 Windows SMB/CIFS", "smb"),
                ("🐧 Linux NFS", "nfs"),
            ]
        )
    
    def shareTypeSelected(self, choice):
        if not choice:
            return
        
        share_type = choice[1]
        
        self.session.openWithCallback(
            lambda details: self.configureShare(share_type, details),
            VirtualKeyBoard,
            title=f"Enter {share_type.upper()} path",
            text="192.168.1.100/Music"
        )
    
    def configureShare(self, share_type, path):
        if not path:
            return
        
        mount_name = path.replace("/", "_").replace(".", "_")
        mount_point = os.path.join(NETWORK_MOUNT, mount_name)
        os.makedirs(mount_point, exist_ok=True)
        
        if share_type == "smb":
            success = self.mountSMBShare(f"//{path}", mount_point)
        elif share_type == "nfs":
            success = self.mountNFSShare(f"{path}", mount_point)
        else:
            self.session.open(
                MessageBox,
                f"Share type {share_type} not yet implemented",
                MessageBox.TYPE_INFO
            )
            return
        
        if success:
            self.session.open(
                MessageBox,
                f"✅ {share_type.upper()} share mounted!",
                MessageBox.TYPE_INFO
            )
            self.session.openWithCallback(
                self.fileBrowserClosed,
                CiefpFileBrowser,
                initial_dir=mount_point
            )
    
    def mountNFSShare(self, nfs_path, mount_point):
        """Mount NFS share"""
        try:
            cmd = ["mount", "-t", "nfs", nfs_path, mount_point, "-o", "ro"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            print(f"[CiefpVibes] NFS mount error: {e}")
            return False
    
    def disconnectNetwork(self):
        """Unmount sve mrežne share-ove"""
        try:
            for item in os.listdir(NETWORK_MOUNT):
                mount_point = os.path.join(NETWORK_MOUNT, item)
                if os.path.ismount(mount_point):
                    subprocess.run(["umount", "-l", mount_point], capture_output=True)
            
            self.session.open(
                MessageBox,
                "✅ All network shares disconnected",
                MessageBox.TYPE_INFO
            )
        except Exception as e:
            print(f"[CiefpVibes] Unmount error: {e}")
    
    def autoScanNetwork(self):
        """Automatsko skeniranje mreže za SMB share-ove"""
        import socket
        import threading
        
        self["nowplaying"].setText("🔍 Scanning network...")
        
        def scan_job():
            found_devices = []
            
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                my_ip = s.getsockname()[0]
                s.close()
                
                base_ip = ".".join(my_ip.split(".")[:3]) + "."
            except:
                base_ip = "192.168.1."
            
            for i in range(1, 255):
                ip = base_ip + str(i)
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.3)
                    result = sock.connect_ex((ip, 445))
                    
                    if result == 0:
                        try:
                            hostname = socket.gethostbyaddr(ip)[0]
                        except:
                            hostname = ip
                        
                        found_devices.append((hostname, ip))
                    
                    sock.close()
                except:
                    pass
            
            if found_devices:
                choices = []
                for hostname, ip in found_devices:
                    choices.append((f"💻 {hostname} ({ip})", ip))
                
                self.session.openWithCallback(
                    self.scannedDeviceSelected,
                    ChoiceBox,
                    title="🌐 Found Devices",
                    list=choices
                )
            else:
                self.session.open(
                    MessageBox,
                    "No SMB devices found!",
                    MessageBox.TYPE_INFO
                )
            
            self["nowplaying"].setText("Ready")
        
        thread = threading.Thread(target=scan_job)
        thread.daemon = True
        thread.start()
    
    def scannedDeviceSelected(self, choice):
        if choice:
            self.laptopIPEntered(choice[1])

    # === FILE BROWSER METODE ===
    
    def openFileBrowser(self):
        """Otvori file browser"""
        from Screens.ChoiceBox import ChoiceBox
        
        self.session.openWithCallback(
            self.browserTypeSelected,
            ChoiceBox,
            title="📁 Select Source",
            list=[
                ("💾 Local Storage", "local"),
                ("💻 Network (Laptop)", "network"),
                ("📡 Online Streams", "online"),
            ]
        )
    
    def browserTypeSelected(self, choice):
        if not choice:
            return
        
        if choice[1] == "local":
            self.session.openWithCallback(
                self.localLocationSelected,
                ChoiceBox,
                title="💾 Local Storage",
                list=[
                    ("📁 Media/HDD", "/media/hdd"),
                    ("📁 USB", "/media/usb"),
                    ("📁 Root", "/"),
                ]
            )
        elif choice[1] == "network":
            self.openNetworkMenu()
        elif choice[1] == "online":
            self.openGitHubLists()
    
    def localLocationSelected(self, choice):
        if choice:
            self.session.openWithCallback(
                self.fileBrowserClosed,
                CiefpFileBrowser,
                initial_dir=choice[1]
            )

    # === POSTER METODE ===
    def showDefaultPoster(self):
        # Ovu funkciju zovemo samo kada želimo namerno prikazati default poster
        default_poster = os.path.join(PLUGIN_DIR, "posters", self.current_poster)

        # Proveri da li već prikazujemo default poster
        if self.current_poster_path == default_poster:
            return

        self.showPoster(default_poster)

        # Resetuj zaključavanje kada prikazujemo default poster
        self.poster_locked = False
        self.poster_change_count = 0

        # Postavi callback za timer ako nije već postavljen
        if not self.poster_search_timer.callback:
            self.poster_search_timer.callback.append(self.delayedPosterSearch)

    def showPoster(self, path):
        print(f"[CiefpVibes-DEBUG] showPoster called with path: {path}")
        if not path or not os.path.exists(path):
            print(f"[CiefpVibes-DEBUG] Invalid or missing file")
            return

        file_size = os.path.getsize(path)
        if file_size < 1024:
            print(f"[CiefpVibes-DEBUG] File too small ({file_size} bytes)")
            return

        # Otključaj ako je trenutni poster default
        default_posters = [f"poster{i}.png" for i in range(1, 11)]
        if self.current_poster_path and os.path.basename(self.current_poster_path) in default_posters:
            self.poster_locked = False
            self.poster_change_count = 0
            print(f"[CiefpVibes-DEBUG] Unlocked default poster")

        if self.poster_locked:
            print(f"[CiefpVibes-DEBUG] Poster locked, skipping change")
            return

        if self.current_poster_path == path:
            print(f"[CiefpVibes-DEBUG] Same poster already shown")
            return

        # Slabiji throttle: dozvoli promenu ako je prošlo bar 0.5 sekundi (ili ako je default)
        current_time = time.time()
        if not self.current_poster_path or os.path.basename(self.current_poster_path) in default_posters:
            # Ako je trenutni default ili nema poster – dozvoli ODMAH
            pass
        elif current_time - self.last_poster_change < 0.5:
            print(f"[CiefpVibes-DEBUG] Throttled: too soon ({current_time - self.last_poster_change:.2f}s)")
            return

        self.last_poster_change = current_time
        self.poster_change_count += 1

        if self.poster_change_count > self.max_poster_changes:
            print(f"[CiefpVibes-DEBUG] Max changes reached, locking poster")
            self.poster_locked = True
            return

        try:
            self["poster"].instance.setPixmapFromFile(path)
            self["poster"].show()
            self.current_poster_path = path
            print(
                f"[CiefpVibes-DEBUG] SUCCESS: Poster displayed #{self.poster_change_count} → {os.path.basename(path)}")

            # Zaključaj samo ako je dobar (ne-default) poster
            if os.path.basename(path) not in default_posters:
                self.poster_locked = True
                print(f"[CiefpVibes-DEBUG] Good poster → locked for 3 seconds")

        except Exception as e:
            print(f"[CiefpVibes-DEBUG] ERROR displaying poster: {e}")
            import traceback
            traceback.print_exc()

    def findLocalCover(self, media_path):
        """
        Traži cover u folderu gde se nalazi lokalni audio fajl
        Prioritet:
        1. cover.jpg / folder.jpg / front.jpg / album.jpg / Cover.jpg / Folder.jpg
        2. prvi .jpg/.png iz foldera
        """
        try:
            print(f"[CiefpVibes] Looking for local cover for: {media_path}")

            if not media_path or not os.path.isfile(media_path):
                print(f"[CiefpVibes] Invalid media path")
                return None

            folder = os.path.dirname(media_path)
            if not os.path.isdir(folder):
                print(f"[CiefpVibes] Folder doesn't exist: {folder}")
                return None

            # Keš po folderu (da ne skeniramo stalno)
            if folder in self.folderCoverCache:
                cached = self.folderCoverCache[folder]
                print(f"[CiefpVibes] Cache hit for folder: {folder} -> {cached}")
                return cached

            # Lista prioriteta za cover fajlove
            priority_names = [
                "cover.jpg", "folder.jpg", "front.jpg", "album.jpg", "artwork.jpg",
                "Cover.jpg", "Folder.jpg", "Front.jpg", "Album.jpg", "Artwork.jpg",
                "cover.png", "folder.png", "front.png", "album.png", "artwork.png",
                "Cover.png", "Folder.png", "Front.png", "Album.png", "Artwork.png"
            ]

            # Proveri prioritetne fajlove
            for name in priority_names:
                cover_path = os.path.join(folder, name)
                print(f"[CiefpVibes] Checking: {cover_path}")
                if os.path.isfile(cover_path):
                    file_size = os.path.getsize(cover_path)
                    if file_size > 1024:  # Minimalna veličina 1KB
                        print(f"[CiefpVibes] Found priority cover: {cover_path} ({file_size} bytes)")
                        self.folderCoverCache[folder] = cover_path
                        return cover_path
                    else:
                        print(f"[CiefpVibes] File too small: {file_size} bytes")

            # Fallback: traži bilo koji JPG/PNG u folderu (osim default postera)
            print(f"[CiefpVibes] Searching all images in folder...")
            default_posters = [f"poster{i}.png" for i in range(1, 11)]

            for filename in os.listdir(folder):
                if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    # Preskoči default postere iz plugina
                    if filename in default_posters:
                        continue

                    cover_path = os.path.join(folder, filename)
                    if os.path.isfile(cover_path):
                        file_size = os.path.getsize(cover_path)
                        if 1024 < file_size < 10 * 1024 * 1024:  # 1KB do 10MB
                            print(f"[CiefpVibes] Found fallback image: {filename} ({file_size} bytes)")
                            self.folderCoverCache[folder] = cover_path
                            return cover_path

            # Proveri parent folder (za albume gde su pesme u podfolderima)
            parent_folder = os.path.dirname(folder)
            if parent_folder and os.path.isdir(parent_folder):
                for name in priority_names:
                    cover_path = os.path.join(parent_folder, name)
                    if os.path.isfile(cover_path) and os.path.getsize(cover_path) > 1024:
                        print(f"[CiefpVibes] Found cover in parent folder: {cover_path}")
                        self.folderCoverCache[folder] = cover_path
                        return cover_path

            print(f"[CiefpVibes] No local cover found")
            self.folderCoverCache[folder] = None
            return None

        except Exception as e:
            print(f"[CiefpVibes] ERROR in findLocalCover: {e}")
            import traceback
            traceback.print_exc()
            return None

    def forceUnlockAndShowPoster(self, path):
        """Forsira otključavanje i prikaz postera (za test)"""
        print(f"[CiefpVibes-FORCE] Forcing poster display: {path}")

        if not os.path.exists(path):
            print(f"[CiefpVibes-FORCE] ERROR: File does not exist")
            return False

        # Otključaj poster
        self.poster_locked = False
        self.poster_change_count = 0

        # Pokušaj direktno
        try:
            self["poster"].instance.setPixmapFromFile(path)
            self["poster"].show()
            self.current_poster_path = path

            print(f"[CiefpVibes-FORCE] SUCCESS: Poster forced to display")

            # Prikaži poruku
            self["nowplaying"].setText(f"📸 Showing: {os.path.basename(path)}")

            return True
        except Exception as e:
            print(f"[CiefpVibes-FORCE] ERROR: {str(e)}")
            return False

    # === CONFIG METODE ===
    
    def loadConfig(self):
        cfg_path = "/etc/enigma2/ciefpvibes.cfg"
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, "r") as f:
                    for line in f:
                        if line.startswith("bg="):
                            self.current_bg = line[3:].strip() or "background1.png"
                        elif line.startswith("poster="):
                            self.current_poster = line[7:].strip() or "poster5.png"
                        elif line.startswith("ib="):
                            self.current_ib = line[3:].strip() or "infobar5.png"
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

    # === PLAYLIST LOADING ===
    
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

    def fileBrowserClosed(self, result):
        if result:
            filepath, display_name = result
            print(f"[CiefpVibes] Loading: '{filepath}'")
            if not os.path.isfile(filepath):
                self.session.open(MessageBox, f"File does not exist:\n{filepath}", MessageBox.TYPE_ERROR)
                return
            self.loadPlaylistFromFile(filepath, display_name)

    def loadPlaylistFromFile(self, filepath, display_name="Lista"):
        """Učitaj playlistu iz fajla"""
        self.playlist = []
        ext = os.path.splitext(filepath)[1].lower()
        
        # Proveri da li je direktan audio fajl
        audio_extensions = (".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg")
        
        if ext in audio_extensions:
            # DIREKTAN AUDIO FAJL
            success = self.parseDirectAudioFile(filepath)
            if success:
                display_name = f"🎵 {os.path.basename(filepath)}"
            else:
                self.session.open(MessageBox, f"Cannot play audio file:\n{filepath}", MessageBox.TYPE_ERROR)
                return
                
        elif ext == ".tv" or ext == ".radio": 
            # TV/RADIO BOUQUET
            self.parseTVBouquet(filepath)
            
        elif ext in (".m3u", ".m3u8"):
            # M3U PLAYLIST
            self.parseM3U(filepath)
            
        else:
            self.session.open(MessageBox, 
                             f"Unsupported file type: {ext}\n\n"
                             f"Supported formats:\n"
                             f"• Audio: .mp3 .flac .m4a .aac\n"
                             f"• Playlists: .m3u .m3u8 .tv .radio", 
                             MessageBox.TYPE_ERROR)
            return

        # Proveri da li ima pesama
        if not self.playlist:
            self["nowplaying"].setText("Nema pesama")
            self.session.open(MessageBox, 
                             "The file contains no playable music!",
                             MessageBox.TYPE_WARNING)
            return

        # Postavi listu
        self["playlist"].list = self.playlist
        self["playlist"].index = 0
        self.currentIndex = 0
        
        # Prikaži informacije
        if len(self.playlist) == 1:
            self["nowplaying"].setText(f"🎵 {self.playlist[0][0]}")
        else:
            self["nowplaying"].setText(f"📁 {display_name} • {len(self.playlist)} pesama")
        
        self.saveLastPlaylist(filepath, display_name)
        self.playCurrent()

    def parseDirectAudioFile(self, path):
        """Parsira direktan audio fajl (mp3, flac, m4a)"""
        print(f"[CiefpVibes] Parsing direct audio file: {path}")
        
        if not os.path.isfile(path):
            print(f"[CiefpVibes] File does not exist: {path}")
            return False
        
        # Uzmi ime pesme iz fajla
        filename = os.path.basename(path)
        song_name = os.path.splitext(filename)[0]
        # Ako ime fajla sadrži " - ", automatski izvuci artist + title
        if " - " in song_name:
            parts = song_name.split(" - ", 1)
            artist = parts[0].strip()
            title = parts[1].strip()
            song_name = f"{artist} - {title}"

            # Sačuvaj info za dalju obradu
            self.current_song_info = {
                "artist": artist,
                "title": title
            }
        else:
            # ako nije u formatu "artist - title", neka ostane kao prije
            self.current_song_info = {
                "artist": "",
                "title": song_name
            }

        # Čišćenje imena
        song_name = song_name.replace("_", " ").replace("  ", " ")
        song_name = song_name.replace("-", " - ")
        song_name = song_name.replace(".", " ")
        
        # Dodaj u playlistu
        self.playlist = [(song_name, path)]
        print(f"[CiefpVibes] Added direct audio: {song_name}")
        return True

    def parseTVBouquet(self, path):
        """Parsira .tv ili .radio bouquet fajl"""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f.readlines()]
        except Exception as e:
            print(f"[CiefpVibes] Error reading bouquet: {e}")
            return

        try:
            from urllib.parse import unquote
        except ImportError:
            from urllib import unquote

        i = 0
        entries = 0
        
        while i < len(lines):
            line = lines[i]
            if line.startswith("#SERVICE 4097:"):
                try:
                    parts = line[9:].split(":")
                    if len(parts) >= 11:
                        if len(parts) > 11:
                            url_encoded = ":".join(parts[10:-1])
                            name = parts[-1].strip()
                        else:
                            url_encoded = parts[10]
                            name = None

                        url = unquote(url_encoded).strip()

                        if not name and i + 1 < len(lines) and lines[i + 1].startswith("#DESCRIPTION"):
                            name = lines[i + 1][13:].strip()
                            i += 1

                        name = name or "Unknown"
                        name = name.replace(" external stream link", "").strip()
                        for ext in [".mp3", ".flac", ".m4a", ".aac"]:
                            name = name.replace(ext, "")
                        name = name.strip()

                        audio_indicators = [
                            ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav", 
                            ".m3u8", ".m3u", ".pls", ".nsv",
                            "/stream", "/;", "/live", "/audio", "/radio", "/listen",
                            "rtmp://", "rtsp://", "http://", "https://"
                        ]
                        is_audio = any(ind in url.lower() for ind in audio_indicators)

                        video_indicators = [".ts", ".mp4", ".mkv", ".avi", ".mov", "/video", "video=", "?video"]
                        is_video = any(ind in url.lower() for ind in video_indicators)

                        if is_audio and not is_video:
                            self.playlist.append((name, url))
                            entries += 1

                except Exception as ex:
                    print(f"[CiefpVibes] Error parsing bouquet line: {ex}")
                i += 1
            else:
                i += 1
        
        print(f"[CiefpVibes] Bouquet parsed: {entries} entries")

    def parseM3U(self, path):
        """Parsira M3U playlist fajl"""
        print(f"[CiefpVibes] Parsing M3U playlist: {path}")
        
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f.readlines()]
        except Exception as e:
            print(f"[CiefpVibes] Error reading M3U: {e}")
            self.session.open(MessageBox, f"Cannot read playlist:\n{path}", MessageBox.TYPE_ERROR)
            return
        
        current_title = ""
        entries_found = 0
        
        for line in lines:
            if not line:
                continue
                
            if line.startswith("#EXTINF:"):
                if "," in line:
                    current_title = line.split(",", 1)[1].strip()
            elif line.startswith("http") and any(ext in line.lower() for ext in [".mp3", ".flac", ".m4a", ".aac"]):
                # Online audio fajl
                title = (current_title or os.path.basename(line))
                
                for ext in [".mp3", ".flac", ".m4a", ".aac"]:
                    title = title.replace(ext, "")
                title = title.strip()
                
                self.playlist.append((title, line))
                entries_found += 1
                current_title = ""
            elif line and not line.startswith("#") and any(ext in line.lower() for ext in [".mp3", ".flac", ".m4a", ".aac"]):
                # Lokalni audio fajl
                title = os.path.basename(line)
                for ext in [".mp3", ".flac", ".m4a", ".aac"]:
                    title = title.replace(ext, "")
                title = title.strip()
                
                if not os.path.isabs(line):
                    m3u_dir = os.path.dirname(path)
                    absolute_path = os.path.join(m3u_dir, line)
                    if os.path.exists(absolute_path):
                        line = absolute_path
                    else:
                        print(f"[CiefpVibes] File not found: {line}")
                        continue
                
                self.playlist.append((title, line))
                entries_found += 1
                current_title = ""
        
        print(f"[CiefpVibes] M3U parsed: {entries_found} entries")
        
        if entries_found == 0:
            for line in lines:
                if line and not line.startswith("#"):
                    if line.startswith("http") or any(line.lower().endswith(ext) for ext in [".mp3", ".flac", ".m4a", ".aac"]):
                        title = os.path.basename(line)
                        for ext in [".mp3", ".flac", ".m4a", ".aac"]:
                            title = title.replace(ext, "")
                        title = title.strip()
                        self.playlist.append((title, line))
                        entries_found += 1
            
            if entries_found == 0:
                print(f"[CiefpVibes] No valid entries in M3U")

    # === WELCOME PLAYLIST ===
    
    def loadPlaylist(self):
        """Učitaj welcome playlistu sa GitHub-a"""
        welcome_url = "https://raw.githubusercontent.com/ciefp/CiefpVibesFiles/main/TV/userbouquet.ciefpvibes_welcome.tv"
        tmp_path = "/tmp/ciefpvibes_welcome.tv"
        self["nowplaying"].setText("🌐 Loading welcome playlist...")

        try:
            urllib.request.urlretrieve(welcome_url, tmp_path)
            print(f"[CiefpVibes] Downloaded welcome playlist")
        except Exception as e:
            print(f"[CiefpVibes] Download error: {e}")
            self["nowplaying"].setText("⚠ Download failed")
            self.session.open(MessageBox, f"Can't download welcome playlist:\n{e}", MessageBox.TYPE_ERROR)
            return

        try:
            with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"[CiefpVibes] File read error: {e}")
            self["nowplaying"].setText("⚠ File error")
            return

        entries = []
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("#SERVICE"):
                try:
                    parts = line[9:].split(":")
                    if len(parts) >= 11:
                        url_encoded = ":".join(parts[10:-1]) if len(parts) > 11 else parts[10]
                        url = unquote(url_encoded)
                        name = "Unknown"

                        if i + 1 < len(lines) and lines[i + 1].strip().startswith("#DESCRIPTION"):
                            name = lines[i + 1].strip()[13:]
                            for ext in [".mp3", ".flac", ".m4a", ".aac"]:
                                name = name.replace(ext, "")
                            name = name.strip()
                            i += 1
                        else:
                            name = parts[-1]
                            for ext in [".mp3", ".flac", ".m4a", ".aac"]:
                                name = name.replace(ext, "")
                            name = name.strip()

                        if any(ext in url.lower() for ext in [".mp3", ".flac", ".m4a", ".aac"]):
                            clean_name = name if name != "Unknown" else os.path.basename(url)
                            entries.append((clean_name, url))
                except Exception as ex:
                    print(f"[CiefpVibes] Error parsing line: {ex}")
            i += 1

        self.playlist = entries
        self["playlist"].list = self.playlist

        if self.playlist:
            self.currentIndex = 0
            self["playlist"].index = 0
            self["nowplaying"].setText(f"🎵 Welcome Playlist • {len(self.playlist)} songs")
            print(f"[CiefpVibes] Loaded {len(self.playlist)} songs")
            self.playCurrent()
        else:
            self["nowplaying"].setText("⚠ Empty playlist")
            self.session.open(MessageBox, "Welcome playlist is empty!",
                              MessageBox.TYPE_WARNING)

    # === ALBUM COVER ==
    def fetchAlbumCover(self, artist, title):
        print(f"[CiefpVibes] Searching cover for: {artist or 'Unknown'} - {title or 'Unknown'}")

        if not artist and not title:
            return None

        def clean_string(text):
            if not text:
                return ""
            import re
            text = re.sub(r'[<>:"/\\|?*]', '', text)
            return text.strip()

        clean_artist = clean_string(artist)
        clean_title = clean_string(title)

        cache_dir = CACHE_DIR

        # === PRVO: Provera keša (postojeći HOTFIX, ostaje isti) ===
        if os.path.exists(cache_dir):
            for filename in os.listdir(cache_dir):
                if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    full_path = os.path.join(cache_dir, filename)
                    if not os.path.isfile(full_path) or os.path.getsize(full_path) < 1024:
                        continue

                    filename_lower = filename.lower()

                    if clean_artist and clean_title:
                        artist_words = [w for w in clean_artist.lower().split() if len(w) > 2]
                        title_words = [w for w in clean_title.lower().split() if len(w) > 2]
                        artist_match = any(w in filename_lower for w in artist_words)
                        title_match = any(w in filename_lower for w in title_words)
                        if artist_match and title_match:
                            print(f"[CiefpVibes-HOTFIX] Perfect cache match: {filename}")
                            return full_path
                        if artist_match or title_match:
                            print(f"[CiefpVibes-HOTFIX] Partial cache match: {filename}")
                            return full_path

                    elif clean_title:
                        title_words = [w for w in clean_title.lower().split() if len(w) > 2]
                        if title_words and any(w in filename_lower for w in title_words):
                            print(f"[CiefpVibes-HOTFIX] Title-only cache match: {filename}")
                            return full_path

                    elif clean_artist:
                        artist_words = [w for w in clean_artist.lower().split() if len(w) > 2]
                        if artist_words and any(w in filename_lower for w in artist_words):
                            print(f"[CiefpVibes-HOTFIX] Artist-only cache match: {filename}")
                            return full_path

        # === DRUGO: iTunes pretraga sa fallback logikom ===
        import urllib.parse

        base_url = "https://itunes.apple.com/search"
        queries = []

        if clean_artist and clean_title:
            queries.append((f"{clean_artist} {clean_title}", "song"))
        if clean_title:
            queries.append((clean_title, "song"))
        if clean_artist:
            queries.append((clean_artist, "album"))  # Fallback: traži albume izvođača

        for query, entity in queries:
            print(f"[CiefpVibes] Trying iTunes query: '{query}' (entity={entity})")
            params = {
                "term": query,
                "entity": entity,
                "limit": 5,
                "country": "US",
                "media": "music"
            }
            url = base_url + "?" + urllib.parse.urlencode(params)

            try:
                with urllib.request.urlopen(url, timeout=8) as response:
                    data = json.loads(response.read().decode())
                    if data.get("resultCount", 0) == 0:
                        continue

                    for result in data["results"]:
                        artwork100 = result.get("artworkUrl100")
                        if not artwork100:
                            continue

                        artwork = artwork100.replace("100x100bb", "600x600bb")

                        res_artist = result.get("artistName", "").lower()
                        res_title = result.get("trackName", "") or result.get("collectionName", "")

                        # Provera match-a
                        good_match = True
                        if clean_artist and clean_artist.lower() not in res_artist:
                            good_match = False
                        if entity == "song" and clean_title and clean_title.lower() not in res_title.lower():
                            good_match = False

                        if good_match:
                            cache_name = f"{clean_artist or 'Unknown'}_{clean_title or 'Single'}.jpg".replace(' ', '_')
                            if entity == "album" and not clean_title:
                                cache_name = f"{clean_artist}_artist.jpg".replace(' ', '_')

                            cover_path = self.downloadAndCacheCover(artwork, cache_name)
                            if cover_path:
                                print(f"[CiefpVibes] Downloaded cover: {os.path.basename(cover_path)}")
                                return cover_path

            except Exception as e:
                print(f"[CiefpVibes] iTunes error for '{query}': {e}")
                continue

        print(f"[CiefpVibes] No cover found for {artist} - {title}")
        return None

    def getCacheSize(self):
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(CACHE_DIR):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.isfile(fp):
                        total_size += os.path.getsize(fp)
            return round(total_size / (1024 * 1024), 1)
        except:
            return 0

    def clearCache(self):
        try:
            for filename in os.listdir(CACHE_DIR):
                file_path = os.path.join(CACHE_DIR, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"[CiefpVibes] Error deleting {file_path}: {e}")
            
            return True, self.getCacheSize()
        except Exception as e:
            print(f"[CiefpVibes] Error clearing cache: {e}")
            return False, self.getCacheSize()

    # === PLAYBACK ===
    def playCurrent(self):
        if not self.playlist or not (0 <= self.currentIndex < len(self.playlist)):
            return

        # RESETUJ kontrolu postera za novu pesmu
        self.poster_locked = False
        self.poster_change_count = 0
        self.current_poster_path = ""

        # Resetuj folder cover keš za novu pesmu
        # (ovo će forsirati ponovno traženje lokalnog postera)
        self.folderCoverCache = {}

        name, url = self.playlist[self.currentIndex]

        # Da li je lokalni fajl?
        is_local_file = url.startswith('/') or url.startswith('file://')
        # Da li je online stream?
        is_online_stream = url.startswith('http://') or url.startswith('https://')

        # ZA ONLINE STREAM, POSTAVI POSEBNA PRAVILA
        if is_online_stream:
            self.is_current_stream_online = True
            self.max_poster_changes = 10
            self.poster_search_delay = 8

            # Resetuj praćenje naslova
            self.last_displayed_title = ""

            # Postavi callback za timer (sada je metoda već definisana)
            if not self.poster_search_timer.callback:
                self.poster_search_timer.callback.append(self.delayedPosterSearch)

            # Kreiraj timer za automatsko ažuriranje ako već ne postoji
            if not hasattr(self, 'auto_title_update_timer') or self.auto_title_update_timer is None:
                self.auto_title_update_timer = eTimer()
                self.auto_title_update_timer.callback.append(self.autoUpdateTitle)

            # POKRENI FORCE REFRESH TIMER (DODAJTE OVO)
            if hasattr(self, 'force_refresh_timer'):
                self.force_refresh_timer.stop()  # Zaustavi prethodni ako postoji
            else:
                self.force_refresh_timer = eTimer()
                self.force_refresh_timer.callback.append(self.forceRefreshMetadata)

            self.force_refresh_timer.start(10000, False)  # 10 sekundi

            print(f"[CiefpVibes] Online stream detected - auto title updates enabled")
        else:
            self.is_current_stream_online = False
            self.max_poster_changes = 3  # Standardno za lokalne fajlove
            self.poster_locked = False  # Resetuj za lokalne fajlove

        if is_local_file:
            filepath = url.replace('file://', '')
            if os.path.isfile(filepath):
                print(f"[CiefpVibes] Local file detected: {filepath}")
                print(f"[CiefpVibes] Full path: {filepath}")

                # PRVO: Proveri da li postoji lokalni cover u folderu
                cover_found = False
                local_cover = self.findLocalCover(filepath)
                if local_cover and os.path.isfile(local_cover):
                    print(f"[CiefpVibes] Found local cover, displaying: {local_cover}")
                    print(f"[CiefpVibes] Local cover size: {os.path.getsize(local_cover)} bytes")

                    # Otključaj za lokalni cover
                    self.poster_locked = False
                    self.poster_change_count = 0
                    self.showPoster(local_cover)
                    # Zaključaj lokalni poster
                    self.poster_locked = True
                    cover_found = True
                else:
                    print(f"[CiefpVibes] No local cover found")
                    cover_found = False

                # Učitavanje tagova
                tags = self.read_audio_tags(filepath)

                # Sačuvaj tagove
                self.current_song_info = tags

                # Formiranje imena za prikaz
                if tags["title"]:
                    if tags["artist"]:
                        display_name = f"{tags['artist']} - {tags['title']}"
                    else:
                        display_name = tags["title"]

                    self["nowplaying"].setText(f"▶ {display_name}")

                    # Pokušaj online cover samo ako nema lokalnog
                    if not cover_found:
                        if tags["artist"]:
                            print(f"[CiefpVibes] Trying online cover search for: {tags['artist']} - {tags['title']}")
                            cover = self.fetchAlbumCover(tags["artist"], tags["title"])
                        else:
                            print(f"[CiefpVibes] No artist tag, using title only: {tags['title']}")
                            cover = self.fetchAlbumCover("", tags["title"])

                        if cover and os.path.isfile(cover):
                            print(f"[CiefpVibes] Using online cover: {cover}")
                            # Otključaj za online cover
                            self.poster_locked = False
                            self.poster_change_count = 0
                            self.showPoster(cover)
                            # Zaključaj poster nakon online pretrage
                            self.poster_locked = True
                        else:
                            print(f"[CiefpVibes] No online cover found, showing default")
                            self.showDefaultPoster()
                else:
                    # Nema tagova - koristi ime fajla
                    self["nowplaying"].setText(f"▶ {name}")
                    if not cover_found:
                        # Pokušaj cover na osnovu imena fajla
                        filename = os.path.basename(filepath)
                        song_name = os.path.splitext(filename)[0]
                        if " - " in song_name:
                            parts = song_name.split(" - ", 1)
                            if len(parts) == 2:
                                artist_from_name = parts[0].strip()
                                title_from_name = parts[1].strip()
                                cover = self.fetchAlbumCover(artist_from_name, title_from_name)
                                if cover and os.path.isfile(cover):
                                    print(f"[CiefpVibes] Found cover from filename: {cover}")
                                    self.poster_locked = False
                                    self.poster_change_count = 0
                                    self.showPoster(cover)
                                    self.poster_locked = True
                                else:
                                    self.showDefaultPoster()
                        else:
                            self.showDefaultPoster()

            else:
                # Fajl ne postoji
                self["nowplaying"].setText(f"▶ {name}")
                self.showDefaultPoster()

        elif is_online_stream:
            # ONLINE STREAM LOGIC
            self["nowplaying"].setText(f"▶ {name}")

            # Za online stream, odmah pokušaj da dobiješ poster iz metapodataka
            # Resetuj trenutne podatke o pesmi
            self.current_song_info = {"artist": "", "title": ""}

            # Prvo prikaži default poster
            self.showDefaultPoster()

            # === NOVO: Pokušaj fallback iz naziva pesme ODMAH ===
            # Mnogi GitHub streamovi nemaju ICY podatke, pa parsiraj iz naziva
            artist_from_name, title_from_name = self.parseArtistTitle(name)
            if artist_from_name or title_from_name:
                self.current_song_info["artist"] = artist_from_name
                self.current_song_info["title"] = title_from_name
                print(f"[CiefpVibes] Fallback metadata from playlist name: {artist_from_name} - {title_from_name}")
                self.updateNowPlayingText()
                # Odmah pokušaj poster na osnovu ovoga
                self.updatePosterFromMetadata(force_update=True)

            # Sačuvaj informaciju da je ovo online stream
            self.is_current_stream_online = True

        else:
            # Ostali tipovi (npr. file:// URL)
            self["nowplaying"].setText(f"▶ {name}")
            self.showDefaultPoster()

        # STREAM STATUS RESET
        self.stream_active = True
        self.stream_check_counter = 0
        self.last_audio_data_time = 0
        self.vibe_value = 0
        self.vibe_direction = 1

        self["offline_status"].hide()
        self["progress_real"].show()
        self["progress_vibe"].show()

        # ==== NOVO: UVIJEK POČNI OD NULE ====
        try:
            service = self.session.nav.getCurrentService()
            if service:
                seek = service.seek()
                if seek:
                    seek.seekTo(0)
        except:
            pass
        # ====================================

        # POKRENI PESMU
        ref = eServiceReference(4097, 0, url)
        ref.setName(name)
        self.session.nav.playService(ref)

        # Probaj da ukloniš pauzu
        service = self.session.nav.getCurrentService()
        if service:
            pauseable = service.pause()
            if pauseable:
                pauseable.unpause()

        self.resetProgress()
        self.progress_timer.start(200, False)
        self.vibe_timer.start(200, False)
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
            pass
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
        import time
        self.last_audio_data_time = time.time()
        self.stream_active = True
        self.stream_check_counter = 0

    def checkStreamStatus(self):
        import time
        
        if not self.stream_active:
            return
            
        self.stream_check_counter += 1
        
        if self.last_audio_data_time > 0 and time.time() - self.last_audio_data_time > 10:
            self.stream_active = False
            self.showOfflineStatus()
        
        elif self.stream_check_counter > 10:
            service = self.session.nav.getCurrentService()
            if service:
                seek = service.seek()
                if seek:
                    pos = seek.getPlayPosition()
                    if pos[0]:
                        if self.current_position == pos[1] and self.current_position > 0:
                            self.stream_active = False
                            self.showOfflineStatus()
                        else:
                            self.current_position = pos[1]
                            self.stream_check_counter = 0
        
        self.stream_check_timer.start(2000, False)

    def showOfflineStatus(self):
        self["offline_status"].setText("OFFLINE")
        self["offline_status"].show()
        self["progress_vibe"].hide()
        self.vibe_timer.stop()
        
        if self.playlist and 0 <= self.currentIndex < len(self.playlist):
            name = self.playlist[self.currentIndex][0]
            self["nowplaying"].setText(f"⭕ {name} [OFFLINE]")

    def updateProgress(self):
        service = self.session.nav.getCurrentService()
        if not service:
            if self.stream_active:
                self.stream_active = False
                self.showOfflineStatus()
            return

        info = service.info()
        new_metadata = False

        if info:
            raw_title = info.getInfoString(iServiceInformation.sTagTitle).strip()
            artist_tag = info.getInfoString(iServiceInformation.sTagArtist)
            title_tag = info.getInfoString(iServiceInformation.sTagTitle)

            # ===== 1. PROVERA PROMENE NA INFOBARU (ZA ONLINE RADIO) =====
            if raw_title and raw_title != self.last_displayed_title:
                print(f"[CiefpVibes] Infobar title changed: {raw_title[:50]}")
                self.last_displayed_title = raw_title

                # Za online radio, odmah parsiraj i ažuriraj
                if self.is_current_stream_online:
                    artist, title = self.parseArtistTitle(raw_title)
                    if artist or title:
                        # Ažuriraj trenutne podatke
                        self.current_song_info["artist"] = artist
                        self.current_song_info["title"] = title

                        # Ažuriraj prikaz naziva
                        self.updateNowPlayingText()

                        # Zaustavi prethodni timer za poster
                        self.poster_search_timer.stop()

                        # Postavi novi timer za poster (8 sekundi)
                        self.poster_search_timer.start(8000, True)

                        # Prikaži default poster odmah
                        self.showDefaultPoster()

                        print(f"[CiefpVibes] Updated from infobar: {artist} - {title}")

            artist = ""
            title = ""

            if raw_title:
                if raw_title.startswith("ICY: "):
                    raw_title = raw_title[5:].strip()
                artist, title = self.parseArtistTitle(raw_title)

                if artist or title:
                    if artist != self.current_song_info["artist"] or title != self.current_song_info["title"]:
                        self.current_song_info["artist"] = artist
                        self.current_song_info["title"] = title
                        new_metadata = True
                        print(f"[CiefpVibes] New metadata from ICY: {artist} - {title}")

            elif artist_tag and artist_tag.strip():
                if artist_tag.strip() != self.current_song_info["artist"]:
                    self.current_song_info["artist"] = artist_tag.strip()
                    new_metadata = True
                    print(f"[CiefpVibes] New metadata from tag: Artist={artist_tag}")

            elif title_tag and title_tag.strip():
                # Neki streamovi stavljaju artist • title u title tag
                if " • " in title_tag:
                    parts = title_tag.split(" • ", 1)
                    if len(parts) > 1:
                        a, t = self.parseArtistTitle(parts[1])
                        if a or t:
                            if a != self.current_song_info["artist"] or t != self.current_song_info["title"]:
                                self.current_song_info["artist"] = a
                                self.current_song_info["title"] = t
                                new_metadata = True
                                print(f"[CiefpVibes] New metadata from title tag: {a} - {t}")

            # === NOVO: Fallback ako nemamo artist, ali imamo title ===
            if not self.current_song_info["artist"] and self.current_song_info["title"]:
                if self.playlist and 0 <= self.currentIndex < len(self.playlist):
                    name = self.playlist[self.currentIndex][0]
                    fallback_artist, fallback_title = self.parseArtistTitle(name)
                    if fallback_artist:
                        self.current_song_info["artist"] = fallback_artist
                        if fallback_title:
                            self.current_song_info["title"] = fallback_title
                        new_metadata = True
                        print(
                            f"[CiefpVibes] Fallback metadata from playlist name: {fallback_artist} - {self.current_song_info['title']}")

            # ===== 2. OBRADA NOVIH METAPODATAKA =====
            if new_metadata:
                self.updateNowPlayingText()

                # POSEBNA LOGIKA ZA ONLINE RADIO
                if self.is_current_stream_online:
                    print(f"[CiefpVibes] Online radio - new metadata detected")

                    # Zaustavi prethodni timer (ako postoji)
                    self.poster_search_timer.stop()

                    # Postavi timer za 8 sekundi (kraće čekanje)
                    self.poster_search_timer.start(8000, True)

                    # Za sada prikaži default poster
                    self.showDefaultPoster()

                    # ===== NOVO: POKRENI AUTOMATSKO AŽURIRANJE =====
                    if not hasattr(self, 'auto_title_update_timer') or not self.auto_title_update_timer.isActive():
                        # Kreiraj timer ako ne postoji
                        self.auto_title_update_timer = eTimer()
                        self.auto_title_update_timer.callback.append(self.autoUpdateTitle)
                        self.auto_title_update_timer.start(5000, False)  # 5 sekundi

                else:
                    # Za lokalne fajlove - stara logika
                    self.updatePosterFromMetadata(force_update=True)

        # ===== 3. PROGRESS BAR UPDATE =====
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

    def autoUpdateTitle(self):
        """Automatski ažurira naziv pesme za online radio"""
        if self.is_current_stream_online and self.stream_active:
            service = self.session.nav.getCurrentService()
            if service:
                info = service.info()
                if info:
                    raw_title = info.getInfoString(iServiceInformation.sTagTitle).strip()
                    if raw_title and raw_title != self.last_displayed_title:
                        print(f"[CiefpVibes] Auto-update detected new title: {raw_title[:50]}")
                        self.last_displayed_title = raw_title

                        artist, title = self.parseArtistTitle(raw_title)
                        if artist or title:
                            # Ažuriraj samo ako su se stvarno promenili
                            if (artist != self.current_song_info["artist"] or
                                    title != self.current_song_info["title"]):
                                self.current_song_info["artist"] = artist
                                self.current_song_info["title"] = title
                                self.updateNowPlayingText()

                                # Resetuj poster kontrolu
                                self.poster_locked = False
                                self.poster_change_count = 0

                                # Pokreni odloženo traženje postera
                                self.poster_search_timer.stop()
                                self.poster_search_timer.start(5000, True)

                                print(f"[CiefpVibes] Auto-updated: {artist} - {title}")

        # Ponovi za 5 sekundi
        if self.is_current_stream_online:
            self.auto_title_update_timer.start(5000, False)

    def updateNowPlayingText(self):
        # Za online radio, resetuj timer kada se promeni prikaz
        if self.is_current_stream_online:
            self.last_title_change_time = time.time()
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

    def updatePosterFromMetadata(self, force_update=False):
        print(f"[CiefpVibes-DEBUG] updatePosterFromMetadata called, force_update={force_update}")
        print(f"[CiefpVibes-DEBUG] is_current_stream_online: {self.is_current_stream_online}")

        # === LOKALNI FAJLOVI: PRVO TRAŽI COVER U FOLDERU ===
        if not self.is_current_stream_online:
            # Dobavi putanju trenutno sviranog fajla
            ref = self.session.nav.getCurrentlyPlayingServiceReference()
            if ref:
                path = ref.getPath()
                if path:
                    print(f"[CiefpVibes-DEBUG] Local file path: {path}")

                    # Prvo pokušaj lokalni cover u folderu
                    local_cover = self.findLocalCover(path)
                    if local_cover and os.path.isfile(local_cover):
                        print(f"[CiefpVibes] Using LOCAL folder cover: {local_cover}")
                        # Otključaj za lokalne fajlove da bi mogao da prikaže
                        self.poster_locked = False
                        self.poster_change_count = 0
                        self.showPoster(local_cover)

                        # Zaključaj lokalni poster nakon uspešnog prikaza
                        self.poster_locked = True
                        return  # Prekini dalju obradu, već imamo lokalni cover
                    else:
                        print(f"[CiefpVibes] No local cover found, trying online...")

        # POSEBNA LOGIKA ZA ONLINE RADIO
        if self.is_current_stream_online:
            # Za online radio, uvek dozvoli promenu
            self.poster_locked = False
            self.max_poster_changes = 10  # Više pokušaja za online radio
            print(f"[CiefpVibes] Online radio mode - posters unlocked")

        # Otključaj ako je trenutni poster default (da dozvoli novi pokušaj)
        default_posters = ["poster1.png", "poster2.png", "poster3.png", "poster4.png", "poster5.png",
                           "poster6.png", "poster7.png", "poster8.png", "poster9.png", "poster10.png"]
        if self.current_poster_path and os.path.basename(self.current_poster_path) in default_posters:
            self.poster_locked = False
            self.poster_change_count = 0
            print(f"[CiefpVibes-DEBUG] Unlocked default poster for new attempt")

        # === FALLBACK: Ako nemamo artist, pokušaj da ekstraktuješ iz title-a ===
        if not self.current_song_info["artist"] and self.current_song_info["title"]:
            title = self.current_song_info["title"]
            print(f"[CiefpVibes-URGENT] No artist, but have title: '{title}'")
            # Pokušaj da izvučeš artist iz title-a ako je u formatu "Artist - Title"
            if " - " in title:
                parts = title.split(" - ", 1)
                if len(parts) == 2:
                    potential_artist = parts[0].strip()
                    potential_title = parts[1].strip()

                    # Proveri da li je "artist" stvarno artist (nije prazan, ima smisla)
                    if potential_artist and len(potential_artist) > 1:
                        print(f"[CiefpVibes-URGENT] Extracted artist from title: '{potential_artist}'")
                        self.current_song_info["artist"] = potential_artist
                        self.current_song_info["title"] = potential_title
                        # Ažuriraj i prikaz
                        self.updateNowPlayingText()

        # SAMO ZA LOKALNE FAJLOVE ZAKLJUČAVAJ
        if not self.is_current_stream_online and self.poster_locked and not force_update:
            print(f"[CiefpVibes-DEBUG] Local file poster locked, skipping")
            return

        artist = self.current_song_info["artist"]
        title = self.current_song_info["title"]

        print(f"[CiefpVibes-DEBUG] Artist: '{artist}', Title: '{title}'")

        if not artist and not title:
            # Nemoj automatski prikazivati default poster
            # Ako već imamo poster, ostavi ga
            if not self.current_poster_path:
                print(f"[CiefpVibes-DEBUG] No artist/title, showing default poster")
                self.showDefaultPoster()
            else:
                print(f"[CiefpVibes-DEBUG] No artist/title, but have existing poster")
                return

        # Za online stream-ove, uvek pokušaj da nađeš novi poster
        print(f"[CiefpVibes-DEBUG] Calling fetchAlbumCover...")
        cover = self.fetchAlbumCover(artist, title)
        print(f"[CiefpVibes-DEBUG] fetchAlbumCover returned: {cover}")

        if cover and os.path.isfile(cover):
            print(f"[CiefpVibes-DEBUG] Cover found, calling showPoster...")
            # Prikaži novi poster
            self.showPoster(cover)

            # NOVO: Zaključaj poster nakon što se potvrdi da je dobar
            # Dodaj timer koji će zaključati poster nakon 3 sekunde
            if self.is_current_stream_online:
                # Postavi timer za 3 sekunde
                self.lock_timer = eTimer()
                self.lock_timer.callback.append(self.lockCurrentPoster)
                self.lock_timer.start(3000, True)  # 3000ms = 3s
                print(f"[CiefpVibes-DEBUG] Setting lock timer for 3 seconds...")
        else:
            # Ako nije nađen poster, prikaži default
            self.showDefaultPoster()

    def delayedPosterSearch(self):
        """Traži poster 10 sekundi nakon promene pesme (za online radio)"""
        print(f"[CiefpVibes] Delayed poster search triggered")

        artist = self.current_song_info["artist"]
        title = self.current_song_info["title"]

        if artist or title:
            print(f"[CiefpVibes] Searching for: {artist} - {title}")

            # Resetuj kontrolu postera
            self.poster_locked = False
            self.poster_change_count = 0

            # Pokušaj da nađeš poster
            cover = self.fetchAlbumCover(artist, title)
            if cover and os.path.isfile(cover):
                self.showPoster(cover)
                print(f"[CiefpVibes] Delayed search SUCCESS: {os.path.basename(cover)}")
            else:
                print(f"[CiefpVibes] Delayed search failed")
        else:
            print(f"[CiefpVibes] No metadata for delayed search")

    # Nova metoda:
    def detectMetadataChange(self, raw_title):
        """Detektuje da li su se metapodaci promenili"""
        if not raw_title:
            return False

        # Dodaj u istoriju (zadržavamo poslednjih 5)
        self.metadata_history.append(raw_title)
        if len(self.metadata_history) > 5:
            self.metadata_history.pop(0)

        # Proveri da li se naslov promenio
        if len(self.metadata_history) >= 2:
            if self.metadata_history[-1] != self.metadata_history[-2]:
                self.metadata_change_counter += 1
                print(f"[CiefpVibes] Metadata change #{self.metadata_change_counter}")
                return True

        return False

    # Nova metoda:
    def forceRefreshMetadata(self):
        """Forsira osvežavanje metapodataka i naziva"""
        print(f"[CiefpVibes] Force refreshing metadata...")

        service = self.session.nav.getCurrentService()
        if not service:
            return

        info = service.info()
        if info:
            raw_title = info.getInfoString(iServiceInformation.sTagTitle).strip()

            if raw_title and raw_title != self.last_displayed_title:
                print(f"[CiefpVibes] Force refresh found new title: {raw_title[:50]}")
                self.last_displayed_title = raw_title

                # Parsiraj
                artist, title = self.parseArtistTitle(raw_title)
                if artist or title:
                    # Ažuriraj
                    self.current_song_info["artist"] = artist
                    self.current_song_info["title"] = title
                    self.updateNowPlayingText()

                    # Traži novi poster
                    self.poster_locked = False
                    self.poster_change_count = 0
                    self.updatePosterFromMetadata(force_update=True)

    def autoUpdateNowPlaying(self):
        """Automatski ažurira naziv pesme svakih 5 sekundi za online radio"""
        if self.is_current_stream_online and self.stream_active:
            # Proveri da li imamo novije metapodatke
            service = self.session.nav.getCurrentService()
            if service:
                info = service.info()
                if info:
                    raw_title = info.getInfoString(iServiceInformation.sTagTitle).strip()
                    if raw_title and raw_title != self.last_displayed_title:
                        print(f"[CiefpVibes] Auto-update: new title detected")
                        self.last_displayed_title = raw_title

                        # Parsiraj i ažuriraj
                        artist, title = self.parseArtistTitle(raw_title)
                        if artist or title:
                            self.current_song_info["artist"] = artist
                            self.current_song_info["title"] = title
                            self.updateNowPlayingText()

        # Ponovi za 5 sekundi
        self.auto_title_update_timer.start(5000, False)

    def downloadAndCacheCover(self, artwork_url, cache_name):
        """Skida artwork sa URL-a i kešuje ga u /tmp/ciefpvibes_cache"""
        if not artwork_url:
            return None

        try:
            # Normalizuj ime fajla za keš
            safe_name = "".join(c for c in cache_name if c.isalnum() or c in (" ", "_", "-")).rstrip()
            if not safe_name:
                safe_name = "cover"
            cache_path = os.path.join(CACHE_DIR, safe_name + ".jpg")

            # Ako već postoji u kešu, vrati putanju
            if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1024:
                print(f"[CiefpVibes] Using existing cached cover: {cache_path}")
                return cache_path

            # Skini sliku
            print(f"[CiefpVibes] Downloading cover from: {artwork_url}")
            req = urllib.request.Request(artwork_url)
            req.add_header("User-Agent", f"{PLUGIN_NAME}/{PLUGIN_VERSION}")

            with urllib.request.urlopen(req, timeout=10) as response:
                with open(cache_path, "wb") as f:
                    f.write(response.read())

            file_size = os.path.getsize(cache_path)
            if file_size > 1024:
                print(f"[CiefpVibes] Cover saved: {cache_path} ({file_size} bytes)")
                return cache_path
            else:
                print(f"[CiefpVibes] Downloaded file too small ({file_size} bytes), deleting")
                os.remove(cache_path)
                return None

        except Exception as e:
            print(f"[CiefpVibes] Error downloading cover: {str(e)}")
            if os.path.exists(cache_path):
                try:
                    os.remove(cache_path)
                except:
                    pass
            return None

    def parse_id3v1(self, filepath):
        """Parsira ID3v1 tag iz MP3 fajla"""
        try:
            with open(filepath, 'rb') as f:
                f.seek(-128, 2)  # ID3v1 je poslednjih 128 bajtova
                tag_data = f.read(128)

                if len(tag_data) == 128 and tag_data[:3] == b'TAG':
                    title = tag_data[3:33].decode('iso-8859-1', errors='ignore').strip('\x00').strip()
                    artist = tag_data[33:63].decode('iso-8859-1', errors='ignore').strip('\x00').strip()
                    album = tag_data[63:93].decode('iso-8859-1', errors='ignore').strip('\x00').strip()

                    return {
                        "artist": artist,
                        "title": title,
                        "album": album,
                        "version": "ID3v1"
                    }
        except Exception as e:
            print(f"[CiefpVibes] ID3v1 parse error: {e}")

        return {"artist": "", "title": "", "album": "", "version": ""}

    def parse_id3v2_header(self, filepath):
        """Parsira ID3v2 header i traži tagove"""
        try:
            with open(filepath, 'rb') as f:
                header = f.read(10)

                if len(header) >= 10 and header[:3] == b'ID3':
                    # ID3v2 tag
                    major_version = header[3]
                    revision = header[4]
                    flags = header[5]
                    size = (header[6] << 21) | (header[7] << 14) | (header[8] << 7) | header[9]

                    print(f"[CiefpVibes] Found ID3v2.{major_version}.{revision}, size: {size}")

                    # Preskoči extended header ako postoji
                    if flags & 0x40:
                        ext_header_size_data = f.read(4)
                        if len(ext_header_size_data) == 4:
                            ext_header_size = (ext_header_size_data[0] << 21) | (ext_header_size_data[1] << 14) | (
                                        ext_header_size_data[2] << 7) | ext_header_size_data[3]
                            f.seek(ext_header_size, 1)

                    # Parsiraj frame-ove
                    artist = ""
                    title = ""
                    album = ""

                    while True:
                        frame_header = f.read(10)
                        if len(frame_header) < 10:
                            break

                        frame_id = frame_header[:4].decode('ascii', errors='ignore')
                        frame_size = (frame_header[4] << 24) | (frame_header[5] << 16) | (frame_header[6] << 8) | \
                                     frame_header[7]
                        frame_flags = frame_header[8:10]

                        if frame_size <= 0 or frame_size > 1024 * 1024:  # Ograniči veličinu
                            break

                        frame_data = f.read(frame_size)
                        if len(frame_data) != frame_size:
                            break

                        # TPE1 = Artist
                        if frame_id == 'TPE1':
                            encoding = frame_data[0]
                            if encoding == 0:  # ISO-8859-1
                                artist = frame_data[1:].decode('iso-8859-1', errors='ignore').strip('\x00')
                            elif encoding == 1 or encoding == 2:  # UTF-16 with BOM
                                try:
                                    artist = frame_data[3:].decode('utf-16', errors='ignore').strip('\x00')
                                except:
                                    artist = frame_data[1:].decode('utf-16-le', errors='ignore').strip('\x00')
                            elif encoding == 3:  # UTF-8
                                artist = frame_data[1:].decode('utf-8', errors='ignore').strip('\x00')

                        # TIT2 = Title
                        elif frame_id == 'TIT2':
                            encoding = frame_data[0]
                            if encoding == 0:
                                title = frame_data[1:].decode('iso-8859-1', errors='ignore').strip('\x00')
                            elif encoding == 1 or encoding == 2:
                                try:
                                    title = frame_data[3:].decode('utf-16', errors='ignore').strip('\x00')
                                except:
                                    title = frame_data[1:].decode('utf-16-le', errors='ignore').strip('\x00')
                            elif encoding == 3:
                                title = frame_data[1:].decode('utf-8', errors='ignore').strip('\x00')

                        # TALB = Album
                        elif frame_id == 'TALB':
                            encoding = frame_data[0]
                            if encoding == 0:
                                album = frame_data[1:].decode('iso-8859-1', errors='ignore').strip('\x00')
                            elif encoding == 1 or encoding == 2:
                                try:
                                    album = frame_data[3:].decode('utf-16', errors='ignore').strip('\x00')
                                except:
                                    album = frame_data[1:].decode('utf-16-le', errors='ignore').strip('\x00')
                            elif encoding == 3:
                                album = frame_data[1:].decode('utf-8', errors='ignore').strip('\x00')

                    if artist or title or album:
                        return {
                            "artist": artist.strip(),
                            "title": title.strip(),
                            "album": album.strip(),
                            "version": f"ID3v2.{major_version}"
                        }

        except Exception as e:
            print(f"[CiefpVibes] ID3v2 parse error: {e}")

        return {"artist": "", "title": "", "album": "", "version": ""}

    def read_id3_tags(self, filepath):
        """Glavna funkcija za čitanje ID3 tagova"""
        if not filepath or not os.path.isfile(filepath):
            return {"artist": "", "title": "", "album": ""}

        # Prvo pokušaj ID3v2
        tags = self.parse_id3v2_header(filepath)
        if tags["artist"] or tags["title"]:
            print(f"[CiefpVibes] Found ID3v2 tags: Artist='{tags['artist']}', Title='{tags['title']}'")
            return tags

        # Onda pokušaj ID3v1
        tags = self.parse_id3v1(filepath)
        if tags["artist"] or tags["title"]:
            print(f"[CiefpVibes] Found ID3v1 tags: Artist='{tags['artist']}', Title='{tags['title']}'")
            return tags

        print(f"[CiefpVibes] No ID3 tags found in: {os.path.basename(filepath)}")
        return {"artist": "", "title": "", "album": ""}

    def read_audio_tags(self, filepath):
        """Čita tagove iz audio fajla (MP3, FLAC, M4A)"""
        if not filepath or not os.path.isfile(filepath):
            return {"artist": "", "title": "", "album": ""}

        ext = os.path.splitext(filepath)[1].lower()

        # MP3
        if ext == '.mp3':
            return self.read_id3_tags(filepath)

        # FLAC (Vorbis comment)
        elif ext == '.flac':
            return self.read_flac_tags(filepath)

        # M4A/AAC (MP4)
        elif ext in ['.m4a', '.aac']:
            return self.read_mp4_tags(filepath)

        # OGG
        elif ext == '.ogg':
            return self.read_ogg_tags(filepath)

        return {"artist": "", "title": "", "album": ""}

    def read_flac_tags(self, filepath):
        """Parsira FLAC Vorbis komentare"""
        try:
            with open(filepath, 'rb') as f:
                # Proveri FLAC header
                header = f.read(4)
                if header != b'fLaC':
                    return {"artist": "", "title": "", "album": ""}

                artist = ""
                title = ""
                album = ""

                # Traži METADATA_BLOCK_VORBIS_COMMENT
                while True:
                    block_header = f.read(4)
                    if len(block_header) < 4:
                        break

                    is_last = (block_header[0] >> 7) & 1
                    block_type = block_header[0] & 0x7F
                    block_size = (block_header[1] << 16) | (block_header[2] << 8) | block_header[3]

                    if block_type == 4:  # VORBIS_COMMENT
                        # Preskoči vendor string length
                        vendor_len_data = f.read(4)
                        if len(vendor_len_data) == 4:
                            vendor_len = (vendor_len_data[0] | (vendor_len_data[1] << 8) |
                                          (vendor_len_data[2] << 16) | (vendor_len_data[3] << 24))
                            f.seek(vendor_len, 1)

                        # Pročitaj broj komentara
                        comment_count_data = f.read(4)
                        if len(comment_count_data) == 4:
                            comment_count = (comment_count_data[0] | (comment_count_data[1] << 8) |
                                             (comment_count_data[2] << 16) | (comment_count_data[3] << 24))

                            for _ in range(comment_count):
                                comment_len_data = f.read(4)
                                if len(comment_len_data) < 4:
                                    break
                                comment_len = (comment_len_data[0] | (comment_len_data[1] << 8) |
                                               (comment_count_data[2] << 16) | (comment_count_data[3] << 24))

                                comment_data = f.read(comment_len)
                                if len(comment_data) == comment_len:
                                    comment = comment_data.decode('utf-8', errors='ignore')
                                    if '=' in comment:
                                        key, value = comment.split('=', 1)
                                        key = key.upper()

                                        if key == 'ARTIST':
                                            artist = value
                                        elif key == 'TITLE':
                                            title = value
                                        elif key == 'ALBUM':
                                            album = value

                        return {
                            "artist": artist.strip(),
                            "title": title.strip(),
                            "album": album.strip()
                        }

                    elif is_last:
                        break
                    else:
                        f.seek(block_size, 1)

        except Exception as e:
            print(f"[CiefpVibes] FLAC parse error: {e}")

        return {"artist": "", "title": "", "album": ""}

    def read_mp4_tags(self, filepath):
        """Parsira MP4/M4A tagove"""
        try:
            with open(filepath, 'rb') as f:
                # Pročitaj atoms do "moov"
                while True:
                    atom_header = f.read(8)
                    if len(atom_header) < 8:
                        break

                    atom_size = (atom_header[0] << 24) | (atom_header[1] << 16) | (atom_header[2] << 8) | atom_header[3]
                    atom_type = atom_header[4:8].decode('ascii', errors='ignore')

                    if atom_type == 'moov':
                        moov_start = f.tell() - 8

                        while f.tell() < moov_start + atom_size:
                            sub_header = f.read(8)
                            if len(sub_header) < 8:
                                break

                            sub_size = (sub_header[0] << 24) | (sub_header[1] << 16) | (sub_header[2] << 8) | \
                                       sub_header[3]
                            sub_type = sub_header[4:8].decode('ascii', errors='ignore')

                            if sub_type == 'udta':  # User data
                                udta_start = f.tell() - 8

                                while f.tell() < udta_start + sub_size:
                                    meta_header = f.read(8)
                                    if len(meta_header) < 8:
                                        break

                                    meta_size = (meta_header[0] << 24) | (meta_header[1] << 16) | (
                                                meta_header[2] << 8) | meta_header[3]
                                    meta_type = meta_header[4:8].decode('ascii', errors='ignore')

                                    # Traži tagove (pojednostavljeno)
                                    if meta_type == '©ART':
                                        artist_data = f.read(meta_size - 8)
                                        artist = artist_data.decode('utf-8', errors='ignore').strip('\x00')
                                    elif meta_type == '©nam':
                                        title_data = f.read(meta_size - 8)
                                        title = title_data.decode('utf-8', errors='ignore').strip('\x00')
                                    elif meta_type == '©alb':
                                        album_data = f.read(meta_size - 8)
                                        album = album_data.decode('utf-8', errors='ignore').strip('\x00')
                                    else:
                                        f.seek(meta_size - 8, 1)

                                return {
                                    "artist": artist.strip() if 'artist' in locals() else "",
                                    "title": title.strip() if 'title' in locals() else "",
                                    "album": album.strip() if 'album' in locals() else ""
                                }
                            else:
                                f.seek(sub_size - 8, 1)
                    else:
                        if atom_size < 8:
                            break
                        f.seek(atom_size - 8, 1)

        except Exception as e:
            print(f"[CiefpVibes] MP4 parse error: {e}")

        return {"artist": "", "title": "", "album": ""}
        
    def parseArtistTitle(self, text):
        if not text:
            return "", ""

        original_text = text
        text = text.strip()
        print(f"[CiefpVibes-DEBUG] parseArtistTitle input: '{text}'")

        import re

        # 1. Ukloni godinu na kraju u zagradama (npr. "What Is Love (1993)")
        text = re.sub(r'\s*\(\d{4}\)\s*$', '', text).strip()

        # 2. Ukloni vodeći redni broj + separator
        # Podržava oblike: "001 - ", "01 - ", "008-", "10. ", "1 ", "12 -", "123.", itd.
        text = re.sub(r'^\d{1,4}\s*[\.\-\_\s]+\s*', '', text, flags=re.IGNORECASE).strip()

        print(f"[CiefpVibes-DEBUG] After cleaning track number/year: '{text}'")

        # 3. Poseban slučaj za " • " separator (neki online streamovi)
        if " • " in text:
            parts = text.split(" • ", 1)
            artist_title_part = parts[1].strip() if len(parts) > 1 else parts[0].strip()
            print(f"[CiefpVibes-DEBUG] Found ' • ' separator → using part: '{artist_title_part}'")
        else:
            artist_title_part = text

        # 4. Lista svih mogućih separatora između artist i title
        separators = [
            " - ", " – ", " — ", " | ", " :: ", " › ", " / ", " ~ ",
            " -", "- ", "– ", "— ", "| ", ":: ", "› ", "/ ", "~ "
        ]

        for sep in separators:
            if sep in artist_title_part:
                parts = artist_title_part.split(sep, 1)
                artist = parts[0].strip()
                title = parts[1].strip()

                # Očisti title od nepotrebnih sufiksa
                title = re.sub(r'\s*(?:\(|\[).*?(?:\)|])\s*$', '', title).strip()  # (Official Video), [Remix] itd.
                title = re.sub(r'\s*(Official|Video|Audio|Remix|Live|HD|Extended|Mix|Version).*?$', '', title, flags=re.IGNORECASE).strip()

                # Ukloni vodeće crtice ili tačke iz title-a
                while title.startswith(('-', '–', '—', '.', ' ', '_')):
                    title = title[1:].strip()

                if artist and title:
                    print(f"[CiefpVibes-DEBUG] SUCCESS → artist='{artist}', title='{title}' (from original: '{original_text}')")
                    return artist, title
                elif title:  # Ako ima samo title
                    print(f"[CiefpVibes-DEBUG] Title only → '{title}'")
                    return "", title

        # 5. Ako nema separatora – pretpostavi da je sve title
        print(f"[CiefpVibes-DEBUG] No separator found → title only: '{artist_title_part}'")
        return "", artist_title_part

    def lockCurrentPoster(self):
        """Zaključaj trenutni poster (samo za lokalne fajlove)"""
        if self.current_poster_path and not self.poster_locked:
            # ZAKLJUČAJ SAMO LOKALNE FAJLOVE
            if not self.is_current_stream_online:
                # Proveri da li je poster "dobro" ime (da nije default)
                default_posters = [f"poster{i}.png" for i in range(1, 11)]
                current_basename = os.path.basename(self.current_poster_path)

                if current_basename not in default_posters:
                    print(f"[CiefpVibes] Locking local poster: {current_basename}")
                    self.poster_locked = True
                else:
                    print(f"[CiefpVibes] Not locking default poster for local file")
            else:
                # ONLINE RADIO - NIKAD NE ZAKLJUČAVAJ
                print(f"[CiefpVibes] Online radio - keeping poster unlocked")

    def updateVibeProgress(self):
        if not self.stream_active:
            return
            
        self.vibe_value += self.vibe_direction * 5
        
        if self.vibe_value >= 70:
            self.vibe_value = 70
            self.vibe_direction = -1
        elif self.vibe_value <= 0:
            self.vibe_value = 0
            self.vibe_direction = 1
            
        self["progress_vibe"].setValue(self.vibe_value)

    # === EXIT ===
    
    def exit(self):
        self.session.nav.stopService()
        self.progress_timer.stop()
        self.vibe_timer.stop()
        self.stream_check_timer.stop()
        self.saveConfig()
        self.close()

    # === SETTINGS ===
    
    def openSettings(self):
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
                ("🧹 Clear Cache", "clear_cache"),
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
        elif key == "clear_cache":
            cache_size = self.getCacheSize()
            self.session.openWithCallback(
                self.clearCacheConfirmed,
                MessageBox,
                f"🧹 Clear all cached files?\n\nCurrent cache size: {cache_size}MB",
                MessageBox.TYPE_YESNO
            )
        elif key == "save":
            self.saveConfig()
            self.saveLastPlaylist()
            self.session.open(MessageBox, "💾 Configuration saved.", MessageBox.TYPE_INFO)

    def clearCacheConfirmed(self, result):
        if result:
            success, new_size = self.clearCache()
            if success:
                self.session.open(MessageBox, f"✅ Cache cleared!\n\nNew size: {new_size}MB", MessageBox.TYPE_INFO)
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
            self.showDefaultPoster()
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

    # === ONLINE FILES ===
    
    def openGitHubLists(self):
        self.session.openWithCallback(
            self.githubCategorySelected,
            ChoiceBox,
            title="📥 Online Files",
            list=[
                ("🎶 M3U Playlists", "M3U"),
                ("📺 .tv Bouquets", "TV"),
                ("📻 Radio Lists", "RADIO"),
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
        elif cat == "RADIO":
            url = GITHUB_RADIO_URL
        else:
            return

        items = self.fetchGitHubLists(url, cat)
        if not items:
            self.session.open(MessageBox, f"No lists in {cat} category.", MessageBox.TYPE_INFO)
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
                        if dl_url and name.lower().endswith((".m3u", ".m3u8", ".tv", ".radio")):
                            clean = name
                            if clean.startswith("userbouquet."):
                                clean = clean[12:]
                            clean = clean.replace("IPTV_OPD_", "").replace("IPTV ", "")
                            clean = clean.replace("_mp3", "").replace("_flac", "").replace("_m4a", "")
                            for date in [" 08.11.2025", "_08112025", "_03112025", "_29112025", "_0909_1"]:
                                clean = clean.replace(date, "")
                            clean = clean.replace("_", " ").replace(".", " ").strip()
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
            print(f"[CiefpVibes] GitHub error: {e}")
            return []

    def githubListSelected(self, choice):
        if not choice:
            return
        
        dl_url, filename = choice[1]
        display_name = choice[0]
        
        tmp_path = os.path.join(CACHE_DIR, filename)
        
        try:
            urllib.request.urlretrieve(dl_url, tmp_path)
            print(f"[CiefpVibes] Downloaded: {filename}")
            
            # Debug: pročitaj prvih nekoliko linija
            with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                first_lines = f.readlines()[:10]
                print(f"[CiefpVibes] First 10 lines:")
                for i, line in enumerate(first_lines):
                    print(f"  {i}: {line.strip()}")
            
            # Učitaj playlistu
            self.loadPlaylistFromFile(tmp_path, display_name)
            
        except Exception as e:
            print(f"[CiefpVibes] Error: {e}")
            self.session.open(MessageBox, 
                             f"❌ Error:\n{str(e)[:100]}", 
                             MessageBox.TYPE_ERROR)

    def showAbout(self):
        self.session.open(MessageBox, 
                         f"""{PLUGIN_NAME} v{PLUGIN_VERSION}
✅ Features:
• Direct MP3/FLAC/M4A playback
• Network shares (SMB/NFS)
• Online playlists
• Album covers
• 10 backgrounds/infobars/posters
• Repeat/Shuffle modes""",
                         MessageBox.TYPE_INFO)

# === FILE BROWSER ===
class CiefpFileBrowser(Screen):
    skin = '''
    <screen position="center,140" size="1600,800" title="..:: FILE BROWSER ::..">
        <widget name="filelist" position="10,10" size="1180,620" scrollbarMode="showOnDemand"/>
        <widget name="background" position="1200,0" size="400,800" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/CiefpVibes/fileexplorer.png" zPosition="-1" alphatest="on" />
        <widget name="curr_dir" position="10,650" size="1180,40" font="Regular;30" halign="center"/>
        <widget name="key_red"   position="40,700" size="200,50" font="Regular;32" halign="center" backgroundColor="#300000" foregroundColor="#ff5555"/>
        <widget name="key_green" position="280,700" size="200,50" font="Regular;32" halign="center" backgroundColor="#003000" foregroundColor="#55ff55"/>
        <widget name="key_yellow" position="520,700" size="200,50" font="Regular;32" halign="center" backgroundColor="#303000" foregroundColor="#ffff55" text="🌐 Network"/>
        <widget name="key_blue"   position="760,700" size="200,50" font="Regular;32" halign="center" backgroundColor="#000030" foregroundColor="#5599ff" text="📁 Folder"/>
    </screen>
    '''
    
    def __init__(self, session, initial_dir="/tmp"):
        Screen.__init__(self, session)
        self["background"] = Pixmap()
        self["filelist"] = FileList(initial_dir, showDirectories=True, showFiles=True)
        self["curr_dir"] = Label(initial_dir)
        self["key_red"] = Label("Cancel")
        self["key_green"] = Label("Play")
        self["key_yellow"] = Label("🌐 Network")
        self["key_blue"] = Label("📁 Folder")
        
        self["actions"] = ActionMap(["OkCancelActions", "WizardActions", "DirectionActions", "ColorActions"], {
            "ok": self.ok,
            "cancel": self.cancel,
            "red": self.cancel,
            "green": self.ok,
            "yellow": self.network,
            "blue": self.selectFolder,
            "up": self.up,
            "down": self.down,
            "pageUp": self["filelist"].pageUp,
            "pageDown": self["filelist"].pageDown,
        }, -1)
        self.onLayoutFinish.append(self.updateDir)
    
    def selectFolder(self):
        """Učitaj sve audio fajlove u trenutnom folderu"""
        current_dir = self["filelist"].getCurrentDirectory()
        
        if not os.path.isdir(current_dir):
            self.session.open(MessageBox, "This is not a folder!", MessageBox.TYPE_WARNING)
            return
        
        folder_name = os.path.basename(current_dir.rstrip('/'))
        self.session.openWithCallback(
            lambda result: self.createFolderPlaylist(result, current_dir, folder_name),
            MessageBox,
            f"Create playlist from ALL audio files?\n\n"
            f"Folder: {folder_name}\n"
            f"Files will be sorted by name.",
            MessageBox.TYPE_YESNO
        )

    def createFolderPlaylist(self, result, folder_path, folder_name):
        if not result:
            return

        audio_files = []
        supported_extensions = (".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg")

        print(f"[CiefpVibes] Scanning folder: {folder_path}")

        try:
            # Kolekcija za hijerarhijsko sortiranje
            folder_structure = {}  # folder -> lista fajlova

            for root, dirs, files in os.walk(folder_path):
                dirs[:] = [d for d in dirs if not d.startswith('.')]

                current_files = []
                for file in files:
                    file_lower = file.lower()
                    if any(file_lower.endswith(ext) for ext in supported_extensions):
                        full_path = os.path.join(root, file)
                        current_files.append((file, full_path))

                if current_files:
                    # Sortiraj fajlove u folderu po imenu
                    current_files.sort(key=lambda x: x[0].lower())

                    # Dodaj u strukturu
                    rel_path = os.path.relpath(root, folder_path)
                    if rel_path == ".":
                        rel_path = ""  # root folder

                    folder_structure[rel_path] = [f[1] for f in current_files]

            # Sada kreiraj playlistu sa hijerarhijom
            import hashlib
            import time

            timestamp = int(time.time())
            folder_hash = hashlib.md5(folder_path.encode()).hexdigest()[:8]
            temp_dir = "/tmp/ciefpvibes_folders"
            os.makedirs(temp_dir, exist_ok=True)

            temp_path = os.path.join(temp_dir, f"folder_{folder_hash}_{timestamp}.m3u")

            with open(temp_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")

                # Prvo root folder fajlovi
                if "" in folder_structure:
                    for audio_file in folder_structure[""]:
                        self.writeSongToM3U(f, audio_file, folder_path)

                # Onda ostali folderi sortirani po imenu
                sorted_folders = sorted([f for f in folder_structure.keys() if f != ""])

                for folder in sorted_folders:
                    # Dodaj separator za folder
                    folder_display = folder.replace("\\", "/")
                    if folder_display:
                        # Dodaj komentar za folder u M3U
                        f.write(f"# Folder: {folder_display}\n")

                    for audio_file in folder_structure[folder]:
                        self.writeSongToM3U(f, audio_file, folder_path)

            print(f"[CiefpVibes] Created hierarchical playlist")

            # Prebroji ukupno fajlova
            total_files = sum(len(files) for files in folder_structure.values())
            display_name = f"📁 {folder_name} ({total_files} songs)"
            self.close((temp_path, display_name))

        except Exception as e:
            print(f"[CiefpVibes] Error: {e}")
            self.session.open(MessageBox, f"Error:\n{str(e)[:100]}", MessageBox.TYPE_ERROR)

    def writeSongToM3U(self, file_handle, audio_file, base_folder):
        """Pomoćna funkcija za pisanje pesme u M3U"""
        filename = os.path.basename(audio_file)
        song_name = os.path.splitext(filename)[0]

        # Dodaj folder ime ako nije u root-u
        rel_path = os.path.relpath(os.path.dirname(audio_file), base_folder)
        if rel_path != ".":
            folder_name = os.path.basename(rel_path)
            song_name = f"[{folder_name}] {song_name}"

        song_name = song_name.replace("_", " ").replace("  ", " ")
        song_name = song_name.replace("-", " - ")
        song_name = song_name.replace(".", " ")

        file_handle.write(f"#EXTINF:-1,{song_name}\n")
        file_handle.write(f"{audio_file}\n")
    
    def createSingleM3U(self, audio_file):
        import hashlib
        import time
        
        try:
            timestamp = int(time.time())
            file_hash = hashlib.md5(audio_file.encode()).hexdigest()[:8]
            temp_dir = "/tmp/ciefpvibes_singles"
            os.makedirs(temp_dir, exist_ok=True)
            
            temp_path = os.path.join(temp_dir, f"single_{file_hash}_{timestamp}.m3u")
            
            filename = os.path.basename(audio_file)
            song_name = os.path.splitext(filename)[0]
            song_name = song_name.replace("_", " ").replace("-", " - ").strip()
            
            m3u_content = f"""#EXTM3U
#EXTINF:-1,{song_name}
{audio_file}
"""
            
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(m3u_content)
            
            return temp_path
            
        except Exception as e:
            print(f"[CiefpVibes] Error: {e}")
            return None
    
    def network(self):
        from Screens.ChoiceBox import ChoiceBox
        
        self.session.openWithCallback(
            self.networkActionSelected,
            ChoiceBox,
            title="🌐 Network Actions",
            list=[
                ("💻 Connect to Laptop", "laptop"),
                ("📡 Go to Network Folder", "network_folder"),
                ("🔌 Disconnect", "disconnect"),
                ("🏠 Back to Home", "home"),
            ]
        )
    
    def networkActionSelected(self, choice):
        if not choice:
            return
        
        if choice[1] == "laptop":
            self.close((None, "network"))
        elif choice[1] == "network_folder":
            if os.path.isdir("/media/network"):
                self["filelist"].changeDir("/media/network")
                self.updateDir()
        elif choice[1] == "disconnect":
            import subprocess
            try:
                subprocess.run(["umount", "-a", "-t", "cifs,nfs"], capture_output=True)
                self.session.open(MessageBox, "Network shares disconnected", MessageBox.TYPE_INFO)
            except:
                pass
        elif choice[1] == "home":
            self["filelist"].changeDir("/")
            self.updateDir()
    
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
                fn = os.path.basename(path).lower()
                
                audio_ext = (".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg")
                playlist_ext = (".tv", ".radio", ".m3u", ".m3u8")
                
                if any(fn.endswith(ext) for ext in playlist_ext):
                    self.close((path, os.path.basename(path)))
                elif any(fn.endswith(ext) for ext in audio_ext):
                    temp_m3u = self.createSingleM3U(path)
                    if temp_m3u:
                        display_name = os.path.splitext(os.path.basename(path))[0]
                        self.close((temp_m3u, display_name))
                    else:
                        self.session.open(MessageBox, f"Cannot play:\n{path}", MessageBox.TYPE_ERROR)
                else:
                    self.session.open(MessageBox, 
                                     f"Select music file or playlist!\n\n"
                                     f"Supported:\n.mp3 .flac .m4a .aac\n.tv .radio .m3u", 
                                     MessageBox.TYPE_WARNING)
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