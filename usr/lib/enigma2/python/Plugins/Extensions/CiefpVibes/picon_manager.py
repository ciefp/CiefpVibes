from enigma import eServiceReference, eTimer
from Tools.Directories import fileExists
from Tools.LoadPixmap import LoadPixmap
import os
import re
import shutil

class PiconManager:
    """Klasa za upravljanje piconima sa podrškom za podfoldere i default pikon"""

    def __init__(self, picon_path="/media/usb/picon/", default_picon_path=None):
        self.picon_path = picon_path
        self.base_path = self.get_base_path(picon_path)

        if default_picon_path and os.path.isfile(default_picon_path):
            self.default_picon = default_picon_path
            print(f"[PiconManager] Default picon OK: {default_picon_path}")
        else:
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            self.default_picon = os.path.join(plugin_dir, "picon_default.png")
            print(
                f"[PiconManager] Default picon fallback: {self.default_picon} (exists={os.path.isfile(self.default_picon)})")

        print(f"[PiconManager] Default picon final: {self.default_picon}, exists={os.path.isfile(self.default_picon)}")

        self.cache = {}
        self.search_dirs = []
        self.picon_name_cache = {}  # Cache za imena picona
        self.build_search_dirs()

    def get_default_picon(self):
        """Vraća putanju do default pikona ako postoji"""
        if os.path.isfile(self.default_picon):
            return self.default_picon
        return None

    def get_base_path(self, path):
        """Dohvati osnovni direktorijum"""
        if path.endswith('/picon/') or path.endswith('/picons/'):
            return path
        
        current = path.rstrip('/')
        while current and not current.endswith('/picon') and not current.endswith('/picons'):
            current = os.path.dirname(current)
            if current == '/' or current == '':
                break
        
        if current and (current.endswith('/picon') or current.endswith('/picons')):
            return current + '/'
        
        return path
    
    def build_search_dirs(self):
        """Izgradi listu direktorijuma za pretragu"""
        self.search_dirs = []
        self.picon_name_cache = {}  # Očisti cache
        
        # Uvijek dodaj /picon/ kao primarni direktorijum
        primary_paths = [
            "/picon/",
            self.picon_path,
        ]
        
        for path in primary_paths:
            if os.path.exists(path) and path not in self.search_dirs:
                self.search_dirs.append(path)
                self._index_picons_in_directory(path)
        
        # Dodaj sve podfoldere iz /picon/
        if os.path.exists("/picon/"):
            try:
                for root, dirs, files in os.walk("/picon/"):
                    has_png = any(f.lower().endswith('.png') for f in files)
                    if has_png and root + '/' not in self.search_dirs:
                        self.search_dirs.append(root + '/')
                        self._index_picons_in_directory(root + '/')
            except Exception as e:
                print(f"Error walking /picon/: {e}")
        
        # Dodaj sve podfoldere iz media putanja
        if os.path.exists(self.picon_path):
            try:
                for root, dirs, files in os.walk(self.picon_path):
                    has_png = any(f.lower().endswith('.png') for f in files)
                    if has_png and root + '/' not in self.search_dirs:
                        self.search_dirs.append(root + '/')
                        self._index_picons_in_directory(root + '/')
            except Exception as e:
                print(f"Error walking {self.picon_path}: {e}")
        
        # Dodaj default putanje
        default_paths = [
            "/media/usb/picon/",
            "/media/hdd/picon/",
            "/usr/share/enigma2/picon/",
        ]
        for path in default_paths:
            if os.path.exists(path) and path not in self.search_dirs:
                self.search_dirs.append(path)
                self._index_picons_in_directory(path)
        
        # Ukloni duplikate
        self.search_dirs = list(dict.fromkeys(self.search_dirs))
        print(f"Search dirs: {self.search_dirs}")
        print(f"Picon name cache has {len(self.picon_name_cache)} entries")
    
    def _index_picons_in_directory(self, directory):
        """Indeksiraj sve pikone u direktorijumu"""
        if not os.path.exists(directory):
            return
        
        try:
            for file in os.listdir(directory):
                if file.lower().endswith('.png'):
                    name_without_ext = file[:-4]
                    full_path = os.path.join(directory, file)
                    
                    self.picon_name_cache[name_without_ext] = full_path
                    self.picon_name_cache[name_without_ext.lower()] = full_path
                    
                    name_with_colon = name_without_ext.replace('_', ':')
                    self.picon_name_cache[name_with_colon] = full_path
                    self.picon_name_cache[name_with_colon.lower()] = full_path
                    
                    name_with_underscore = name_without_ext.replace(':', '_')
                    self.picon_name_cache[name_with_underscore] = full_path
                    self.picon_name_cache[name_with_underscore.lower()] = full_path
                    
                    if name_without_ext.startswith('p:') or name_without_ext.startswith('c:'):
                        without_prefix = name_without_ext[2:]
                        self.picon_name_cache[without_prefix] = full_path
                        self.picon_name_cache[without_prefix.lower()] = full_path
                        
                        without_prefix_colon = without_prefix.replace('_', ':')
                        self.picon_name_cache[without_prefix_colon] = full_path
                        self.picon_name_cache[without_prefix_colon.lower()] = full_path
                        
                        without_prefix_underscore = without_prefix.replace(':', '_')
                        self.picon_name_cache[without_prefix_underscore] = full_path
                        self.picon_name_cache[without_prefix_underscore.lower()] = full_path
        except Exception as e:
            print(f"Error indexing picons in {directory}: {e}")
    
    def set_picon_path(self, path):
        """Postavi putanju do picona"""
        if os.path.exists(path):
            self.picon_path = path
            self.base_path = self.get_base_path(path)
            self.cache.clear()
            self.picon_name_cache.clear()
            self.build_search_dirs()
            return True
        return False
    
    def is_marker(self, service_ref):
        """Provjeri da li je service_ref marker (1:64)"""
        ref_clean = service_ref.replace("#SERVICE", "").strip()
        parts = ref_clean.split(":")
        if len(parts) >= 2 and parts[1] == "64":
            return True
        return False
    
    def clean_service_ref(self, service_ref):
        """Očisti service referencu i ukloni višak : na kraju"""
        ref_clean = service_ref.replace("#SERVICE", "").strip()
        while ref_clean.endswith(':'):
            ref_clean = ref_clean[:-1]
        return ref_clean
    
    def find_picon(self, service_ref, channel_name=None, return_default=True):
        """Pronađi picon za service referencu ili ime kanala. Ako ne nađe, vraća default pikon ako je return_default=True."""
        if self.is_marker(service_ref):
            return self.get_default_picon() if return_default else None
        
        ref_clean = self.clean_service_ref(service_ref)
        cache_key = ref_clean + (channel_name or "")
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        possible_names = self.generate_picon_names(ref_clean)
        result = None
        
        for picon_dir in self.search_dirs:
            if not os.path.exists(picon_dir):
                continue
            
            for name in possible_names:
                picon_file = os.path.join(picon_dir, name)
                if fileExists(picon_file):
                    result = picon_file
                    break
                
                picon_file = os.path.join(picon_dir, name.lower())
                if fileExists(picon_file):
                    result = picon_file
                    break
            
            if result:
                break
        
        if not result and channel_name:
            clean_name = channel_name
            for suffix in [" (IPTV)", " (StreamRelay)", " (HD)", " (SD)"]:
                if clean_name.endswith(suffix):
                    clean_name = clean_name[:-len(suffix)]
            
            clean_name_lower = clean_name.lower()
            search_names = [
                clean_name_lower,
                clean_name_lower.replace(' ', ''),
                clean_name_lower.replace(' ', '_'),
                clean_name_lower.replace(' ', '-'),
                clean_name_lower.replace('&', 'and'),
                clean_name_lower.replace('+', 'plus'),
                clean_name_lower.replace('.', ''),
                clean_name_lower.replace("'", ''),
            ]
            
            for name in search_names:
                if name in self.picon_name_cache:
                    result = self.picon_name_cache[name]
                    break
                
                for prefix in ['p:', 'c:', '']:
                    test_name = prefix + name
                    if test_name in self.picon_name_cache:
                        result = self.picon_name_cache[test_name]
                        break
                if result:
                    break
            
            if not result:
                for cache_name, path in self.picon_name_cache.items():
                    if clean_name_lower in cache_name or cache_name in clean_name_lower:
                        result = path
                        break

        # Ako picon NIJE pronađen, uradi fallback na default pikon
        final_picon = result if result else (self.get_default_picon() if return_default else None)
        
        self.cache[cache_key] = final_picon
        return final_picon

    def generate_picon_names(self, service_ref):
        """Generiraj moguće nazive picon fajlova"""
        names = []
        ref_clean = service_ref
        while ref_clean.endswith(':'):
            ref_clean = ref_clean[:-1]
        
        parts = ref_clean.split(":")
        if len(parts) >= 2 and parts[1] == "64":
            return names
        
        names.append(ref_clean.replace(":", "_") + ".png")
        
        if len(parts) >= 10:
            names.append("_".join(parts) + ".png")
            names.append("_".join(parts[:-3]) + ".png")
            if len(parts) >= 7:
                names.append("_".join(parts[:6]) + ".png")
                names.append("_".join(parts[2:7]) + ".png")
            if len(parts) >= 6:
                names.append("_".join(parts[3:6]) + ".png")
        
        if len(parts) >= 6:
            try:
                sid, tsid, onid = parts[3], parts[4], parts[5]
                sid_4 = f"{int(sid, 16):04x}" if sid else sid
                tsid_4 = f"{int(tsid, 16):04x}" if tsid else tsid
                onid_4 = f"{int(onid, 16):04x}" if onid else onid
                
                names.append("_".join([sid_4, tsid_4, onid_4]) + ".png")
                if len(parts) >= 7:
                    satfreq = parts[6]
                    names.append("_".join(parts[:3] + [sid_4, tsid_4, onid_4, satfreq]) + ".png")
            except:
                pass
        
        if parts[0] == "1":
            for name in names[:]:
                names.append("p:" + name)
                names.append("c:" + name)
        
        names.extend([name.lower() for name in names])
        
        for name in names[:]:
            if "_" in name:
                names.append(name.replace("_", ":"))
            if ":" in name:
                names.append(name.replace(":", "_"))
        
        if len(parts) >= 3 and parts[2].isdigit():
            alt_parts = parts[:]
            alt_parts[2] = "1"
            names.append("_".join(alt_parts) + ".png")
            if len(parts) >= 7:
                names.append("_".join(alt_parts[:7]) + ".png")
        
        unique_names = []
        for name in names:
            if name and name.endswith('.png'):
                base = name[:-4]
                while base.endswith('_'):
                    base = base[:-1]
                clean_name = base + '.png'
                if clean_name not in unique_names:
                    unique_names.append(clean_name)
            elif name and name not in unique_names:
                unique_names.append(name)
        
        return unique_names
    
    def get_picon_pixmap(self, service_ref, channel_name=None):
        """Dohvati picon kao pixmap (uključujući i default pikon ako nema pravog)"""
        if self.is_marker(service_ref):
            default_path = self.get_default_picon()
            return LoadPixmap(default_path) if default_path else None
        
        picon_file = self.find_picon(service_ref, channel_name, return_default=True)
        if picon_file and fileExists(picon_file):
            return LoadPixmap(picon_file)
        return None

    def assign_picon(self, service_ref, source_file):
        """Dodijeli picon kanalu - kopira u /picon/ i ostavlja original"""
        if self.is_marker(service_ref):
            return False
        
        try:
            ref_clean = self.clean_service_ref(service_ref)
            picon_name = ref_clean.replace(":", "_") + ".png"
            primary_target = os.path.join("/picon/", picon_name)
            
            if not os.path.exists("/picon/"):
                try:
                    os.makedirs("/picon/")
                except:
                    pass
            
            try:
                shutil.copy2(source_file, primary_target)
                print(f"[PiconManager] Copied to /picon/: {primary_target}")
            except Exception as e:
                print(f"[PiconManager] Error copying to /picon/: {e}")
            
            media_target = os.path.join(self.picon_path, picon_name)
            try:
                shutil.copy2(source_file, media_target)
                print(f"[PiconManager] Copied to media: {media_target}")
            except Exception as e:
                print(f"[PiconManager] Error copying to media: {e}")
            
            self.cache[ref_clean] = primary_target
            self.build_search_dirs()
            return True
        except Exception as e:
            print(f"Error assigning picon: {e}")
            return False

    def delete_picon(self, service_ref):
        """Obriši picon za kanal - briše iz svih lokacija"""
        if self.is_marker(service_ref):
            return False
        
        ref_clean = self.clean_service_ref(service_ref)
        picon_name = ref_clean.replace(":", "_") + ".png"
        deleted = False
        
        primary_file = os.path.join("/picon/", picon_name)
        if fileExists(primary_file):
            try:
                os.remove(primary_file)
                deleted = True
                print(f"[PiconManager] Deleted from /picon/: {primary_file}")
            except Exception as e:
                print(f"[PiconManager] Error deleting from /picon/: {e}")
        
        media_file = os.path.join(self.picon_path, picon_name)
        if fileExists(media_file):
            try:
                os.remove(media_file)
                deleted = True
                print(f"[PiconManager] Deleted from media: {media_file}")
            except Exception as e:
                print(f"[PiconManager] Error deleting from media: {e}")
        
        for picon_dir in self.search_dirs:
            if picon_dir not in ["/picon/", self.picon_path]:
                picon_file = os.path.join(picon_dir, picon_name)
                if fileExists(picon_file):
                    try:
                        os.remove(picon_file)
                        deleted = True
                        print(f"[PiconManager] Deleted from {picon_dir}")
                    except Exception as e:
                        print(f"[PiconManager] Error deleting from {picon_dir}: {e}")
        
        self.cache[ref_clean] = None
        self.build_search_dirs()
        return deleted
    
    def get_picons_from_selected_folder(self):
        """Dohvati samo pikone iz selektiranog foldera"""
        picon_files = []
        if not os.path.exists(self.picon_path):
            return picon_files
        
        try:
            for file in os.listdir(self.picon_path):
                if file.lower().endswith('.png'):
                    full_path = os.path.join(self.picon_path, file)
                    if os.path.isfile(full_path):
                        display_name = file.replace('.png', '').replace('_', ':')
                        if len(display_name) > 40:
                            display_name = display_name[:37] + "..."
                        picon_files.append((display_name, full_path, file))
            
            picon_files.sort(key=lambda x: x[0])
        except Exception as e:
            print(f"Error getting picons from selected folder: {e}")
        
        return picon_files
    
    def get_all_picons(self):
        """Dohvati sve pikone iz svih direktorijuma"""
        picon_files = []
        for picon_dir in self.search_dirs:
            if not os.path.exists(picon_dir):
                continue
            
            try:
                for file in os.listdir(picon_dir):
                    if file.lower().endswith('.png'):
                        full_path = os.path.join(picon_dir, file)
                        if os.path.isfile(full_path):
                            display_name = file.replace('.png', '').replace('_', ':')
                            if len(display_name) > 40:
                                display_name = display_name[:37] + "..."
                            dir_name = os.path.basename(picon_dir.rstrip('/'))
                            if dir_name and dir_name not in ["picon", "picons", "media", "usb", "hdd"]:
                                display_name = f"[{dir_name}] {display_name}"
                            picon_files.append((display_name, full_path, file))
            except Exception as e:
                print(f"Error getting picons from {picon_dir}: {e}")
        
        seen = set()
        unique_picons = []
        for p in picon_files:
            if p[2] not in seen:
                seen.add(p[2])
                unique_picons.append(p)
        
        unique_picons.sort(key=lambda x: x[0])
        return unique_picons