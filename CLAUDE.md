# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# Activate venv and run
source venv/bin/activate
python src/app.py
```

## Building

```bash
pip install -r requirements-build.txt
pyinstaller lp.spec
```

CI builds are triggered by pushing a `v*` tag or via workflow_dispatch. Builds run on Linux (ubuntu-22.04), macOS, and Windows using Python 3.12.

## Architecture

PyQt5 desktop music player ("lp") with a three-panel QSplitter layout:

**`app.py`** — QMainWindow orchestrator. Owns all top-level widgets, wires signals between them, manages theme/settings/shortcuts, and implements three display modes:
- Normal: folder_view | player | right_splitter(album_view + lyrics_widget)
- Miniplayer (`m`): compact window with art + controls, optional lyrics
- Max mode (`Shift+M`): fullscreen with large art + large lyrics

**Widget ownership**: App creates Player, AlbumView, LyricsWidget, FolderView and cross-wires them (e.g., `player.album_view = self.album_view`). This coupling is intentional — widgets reference each other directly rather than through signals for most interactions.

**`player.py`** — Playback controls and album art display. Uses `just_playback` library. Important: `just_playback` requires `play()` before `pause()`/`seek()` will work. Emits `track_changed` and `track_finished` signals. Has a 20ms QTimer for progress updates.

**`theme.py`** — LIGHT/DARK theme dicts with color tokens → QSS generator functions (`app_qss()`, `player_qss()`, etc.). Accent color is overridden at apply time by copying the theme dict and replacing accent/selection keys.

**`album.py`** — Parses a folder into a list of Track objects using mutagen for metadata and tinytag as fallback.

**`track.py`** — Plain data class for track metadata. All string fields are `str()`-converted in `__init__` to avoid mutagen lazy objects.

**`folder_view.py`** — Filesystem folder browser using QFileSystemModel. Filters to show only directories. Double-click loads a folder as an album in AlbumView. Has context menu for "Open folder" via platform file manager.

**`progress_bar.py`** — ClickableProgressBar with click-to-seek and drag-to-scrub. Emits `seek_requested` (during drag) and `start_playback` (on release) signals.

**`music_icon_provider.py`** — Custom QFileIconProvider that hides folder icons (returns transparent pixmap) to keep the folder tree visually clean.

**`lyrics_widget.py` / `lyrics_fetcher.py`** — Lyrics display with synced scrolling. Fetches from LRCLIB API, prefers synced `.lrc` format, caches in `album/lyrics/` directory.

**`artwork_finder.py`** — iTunes Search API for album art, saves as `cover.jpg`.

**`vim_views.py`** — VimTreeView/VimListWidget with `/` search and Enter-to-open (no h/j/k/l nav — removed in favor of global shortcuts).

**Settings**: `QSettings('lp', 'music-player')` persists theme, accent, font size, window geometry, splitter sizes, and library path.

## Keyboard Shortcuts

All global QShortcuts are suppressed when a QLineEdit has focus. Miniplayer/max mode disable some shortcuts to prevent conflicts.

| Key | Action |
|-----|--------|
| `p` | Play/Pause |
| `>` / `<` | Next / Previous track |
| `f` / `b` | Seek forward / back 5s |
| `.` / `,` | Volume up / down 5% |
| `1` | Toggle library panel |
| `2` | Toggle tracklist panel |
| `3` or `l` | Toggle lyrics panel |
| `m` | Toggle miniplayer |
| `Shift+M` | Toggle max mode |
| `q` | Quit |
| `?` | Show shortcuts dialog |

## Key Conventions

- No h/j/k/l vim navigation — global shortcuts should work everywhere without conflicting with text input
- Global QShortcuts are suppressed when a QLineEdit has focus
- Miniplayer/maxplayer modes reparent widgets and save/restore state
- Panel toggles use the `pressed` signal + `isVisible()` as source of truth
- All source files live in `src/` with flat structure (no subpackages)
- No test suite exists currently
- Dependencies: PyQt5 for GUI, just_playback for audio, mutagen/tinytag for metadata, requests for API calls
