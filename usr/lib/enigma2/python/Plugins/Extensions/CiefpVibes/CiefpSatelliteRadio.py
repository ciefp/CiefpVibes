# -*- coding: utf-8 -*-
import os
import re
from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from enigma import gFont, RT_HALIGN_LEFT, RT_VALIGN_CENTER, eTimer

# === MAPIRANJE NAMESPACE -> SATELITSKA POZICIJA ===
SAT_POSITION_MAP = {}

def load_satellite_positions():
    """
    Učitava satelitske pozicije iz /etc/enigma2/satellites.xml
    i gradi mapu namespace -> pozicija
    
    PREMA UPUTSTVU:
    - Za Istočne (E): position * 10 u hex
    - Za Zapadne (W): 3600 - (position * 10) u hex
    """
    global SAT_POSITION_MAP
    sat_xml_path = "/etc/enigma2/satellites.xml"

    if not os.path.exists(sat_xml_path):
        print("[CiefpSatelliteRadio] satellites.xml not found")
        SAT_POSITION_MAP = {}
        return

    try:
        with open(sat_xml_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        # Izvuci sve satelite sa pozicijama
        sat_pattern = r'<sat\s+name="([^"]*)"\s+flags="\d+"\s+position="([-]?\d+)"'
        satellites = re.findall(sat_pattern, content)
        
        print(f"[CiefpSatelliteRadio] Loaded {len(satellites)} satellites from XML")
        
        # Kreiraj mapu namespace -> pozicija
        known_namespace_map = {}
        
        for sat_name, position in satellites:
            pos_int = int(position)
            
            if pos_int >= 0:  # Istočni satelit
                # Formula: position * 10 u hex
                pos_value = pos_int
                ns_hex = f"{pos_value:04X}".upper()
                deg = pos_value / 10.0
                if deg % 1 == 0:
                    pos_str = f"{deg:.0f}°E"
                else:
                    pos_str = f"{deg:.1f}°E"
                known_namespace_map[ns_hex] = pos_str
            else:  # Zapadni satelit
                # Formula: 3600 - (abs(position) * 10) u hex
                pos_abs = abs(pos_int)
                pos_value = 3600 - pos_abs
                ns_hex = f"{pos_value:04X}".upper()
                deg = pos_abs / 10.0
                if deg % 1 == 0:
                    pos_str = f"{deg:.0f}°W"
                else:
                    pos_str = f"{deg:.1f}°W"
                known_namespace_map[ns_hex] = pos_str
        
        SAT_POSITION_MAP = known_namespace_map
        print(f"[CiefpSatelliteRadio] Built position map with {len(SAT_POSITION_MAP)} entries")
        
        # Debug: ispiši neke primere
        for ns, pos in list(SAT_POSITION_MAP.items())[:10]:
            print(f"  {ns} -> {pos}")
        
    except Exception as e:
        print(f"[CiefpSatelliteRadio] Error loading satellites.xml: {e}")
        SAT_POSITION_MAP = {}

# Učitaj satelitske pozicije pri startu
load_satellite_positions()


def get_satellite_position_from_namespace(namespace):
    """
    Dohvata satelitsku poziciju iz mape namespace -> pozicija
    """
    global SAT_POSITION_MAP
    if not namespace:
        return "Ostali Sateliti"

    # Uzmi prva 4 karaktera (prva 2 bajta) kao ključ
    ns_key = namespace[:4].upper()

    # SPECIJALNI SLUČAJEVI ZA DVB-T I DVB-C
    if ns_key.startswith("EEEE"):
        return "DVB-T/T2"
    if ns_key.startswith("FFFF"):
        return "DVB-C"

    # Pokušaj direktno mapiranje
    if ns_key in SAT_POSITION_MAP:
        return SAT_POSITION_MAP[ns_key]

    # Pokušaj sa heks konverzijom
    try:
        ns_val = int(ns_key, 16)

        if ns_val < 0x708:  # Istočni satelit (< 1800 dec)
            deg = ns_val / 10.0
            if deg > 180:
                deg = 360 - deg
            return f"{deg:.1f}°E".replace(".0°E", "°E")
        else:  # Zapadni satelit (> 1800 dec)
            deg = (3600 - ns_val) / 10.0
            return f"{deg:.1f}°W".replace(".0°W", "°W")
    except:
        pass

    return "Ostali Sateliti"

def get_satellite_radio_from_lamedb():
    """
    Čita radio kanale iz /etc/enigma2/lamedb
    
    PREMA UPUTSTVU, format servisa je:
    sid:namespace:tid:nid:service_type:source_id
    
    TYPE=2 označava radio.
    """
    lamedb_path = "/etc/enigma2/lamedb"
    satellites = {}
    stations_count = 0
    
    if not os.path.exists(lamedb_path):
        print("[CiefpSatelliteRadio] lamedb ne postoji: ", lamedb_path)
        return satellites

    try:
        with open(lamedb_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        total_lines = len(lines)

        for i in range(total_lines - 2):
            line = lines[i].strip()

            if line.count(":") < 5:
                continue

            parts = line.split(":")
            if len(parts) < 6:
                continue

            # ISPRAVLJENO PARSIRANJE PREMA UPUTSTVU:
            # sid:namespace:tid:nid:service_type:source_id
            sid = parts[0].upper()
            namespace = parts[1].upper().zfill(8)  # NAMESPACE JE NA POZICIJI 1!
            tid = parts[2].upper()
            nid = parts[3].upper()
            srv_type = parts[4]

            # SAMO radio tipovi: 2 ili A (10)
            if srv_type != "2" and srv_type.upper() != "A" and srv_type != "10":
                continue

            station_name = lines[i + 1].strip()
            if not station_name or station_name.startswith("#"):
                continue

            # Odredi satelit iz namespace-a
            sat_pos = get_satellite_position_from_namespace(namespace)
            
            # Enigma2 service reference za radio
            service_ref = "1:0:2:%s:%s:%s:%s:0:0:0:" % (sid, tid, nid, namespace)
            
            if sat_pos not in satellites:
                satellites[sat_pos] = []
                
            if not any(x[1] == service_ref for x in satellites[sat_pos]):
                satellites[sat_pos].append((station_name, service_ref))
                stations_count += 1
                print("[CiefpSatelliteRadio] %s -> %s (%s)" % (station_name, service_ref, sat_pos))

        print("[CiefpSatelliteRadio] Pronađeno %d radio stanica na %d satelita" % (stations_count, len(satellites)))

    except Exception as e:
        print("[CiefpSatelliteRadio] Greška: ", str(e))
        import traceback
        traceback.print_exc()

    return satellites


class CiefpSatelliteRadioScreen(Screen):
    """Ekran za prikaz satelita i vraćanje selektovanih kanala u CiefpVibes"""

    def buildSkin(self):
        return '''<?xml version="1.0" encoding="utf-8"?>
        <screen position="center,center" size="1920,1080"  backgroundColor="#01053b">
            <widget name="separator0" position="0,0" size="1920,3" backgroundColor="#d5fa02" zPosition="1" /> 
            <eLabel position="0,0" size="1920,100" backgroundColor="#2e0130" zPosition="-1" />
            <eLabel text="..:: Ciefp Satellite Radio (lamedb) ::.." position="60,25" size="800,60" font="Regular;40" foregroundColor="#ffffff" backgroundColor="#2e0130" transparent="1" />
            <widget name="separator1" position="0,90" size="1920,3" backgroundColor="#d5fa02" zPosition="1" />  
            <!-- SLIKA NA DESNOJ STRANI -->
            <widget name="sat_image" position="900,100" size="1000,800" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/CiefpVibes/satellite.png" alphatest="on" zPosition="1"/>

            <!-- NASLOV -->
            <widget name="title_label" position="500,950" size="850,40" font="Regular;28" foregroundColor="#ffcc00" transparent="1"/>

            <!-- LISTA SATELITA -->
            <widget source="sat_list" render="Listbox" position="30,100" size="850,800" transparent="1" scrollbarMode="showOnDemand" zPosition="2">
                <convert type="TemplatedMultiContent">
                    {"template": [
                        MultiContentEntryText(pos=(20, 10), size=(800, 40), font=0, flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER, text=0)
                    ],
                    "fonts": [gFont("Regular", 30)],
                    "itemHeight": 50}
                </convert>
            </widget>
            <widget name="separator2" position="0,900" size="1920,3" backgroundColor="#d5fa02" zPosition="1" /> 
            <!-- BACK DUGME -->
            <widget name="key_red" position="150,950" size="250,40" font="Regular;30" foregroundColor="#d5fa02" transparent="1"/>

            <eLabel position="0,900" size="1920,150" backgroundColor="#2e0130" zPosition="-1" />
        </screen>'''

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.skin = self.buildSkin()

        # Dodaj widget za sliku
        from Components.Pixmap import Pixmap
        self["sat_image"] = Pixmap()

        # Separatori
        self["separator0"] = Label()
        self["separator1"] = Label()
        self["separator2"] = Label()
        self["separator3"] = Label()
        self["title_label"] = Label("Učitavam satelitske radio stanice...")
        self["key_red"] = Label("✖ Back")

        self.sat_data = {}
        self.ui_list = []
        self["sat_list"] = List([])

        self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
            "ok": self.selectSatellite,
            "cancel": self.closeCancel,
            "red": self.closeCancel
        }, -1)

        self.error_timer = eTimer()
        try:
            self.error_timer_conn = self.error_timer.timeout.connect(self.showErrorAndClose)
        except:
            self.error_timer.callback.append(self.showErrorAndClose)

        self.onLayoutFinish.append(self.parseAndLoad)

    def parseAndLoad(self):
        """Pokreće parser i osvežava listu na ekranu"""
        self.sat_data = get_satellite_radio_from_lamedb()
        
        if not self.sat_data:
            self.error_timer.start(100, True)
            return

        self["title_label"].setText("Select a satellite to view radio stations:")
        
        # Sortiranje satelita: prvo istočni (E), pa zapadni (W)
        def sort_key(sat_name):
            try:
                if '°E' in sat_name:
                    val = float(sat_name.replace('°E', '').strip())
                    return (0, val)
                elif '°W' in sat_name:
                    val = float(sat_name.replace('°W', '').strip())
                    return (1, val)
                else:
                    return (2, 0)
            except:
                return (3, 0)
        
        self.ui_list = []
        for sat in sorted(self.sat_data.keys(), key=sort_key):
            count = len(self.sat_data[sat])
            self.ui_list.append((f"📡 Satellite {sat} ({count} radio stations)", sat))
            
        self["sat_list"].setList(self.ui_list)

    def showErrorAndClose(self):
        self.session.openWithCallback(
            self.closeError,
            MessageBox, 
            "Greška: U lamedb bazi nije pronađen nijedan kanal sa oznakom satelitskog radija (tip 2)!", 
            MessageBox.TYPE_WARNING
        )

    def selectSatellite(self):
        current = self["sat_list"].getCurrent()
        if not current:
            return
            
        sat_key = current[1]
        stations_list = self.sat_data[sat_key]
        
        self.close(stations_list)

    def closeError(self, answer=None):
        self.close(None)

    def closeCancel(self):
        self.close(None)