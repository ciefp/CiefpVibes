# CiefpVibes - Enigma2 Music Jukebox Plugin

![CiefpVibes Screenshot](https://github.com/ciefp/CiefpVibes/blob/main/welcome.jpg) <!-- Replace with actual image paths or links -->

## Overview

CiefpVibes is a versatile music jukebox plugin designed for Enigma2-based set-top boxes (e.g., Dreambox, Vu+, etc.). It allows users to play music playlists locally from files or online via GitHub-hosted repositories. Supporting .m3u, .m3u8, and .tv bouquet formats, it provides a seamless playback experience with features like repeat modes, shuffle, customizable skins, and network timeout configurations. Built with Python and integrated with Enigma2's service framework, it's ideal for turning your STB into a dedicated music player.

**Version:** 1.0  
**Author:** ciefp (or your name/handle)  
**License:** GPL-3.0 (or specify your license)  
**Compatible with:** Enigma2 images (tested on OpenPLi, OpenATV, etc.)  

## Features

- **Playlist Support:** Load and play .m3u/.m3u8 playlists and .tv bouquets containing audio streams.
- **Local & Online Playback:** Browse local files or fetch playlists directly from GitHub repositories (M3U and TV categories).
- **Playback Controls:** Repeat (off/one/all), shuffle, progress bar, elapsed/remaining time display.
- **Customization:** 5 backgrounds, 5 infobars, and 5 posters for a personalized UI. Configurable network timeout for online fetches.
- **Auto-Save & Reload:** Remembers the last loaded playlist and settings for quick resumption.
- **User-Friendly Interface:** Intuitive navigation with color-coded buttons (Red: Exit, Green: Folder, Yellow: Settings, Blue: Online Files).
- **GitHub Integration:** Fetch latest playlists from predefined repositories without manual downloads.
- **Error Handling:** Graceful handling of invalid files, network errors, and empty playlists.

## Installation

1. **Dependencies:** Ensure your Enigma2 image has Python 3.x, `urllib`, `json`, and Enigma2 core components installed (usually pre-installed).
2. **Download:** Clone or download the repository:
git clone https://github.com/yourusername/CiefpVibes.git
text3. **Install Plugin:**
- Copy the `CiefpVibes` folder to `/usr/lib/enigma2/python/Plugins/Extensions/`.
- Restart Enigma2 GUI: `init 4 && init 3` via telnet/SSH.
4. **Assets:** Ensure subfolders (`backgrounds/`, `infobars/`, `posters/`) contain the required PNG files (included in the repo).
5. **Configuration:** Settings are saved in `/etc/enigma2/ciefpvibes.cfg`. Last playlist in `/etc/enigma2/ciefpvibes_last.txt`.

## Usage

1. **Launch the Plugin:** Go to Plugins menu > CiefpVibes.
2. **Load Playlist:**
- **Local:** Press Green (Folder) to browse and select .m3u/.tv files.
- **Online:** Press Blue (Online Files) to choose M3U or TV categories from GitHub.
3. **Playback:**
- Navigate the playlist with Up/Down.
- Press OK to play selected track.
- Auto-advances to next track on EOF.
4. **Settings (Yellow Button):**
- Change backgrounds, posters, infobars.
- Set repeat/shuffle modes.
- Adjust network timeout or load custom URLs.
5. **Exit:** Press Red or Back.

## Screenshots

![Main Interface](https://github.com/ciefp/CiefpVibes/blob/main/main.jpg)  
![Main Interface](https://github.com/ciefp/CiefpVibes/blob/main/main2.jpg)  
![Playlist Selection](https://github.com/ciefp/CiefpVibes/blob/main/m3u_playlist.jpg)  

## Development & Contributions

- **Source Code:** Written in Python with Enigma2 APIs.
- **GitHub API Integration:** Fetches from `https://github.com/ciefp/CiefpVibesFiles` (M3U and TV folders).
- **Contributions:** Pull requests welcome! For issues, open a ticket.
- **Todo:** Add more skin options, volume controls, or search functionality.

## Troubleshooting

- **No Playlists Found:** Check GitHub repo for files or verify network connection.
- **Playback Issues:** Ensure streams are valid audio URLs (e.g., .mp3/.flac).
- **Missing Assets:** Verify PNG files in respective folders.
- **Errors:** Check console logs for details (e.g., via telnet).

If you encounter issues, feel free to report them in the Issues section.

## Credits

- Inspired by Enigma2 community plugins.
- Icons and assets: Custom-designed (or credit sources if applicable).

Enjoy your vibes with CiefpVibes! 🎶

