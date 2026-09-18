# -*- coding: utf-8 -*-
import os
import re
from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from enigma import gFont, RT_HALIGN_LEFT, RT_VALIGN_CENTER, eTimer

# === MAPIRANJE NAMESPACE -> (SATELITSKA POZICIJA, IME SATELITA) ===
SAT_POSITION_MAP = {}


def load_satellite_positions():
    """
    Učitava satelitske pozicije iz /etc/enigma2/satellites.xml
    i gradi mapu namespace -> (pozicija, ime)
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

        # Izvuci sve satelite sa pozicijama i imenima
        sat_pattern = r'<sat\s+name="([^"]*)"\s+flags="\d+"\s+position="([-]?\d+)"'
        satellites = re.findall(sat_pattern, content)

        print(f"[CiefpSatelliteRadio] Loaded {len(satellites)} satellites from XML")

        known_namespace_map = {}

        for sat_name, position in satellites:
            pos_int = int(position)
            sat_name = sat_name.strip()  # Očisti ime

            if pos_int >= 0:  # Istočni satelit
                pos_value = pos_int
                ns_hex = f"{pos_value:04X}".upper()
                deg = pos_value / 10.0
                if deg % 1 == 0:
                    pos_str = f"{deg:.0f}°E"
                else:
                    pos_str = f"{deg:.1f}°E"
                known_namespace_map[ns_hex] = (pos_str, sat_name)
            else:  # Zapadni satelit
                pos_abs = abs(pos_int)
                pos_value = 3600 - pos_abs
                ns_hex = f"{pos_value:04X}".upper()
                deg = pos_abs / 10.0
                if deg % 1 == 0:
                    pos_str = f"{deg:.0f}°W"
                else:
                    pos_str = f"{deg:.1f}°W"
                known_namespace_map[ns_hex] = (pos_str, sat_name)

        SAT_POSITION_MAP = known_namespace_map
        print(f"[CiefpSatelliteRadio] Built position map with {len(SAT_POSITION_MAP)} entries")

    except Exception as e:
        print(f"[CiefpSatelliteRadio] Error loading satellites.xml: {e}")
        SAT_POSITION_MAP = {}


# Učitaj satelitske pozicije pri startu
load_satellite_positions()


def get_satellite_position_from_namespace(namespace):
    """
    Dohvata satelitsku poziciju i ime iz mape namespace -> (pozicija, ime)
    Vraća tuple: (pozicija_string, ime_satelita)
    """
    global SAT_POSITION_MAP
    if not namespace:
        return "Ostali Sateliti", "Nepoznat"

    ns_key = namespace[:4].upper()

    # SPECIJALNI SLUČAJEVI ZA DVB-T I DVB-C
    if ns_key.startswith("EEEE"):
        return "DVB-T/T2", "DVB-T/T2"
    if ns_key.startswith("FFFF"):
        return "DVB-C", "DVB-C"

    if ns_key in SAT_POSITION_MAP:
        return SAT_POSITION_MAP[ns_key]

    # Fallback ako nema u mapi
    try:
        ns_val = int(ns_key, 16)
        if ns_val < 0x708:  # Istočni
            deg = ns_val / 10.0
            if deg > 180:
                deg = 360 - deg
            return f"{deg:.1f}°E", f"Satelit {deg:.1f}°E"
        else:  # Zapadni
            deg = (3600 - ns_val) / 10.0
            return f"{deg:.1f}°W", f"Satelit {deg:.1f}°W"
    except:
        pass

    return "Ostali Sateliti", "Nepoznat"

def get_satellite_name_from_service_ref(service_ref):
    """
    Pomoćna funkcija koja iz service reference izvlači ime satelita.
    Koristi se u plugin.py.
    """
    if not service_ref or not isinstance(service_ref, str):
        return ""
    try:
        parts = service_ref.split(':')
        print(f"[CiefpSatelliteRadio-DEBUG] Parsing service_ref: {service_ref}, parts: {len(parts)}")
        if len(parts) >= 7:
            namespace = parts[6].upper().zfill(8)
            print(f"[CiefpSatelliteRadio-DEBUG] Namespace: {namespace}")
            _, sat_name = get_satellite_position_from_namespace(namespace)
            print(f"[CiefpSatelliteRadio-DEBUG] Satellite name: {sat_name}")
            return sat_name
    except Exception as e:
        print(f"[CiefpSatelliteRadio-DEBUG] Error: {e}")
    return ""

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
            sat_pos, sat_name = get_satellite_position_from_namespace(namespace)
            sat_key = (sat_pos, sat_name)  # Ključ je tuple

            # Enigma2 service reference za radio
            service_ref = "1:0:2:%s:%s:%s:%s:0:0:0:" % (sid, tid, nid, namespace)

            if sat_key not in satellites:
                satellites[sat_key] = []

            if not any(x[1] == service_ref for x in satellites[sat_key]):
                satellites[sat_key].append((station_name, service_ref))
                stations_count += 1
                print("[CiefpSatelliteRadio] %s -> %s (%s)" % (station_name, service_ref, sat_pos))

        print("[CiefpSatelliteRadio] Pronađeno %d radio stanica na %d satelita" % (stations_count, len(satellites)))

    except Exception as e:
        print("[CiefpSatelliteRadio] Greška: ", str(e))
        import traceback
        traceback.print_exc()

    return satellites

def get_dab_radio_from_bouquets():
    """
    Čita DAB+ radio stanice iz /etc/enigma2/userbouquet.*.radio fajlova.
    DAB+ linije imaju prefiks 4115:0:2:.

    Vraća: {"Buket Ime": [(station_name, service_ref), ...], ...}
    """
    bouquet_dir = "/etc/enigma2"
    dab_bouquets = {}

    if not os.path.exists(bouquet_dir):
        print("[CiefpDAB] /etc/enigma2 ne postoji")
        return dab_bouquets

    try:
        # Nađi sve userbouquet.*.radio fajlove
        for filename in os.listdir(bouquet_dir):
            if not filename.startswith("userbouquet.") or not filename.endswith(".radio"):
                continue

            filepath = os.path.join(bouquet_dir, filename)
            bouquet_name = filename  # default ako nema #NAME
            stations = []

            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()

                for i, line in enumerate(lines):
                    line = line.strip()

                    # Ime buketa
                    if line.startswith("#NAME"):
                        bouquet_name = line[5:].strip()
                        continue

                    # DAB+ servis
                    if line.startswith("#SERVICE 4115:"):
                        # Format: #SERVICE 4115:0:2:SID:TSID:ONID:NS:PARENT_SID:PARENT_TSID:UNUSED:URL:NAME
                        service_line = line[9:].strip()  # skini "#SERVICE "
                        parts = service_line.split(":")

                        if len(parts) < 11:
                            continue

                        # Ime stanice - iz DESCRIPTION linije (pouzdanije)
                        station_name = ""
                        if i + 1 < len(lines) and lines[i + 1].strip().startswith("#DESCRIPTION"):
                            station_name = lines[i + 1].strip()[13:].strip()

                        # Fallback: ime iz zadnjeg dela reference
                        if not station_name:
                            # URL može sadržati ":" pa spajamo sve do zadnjeg
                            # Poslednji deo posle zadnjeg ":" je ime
                            # npr. dab%3a//228.10.1.5%3a10010:1LIVE
                            rest = ":".join(parts[10:])
                            if ":" in rest:
                                station_name = rest.rsplit(":", 1)[-1]
                            else:
                                station_name = rest

                        station_name = station_name.strip()
                        if not station_name:
                            station_name = "Unknown DAB"

                        # NE diraj %3a — ostavi originalni service_ref iz buketa!
                        service_ref = service_line

                        stations.append((station_name, service_ref))

            except Exception as e:
                print("[CiefpDAB] Greška pri čitanju %s: %s" % (filename, str(e)))
                continue

            if stations:
                # Ako ime buketa nije lepo, uzmi iz fajla
                display_name = bouquet_name
                if display_name.startswith("userbouquet."):
                    display_name = display_name.replace("userbouquet.", "").replace(".radio", "")
                display_name = display_name.replace("_", " ").strip()

                dab_bouquets[display_name] = stations
                print("[CiefpDAB] Buket '%s': %d stanica" % (display_name, len(stations)))

        print("[CiefpDAB] Ukupno %d DAB+ buketa" % len(dab_bouquets))

    except Exception as e:
        print("[CiefpDAB] Greška: %s" % str(e))
        import traceback
        traceback.print_exc()

    return dab_bouquets


def is_dab_available():
    """Proverava da li na boxu postoje DAB+ buketi."""
    bouquet_dir = "/etc/enigma2"
    if not os.path.exists(bouquet_dir):
        return False
    try:
        for filename in os.listdir(bouquet_dir):
            if filename.startswith("userbouquet.") and filename.endswith(".radio"):
                filepath = os.path.join(bouquet_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if "4115:" in content:
                            return True
                except:
                    pass
    except:
        pass
    return False


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
            # sat_name je sada tuple (pozicija, ime)
            pos_str = sat_name[0]
            try:
                if '°E' in pos_str:
                    val = float(pos_str.replace('°E', '').strip())
                    return (0, val)
                elif '°W' in pos_str:
                    val = float(pos_str.replace('°W', '').strip())
                    return (1, val)
                else:
                    return (2, 0)
            except:
                return (3, 0)

        self.ui_list = []
        # sat_data je dict gde je ključ tuple (pozicija, ime), a vrednost lista stanica
        for sat_key in sorted(self.sat_data.keys(), key=sort_key):
            pos_str, sat_name = sat_key
            count = len(self.sat_data[sat_key])
            # Prikazujemo ime satelita i poziciju
            display_text = f"📡 {sat_name} ({pos_str}) - {count} radio stations"
            self.ui_list.append((display_text, sat_key))

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

        sat_key = current[1]  # Ovo je tuple (pozicija, ime)
        stations_list = self.sat_data[sat_key]

        self.close(stations_list)

    def closeError(self, answer=None):
        self.close(None)

    def closeCancel(self):
        self.close(None)

class CiefpDABRadioScreen(Screen):
    """Ekran za prikaz DAB+ buketa i stanica."""

    def buildSkin(self):
        return '''<?xml version="1.0" encoding="utf-8"?>
        <screen position="center,center" size="1920,1080" backgroundColor="#01053b">
            <widget name="separator0" position="0,0" size="1920,3" backgroundColor="#d5fa02" zPosition="1" />
            <eLabel position="0,0" size="1920,100" backgroundColor="#2e0130" zPosition="-1" />
            <eLabel text="..:: Ciefp DAB+ Radio (Bouquets) ::.." position="60,25" size="900,60" font="Regular;40" foregroundColor="#ffffff" backgroundColor="#2e0130" transparent="1" />
            <widget name="separator1" position="0,90" size="1920,3" backgroundColor="#d5fa02" zPosition="1" />

            <widget name="dab_image" position="900,100" size="1000,800" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/CiefpVibes/satellite.png" alphatest="on" zPosition="1"/>

            <widget name="title_label" position="500,950" size="850,40" font="Regular;28" foregroundColor="#ffcc00" transparent="1"/>

            <widget source="dab_list" render="Listbox" position="30,100" size="850,800" transparent="1" scrollbarMode="showOnDemand" zPosition="2">
                <convert type="TemplatedMultiContent">
                    {"template": [
                        MultiContentEntryText(pos=(20, 10), size=(800, 40), font=0, flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER, text=0)
                    ],
                    "fonts": [gFont("Regular", 30)],
                    "itemHeight": 50}
                </convert>
            </widget>
            <widget name="separator2" position="0,900" size="1920,3" backgroundColor="#d5fa02" zPosition="1" />

            <widget name="key_red" position="150,950" size="250,40" font="Regular;30" foregroundColor="#d5fa02" transparent="1"/>

            <eLabel position="0,900" size="1920,150" backgroundColor="#2e0130" zPosition="-1" />
        </screen>'''

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.skin = self.buildSkin()

        from Components.Pixmap import Pixmap
        self["dab_image"] = Pixmap()

        self["separator0"] = Label()
        self["separator1"] = Label()
        self["separator2"] = Label()
        self["title_label"] = Label("Učitavam DAB+ stanice...")
        self["key_red"] = Label("✖ Back")

        self.dab_data = {}
        self.ui_list = []
        self["dab_list"] = List([])

        self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
            "ok": self.selectBouquet,
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
        self.dab_data = get_dab_radio_from_bouquets()

        if not self.dab_data:
            self.error_timer.start(100, True)
            return

        self["title_label"].setText("Select a DAB+ bouquet:")

        self.ui_list = []
        for bouquet_name in sorted(self.dab_data.keys()):
            count = len(self.dab_data[bouquet_name])
            self.ui_list.append((f"📻 {bouquet_name} ({count} stations)", bouquet_name))

        self["dab_list"].setList(self.ui_list)

    def showErrorAndClose(self):
        self.session.openWithCallback(
            self.closeError,
            MessageBox,
            "Nema DAB+ buketa!\n\n"
            "DAB+ zahteva OpenATV 8.0 develop ili noviji.\n"
            "Proverite da li imate userbouquet.*.radio\n"
            "sa 4115: prefiksom u /etc/enigma2/.",
            MessageBox.TYPE_WARNING
        )

    def selectBouquet(self):
        current = self["dab_list"].getCurrent()
        if not current:
            return
        bouquet_key = current[1]
        stations_list = self.dab_data[bouquet_key]
        self.close(stations_list)

    def closeError(self, answer=None):
        self.close(None)

    def closeCancel(self):
        self.close(None)