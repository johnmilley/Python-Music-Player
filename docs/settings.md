# Settings & User Data

lp uses Qt's built-in `QSettings` to persist user preferences. On Linux this writes an INI file at `~/.config/lp/music-player.conf`. On macOS it uses a plist, and on Windows the registry.

## What's saved

### Core settings

| Key | Type | What it stores |
|-----|------|----------------|
| `library_root` | string | Path to the music library folder |
| `geometry` | bytes | Window position and size |
| `splitter` | bytes | Main splitter panel proportions |
| `right_splitter` | bytes | Right splitter (tracklist/lyrics) proportions |
| `dark_mode` | `"true"` / `"false"` | Whether dark theme is active |
| `font_size` | int | Font size in points |
| `font_family` | string | Font name (e.g. `Consolas`) |
| `accent_color` | string | User-chosen accent color (hex or name) |
| `album_accents` | dict | Per-album accent colors, keyed by album path |
| `accent_match` | bool | Whether automatic album accent extraction is enabled |
| `lyrics_visible` | `"true"` / `"false"` | Whether lyrics panel was showing |
| `last_album` | string | Path to the last loaded album folder |
| `last_track_pos` | int | Track index in the last album's tracklist |
| `last_seek_pos` | float | Playback position in seconds |
| `mode` | string | Last active mode (`music`, `podcast`, or `radio`) |

### Podcast settings

| Key | Type | What it stores |
|-----|------|----------------|
| `podcast/feeds` | list | URLs of subscribed podcast feeds |
| `podcast/last_feed` | string | URL of the last-played podcast feed |
| `podcast/last_episode` | int | Episode index in the last-played feed |
| `podcast/last_seek` | float | Playback position in last episode |
| `podcast/episode_positions` | dict | Per-episode seek positions, keyed by GUID |

### Radio settings

| Key | Type | What it stores |
|-----|------|----------------|
| `radio/station_names` | list | Names of saved radio stations |
| `radio/station_urls` | list | Stream URLs (parallel to names) |
| `radio/last_station_url` | string | URL of last-played station |
| `radio/last_station_name` | string | Name of last-played station |

## When it saves

All settings are written in `closeEvent()` (`app.py`), so everything persists when you close the window normally. Some settings are saved incrementally:
- `library_root` — written immediately when picking a new library folder
- `podcast/feeds` — written when adding/removing feeds
- `radio/station_names` and `radio/station_urls` — written when adding/removing stations
- `podcast/episode_positions` — written when saving podcast playback position

## When it loads

On startup, `_restore_state()` reads all saved values and restores the window layout, theme, font, active mode, and last-played content. If a last album/podcast/radio station is found, it loads the appropriate content and (for music/podcasts) seeks to the saved position.

## Other persistent data

Beyond QSettings, lp also writes to disk:

- **Lyrics**: cached as `.lrc` (synced) or `.txt` (plain) files in each album's `lyrics/` subdirectory (e.g. `~/Music/Artist/Album/lyrics/01_Song.lrc`)
- **Artwork**: saved as `cover.jpg` in the album folder when downloaded via the artwork finder
- **Podcast episodes**: downloaded to `~/.cache/lp/podcasts/` with MD5-hashed filenames from episode GUIDs
