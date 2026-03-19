# Session Log — 2026-03-18

## 1. Revert "keep radio playing when changing modes" + enhance radio display

**Request:** Review latest uncommitted changes. Revert the radio-keeps-playing-when-changing-modes behavior. Make the radio display more interesting — show now playing text and/or station image.

**Changes:**
- `app.py` — Added `radio_player.stop()` in `_set_mode()` when leaving radio mode
- `radio_player.py` — Added `metadata_changed` signal that fires on ICY stream metadata updates (song/program title)
- `app.py` — New `_on_radio_metadata()` updates marquee label with `Station Name • Now Playing` and shows now-playing info in the lyrics panel
- `app.py` — New `_set_radio_art()` renders a themed SVG placeholder (concentric signal rings, cell tower icon) using current theme colors

## 2. Fix radio playing breaking podcast saved position

**Request:** Playing a radio station causes the remembered last-listened podcast position to disappear. Radio needs more isolation from the shared player.

**Root cause:** `_on_station_selected` called `_save_podcast_position()` correctly, but then stopped playback (resetting `curr_pos` to 0). Since `player.current_track` still pointed to the podcast episode, later calls to `_save_podcast_position()` (e.g. at `closeEvent`) overwrote the saved position with 0.

**Fix:** After saving positions and stopping playback, `_on_station_selected` now sets `player.current_track`, `player.album`, and `player.playlist` to `None`. Both save functions guard on `current_track` being truthy, so they skip cleanly.

## 3. Documentation review and update

**Request:** Make a review of the application and update docs in `/docs`.

**Changes:**
- Updated 5 existing docs: `architecture.md`, `display-modes.md`, `keyboard-shortcuts.md`, `settings.md`, `themes.md`
- Added 2 new docs: `radio.md`, `podcasts.md`
- All docs now cover the three-mode system (music/podcast/radio), toolbar, new modules, and updated settings

## 4. Fix max mode for podcasts + text height

**Request:** Max mode doesn't display podcast HTML nicely. Text (lyrics/podcast) should take up 80% of screen height, centered with the image.

**Changes:**
- `app.py` — New `_copy_lyrics_to_max()` helper properly transfers synced lyrics, timestamped descriptions, or plain descriptions to the max mode widget (previously fell through to `set_lyrics` with raw HTML text)
- `app.py` — `_on_track_changed` now uses `set_description()` instead of `set_lyrics()` for podcast episodes
- `lyrics_widget.py` — `set_description()` now saves `_full_description` for later re-use
- `app.py` `resizeEvent` — Replaced art-pixel-aligned lyrics margins with 80% height / centered padding

## 5. Radio station image — user-driven art picker

**Request:** Add station images. Initially auto-fetched, then changed to let the user choose (similar to album art finder).

**Changes:**
- `radio_player.py` — Added `StationArtDialog` (iTunes podcast search with thumbnails, "Use" button)
- `radio_player.py` — Added `station_art_path()` for cache location, `_DownloadThread` for background fetch
- `radio_view.py` — Added `art_requested` signal and "Find Station Art..." context menu option
- `app.py` — Clicking album art in radio mode opens the picker (instead of max mode). Cached art loads automatically on station select, falls back to SVG placeholder.

## 6. Fix HTML showing in radio lyrics panel

**Request:** Seeing raw HTML tags in the radio now-playing lyrics panel.

**Root cause:** `_on_radio_metadata()` passed HTML markup to `set_description()`, which runs text through `html.escape()`, turning tags into visible `&lt;div&gt;` etc.

**Fix:** Set HTML directly on `lyrics_widget.label` with `setTextFormat(Qt.RichText)`, bypassing `set_description()`. Title and station name are properly escaped for safety.

## 7. Switch image search from iTunes to DuckDuckGo

**Request:** iTunes/Apple Podcast isn't great for radio station images. Use a general image search instead.

**Changes:**
- `radio_player.py` — Replaced `_SearchThread` iTunes podcast API with DuckDuckGo Images (fetches vqd token, queries `duckduckgo.com/i.js`, returns up to 12 results with thumbnails)
- Updated `StationArtDialog` result rendering: shows title + source domain instead of podcast name + artist
- Search defaults to `"<station name> radio logo"`, user can edit query

## 8. Crop station images to square

**Request:** Station images may not be square like album covers. Crop to square with aspect preserved.

**Changes:**
- `radio_player.py` — Added `_crop_square(img)` helper that center-crops a QImage to a square
- `_DownloadThread` now calls `_crop_square()` before saving

## 9. Show tracklist when switching albums

**Request:** Switching albums should toggle the tracklist panel on.

**Changes:**
- `app.py` — Connected `album_view.album_changed` signal to new `_show_tracklist()` method
- `_show_tracklist()` makes album view visible and checks the toggle button if it was hidden

## 10. Clear display when leaving radio mode

**Request:** When leaving radio mode, clear image/tracklist/lyrics. But only if radio was actually playing. Also reset progress bar and time labels.

**Changes (iterated):**
- First attempt restored previous album/podcast state — too complex, broke things
- Final version: only clears if radio was actually playing. Clears album art, track info, progress bar (set to 0), time labels (set to "0:00"), play icon, tracklist, and lyrics. If radio wasn't playing, nothing is touched.

## 11. Better podcast download handling

**Request:** Handle multiple podcast downloads more clearly to the user.

**Changes:**
- `app.py` — Replaced single `_download_thread` with `_download_threads` dict (keyed by episode GUID) supporting concurrent downloads
- Episode labels now show per-episode status: `○` (not downloaded), `⤓ 42%` (downloading), `●` (downloaded)
- Status label shows aggregate: "Downloading 3 episodes..."
- Added "Download" option to right-click context menu for non-downloaded episodes
- `_download_play_guid` tracks which episode to auto-play when done — others download silently

## 12. Cross-platform compatibility review

**Request:** Review and fix Linux-only dependencies before tackling cross-platform media key support.

**Issues found and fixed:**
- `requirements.txt` — Removed 6 Linux-only packages: `evdev`, `keyboard`, `pydbus`, `pynput`, `python-xlib`, `cffi`, `pycparser`, `six`
- `album.py:20` — Replaced hardcoded `path.split('/')` with `Path(path).parent`
- `podcast_feed.py` — Cache dir now platform-aware: `~/Library/Caches/lp/` on macOS, `%LOCALAPPDATA%\lp\cache\` on Windows, `~/.cache/lp/` on Linux
- `radio_player.py` — Same platform-aware cache dir pattern
