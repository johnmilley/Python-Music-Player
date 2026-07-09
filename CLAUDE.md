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
pip install -r requirements.txt
pyinstaller lp.spec
```

CI builds are triggered by pushing a `v*` tag or via workflow_dispatch. Builds run on Linux (ubuntu-22.04), macOS, and Windows using Python 3.12.

## Architecture

PyQt5 desktop music player ("lp") with a nested-splitter layout:

```
root_stack (QStackedWidget, central widget)
├── normal page: toolbar / main_splitter
│     main_splitter (H): left_stack | player | right_splitter
│       left_stack (QStackedWidget): folder_view | podcast_view | radio_view
│       right_splitter (V): album_view / lyrics_widget
└── max page: MaxView (large art + borrowed lyrics widget)

MiniView (separate always-on-top window, toggled with `m`): square album
art + hover controls, optionally the borrowed lyrics widget beside it.
```

**`app.py`** — QMainWindow orchestrator. Owns all top-level widgets, wires signals between them, manages theme/settings/shortcuts, and the three app modes (music/podcast/radio — the left stack swaps views, the splitters never see mode changes).

**`panel_manager.py`** — `PanelManager` is the single source of truth for panel visibility ('library', 'tracklist', 'lyrics') and remembered splitter sizes. Hiding a panel records its extent; showing it restores that extent while shrinking siblings proportionally, so toggles round-trip exactly. Splitter drags update the remembered sizes live. The whole right column collapses when both its panes are hidden. Toolbar buttons mirror its `visibility_changed` signal (they hold no state). Each app mode remembers its own tracklist/lyrics visibility: `snapshot(mode)` on leaving a mode, `apply_mode(mode)` on entering (first visit gets `MODE_DEFAULTS`: podcast opens the tracklist, radio opens neither; music keeps the session state). `save()/load()` persist to QSettings (`layout/main_splitter`, `layout/right_splitter`, `layout/panel_sizes`, `layout/mode_panels`, `*_visible`). `locked = True` during max and mini mode.

**`max_view.py`** — Max mode (`Shift+M`) page. Lives permanently on the root stack; listens to `player.art_changed`/`track_changed`, and *borrows* the app's single LyricsWidget by reparenting it in on enter and back to `right_splitter` index 1 on exit. No widget duplication, no settle timers; the normal page is untouched behind the stack.

**`mini_view.py`** — Mini mode (`m`): a separate frameless, always-on-top window of just the album art. The window stays square (resizeEvent follows the dragged edge); resizing reuses `WindowGrips`, dragging the art moves the window, double-click/Esc/`m` exits. Playback controls float over the art in a translucent bar shown only on hover, hidden immediately on leave or window deactivate, and *also* auto-hidden after `IDLE_HIDE_MS` (2.5s) of no mouse movement even while still hovering — done via a QApplication-wide `MouseMove` event filter (child widgets swallow mouse-move before it would ever reach the window's own handlers) that restarts the idle timer and re-shows the bar plus the art's hover nav arrows together. Lyrics toggle (`5` or the bar button) borrows the app's LyricsWidget beside the art (same reparenting pattern as MaxView — App styles it directly since the main stylesheet doesn't reach another top-level window). Key handling is a Qt-key→callable map supplied by App, so mini mode reuses the app's shortcut behaviors. Geometry and lyrics preference persist (`mini/geometry`, `mini/lyrics`).

**`player.py`** — Playback controls and album art. Uses `just_playback` (requires `play()` before `pause()`/`seek()` will work). Emits `track_changed`, `track_finished`, `art_clicked`, `art_changed(QPixmap)`, and `play_state_changed(bool)`. All artwork must go through `player.set_art(pixmap)` (single image) or `player.set_art_gallery(paths)` so listeners stay in sync. The gallery is the album folder's images (cover first); `step_art(±1)` scrolls it, and every `AlbumArtLabel` registered via `register_art_label()` (player column, max view, mini view) gets hover arrows wired to it. Progress/lyrics tick on a 200ms QTimer. SVG icon rendering is memoized by (name, color, size). Layout is pure Qt layouts, plus one deliberate exception: `resizeEvent` recomputes a `_compact_t` (0=tight..1=roomy) from the column's height and shrinks the controls block's margins/spacing/icon size/progress-bar thickness as it gets short, so the fixed-height controls never eat into the album art's space. `set_control_scale()` folds `_compact_t` into its icon-size formula.

**`art_label.py`** — `AlbumArtLabel`: aspect-ratio-preserving art display. Downscales oversized sources (>1200px) once on load, caches a display-sized copy, and refreshes it on a 120ms debounce — no full-res repaints, no graphics effects. `square=True` center-crops sources to square (vinyl-sleeve feel; used by the player/mini art). Has built-in prev/next hover arrows for art galleries (`set_nav_enabled`) — shown only while hovered, hidden whenever the application deactivates.

**`theme.py`** — One font for the whole app: Inter, bundled in `src/fonts/` (Regular + Bold, OFL) and registered by `resolve_fonts()` at startup (system-sans fallback if missing). One size scale (`SIZES`/`DEFAULT_SIZE`) — the Text Size dialog and `Ctrl+=`/`Ctrl+-` step everything together. LIGHT/DARK token dicts (`bg`, `bg_elevated`, `fg`, `fg_dim`, `hairline`, `hover`, `accent`, `accent_fg`, plus legacy aliases for the dialogs). `build_qss()` produces ONE consolidated stylesheet applied once to the main window in `App.apply_theme` (theme/accent/font changes only). Focused-pane highlighting uses the dynamic `paneFocused` property on the tree/list views with `[paneFocused="true"]` selectors — focus changes repolish only the affected views, never regenerate QSS. `dialog_qss()` styles the dialogs. Accent color is woven into hover states everywhere (`accent_hover`, a ~9%-alpha tint, replaces flat grey hover on toolbar buttons and list/tree items) but is never trusted as literal text color at face value — `App.apply_theme` also computes `accent_text` (accent re-contrast-checked at ~4.5:1, stricter than the 3:1 used for `accent` itself) for the few spots that render it directly as foreground text (see `lyrics_widget.py`).

**`album.py`** — Parses a folder into a list of Track objects using mutagen for metadata and tinytag as fallback. `refresh_art()` scans the folder for artwork: `art` is cover.jpg, `art_list` is every image (cover first) — the scrollable gallery.

**`track.py`** — Plain data class for track metadata. All string fields are `str()`-converted in `__init__` to avoid mutagen lazy objects.

**`folder_view.py`** — Filesystem folder browser using QFileSystemModel. Filters to show only directories. Click loads a folder as an album in AlbumView. Has context menu for "Open folder" via platform file manager.

**`album_view.py`** — Tracklist. Long titles elide on one line (full text in tooltip); `setUniformItemSizes(True)` keeps large lists cheap. Right-click a track for "Look Up Chords / Tab", which opens the default browser (via `QDesktopServices`) with a web search — no scraping, no API key.

**`grip_splitter.py`** — `GripSplitter` (used for `main_splitter`/`right_splitter`) paints a faint 1px hairline along each handle's full length; the line turns accent-colored on hover.

**`progress_bar.py`** — ClickableProgressBar with click-to-seek and drag-to-scrub. Emits `seek_requested` (during drag) and `start_playback` (on release) signals.

**`music_icon_provider.py`** — Custom QFileIconProvider that hides folder icons (returns transparent pixmap) to keep the folder tree visually clean.

**`lyrics_widget.py` / `lyrics_fetcher.py`** — Lyrics display with synced scrolling; fetches from LRCLIB API, prefers synced `.lrc`, caches in `album/lyrics/`. QTextBrowser-based: one QTextBlock per line/segment, active-line highlight via QTextCharFormat on only the changed blocks, auto-scroll from the block's measured y-position (accurate with wrapped lines). The active-line/timestamp color comes from `theme['accent_text']`, not `theme['accent']` — see `theme.py` — so it stays readable regardless of the chosen accent hue. Podcast descriptions get clickable timestamps and segment highlighting. Radio now-playing goes through `set_status_html()`.

**`artwork_finder.py`** — Artwork search dialog. iTunes Search API for covers, saved as `cover.jpg` (overwritten in place, streamed to disk). With `extra=True` ("Find More Album Art...") it saves to the next free `art_N.jpg` instead and *also* searches Discogs (`DiscogsSearchThread`, unauthenticated, ~4 requests/search against a 25/min limit) — Discogs releases carry collector scans of backs, labels, gatefolds and inserts, shown in their own section below the iTunes covers. In this `extra` mode each result row shows a checkbox instead of an immediate-save button; picks persist in `_selected` (keyed by URL) across repeated searches, and "Save Selected" downloads them all in one queued batch before closing the dialog — so you don't need a fresh dialog open per image. The non-extra ("Change Cover Art...") dialog keeps the original single-click-save-and-close flow. "Add Album Art..." (App) copies local image files into the album folder. All paths refresh the player's gallery.

**`color_extract.py`** — Extracts a palette from album art (QImage pixel sampling, HSV binning) and picks the most readable accent color using WCAG contrast ratios. Always runs in `PaletteExtractThread` — never on the UI thread; the last palette is cached for menu rebuilds.

**`vim_views.py`** — VimTreeView/VimListWidget with vim-style j/k/h/l navigation, `/` search, and Enter-to-open. Consumes printable keys to prevent type-to-search.

**Settings**: `QSettings('lp', 'music-player')` persists theme, accent (global + per-album `album_accents`), text size (`font_size`), window geometry, panel layout (`layout/*` keys via PanelManager, incl. per-mode panel memory), mini mode state (`mini/*`), library path, app mode, and per-mode playback positions.

## Keyboard Shortcuts

All global QShortcuts are suppressed when a QLineEdit has focus. Max mode handles its keys in `App.keyPressEvent`; mini mode via a key→handler map App gives the MiniView.

| Key | Action |
|-----|--------|
| `j` / `k` | Navigate down / up in focused pane |
| `h` / `l` | Folder view: collapse / expand; Tracklist: go to library |
| `Tab` | Switch focus between folder view and album view |
| `Enter` | Load album (folder view) or play track (tracklist) |
| `/` | Open search bar in focused pane |
| `p` | Play/Pause |
| `>` / `<` | Next / Previous track (podcast: ±30s) |
| `f` / `b` | Seek forward / back 5s |
| `.` / `,` | Volume up / down 5% |
| `1` / `2` / `3` | Switch to music / podcast / radio mode (same mode again: toggle library panel) |
| `4` | Toggle tracklist panel (+ focus) |
| `5` | Toggle lyrics panel (also in max and mini mode) |
| `m` | Toggle mini mode (in mini: `m`/`Esc`/double-click exits) |
| `Shift+M` | Toggle max mode |
| `Shift+D` | Toggle dark/light theme |
| `Ctrl+=` / `Ctrl+-` | Text size up / down (whole app) |
| `q` | Quit |
| `?` | Show shortcuts dialog |

## Key Conventions

- Vim j/k/h/l navigation in folder view and tracklist; h/l in tracklist switches to folder view
- Global QShortcuts are suppressed when a QLineEdit has focus
- Panel visibility/sizes go through `PanelManager` only — never call `setVisible` or `setSizes` on the panes directly
- All artwork goes through `player.set_art()` / `player.set_art_gallery()`; theme/accent changes go through `App.apply_theme` (one stylesheet)
- One font (Inter) and one text size app-wide — no per-category font settings
- All source files live in `src/` with flat structure (no subpackages)
- No test suite exists currently
- Dependencies: PyQt5 for GUI, just_playback for audio, mutagen/tinytag for metadata, requests for API calls
