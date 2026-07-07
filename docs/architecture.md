# Architecture

lp is a PyQt5 desktop music player with a flat source layout — all files live in `src/` with no subpackages.

## Layout

The central widget is a `QStackedWidget` with two pages — the normal layout
and the fullscreen max view. The normal page nests two splitters under a
custom toolbar:

```
 root_stack (QStackedWidget)
 ├── normal page
 │   ┌─ ToolBar ─────────────────────────────────────────────┐
 │   │ [MUSIC][PODCASTS][RADIO]   [LIBRARY][TRACKLIST][LYRICS][⚙] │
 │   ├────────────┬────────────┬───────────────────────────┤
 │   │ left_stack │   player   │  right_splitter (vertical) │
 │   │ (QStacked- │   (art +   │    album_view (tracklist)  │
 │   │  Widget)   │  controls) │    ──────────────────────  │
 │   │            │            │    lyrics_widget           │
 │   └────────────┴────────────┴───────────────────────────┘
 └── max page: MaxView (large art | track title + borrowed lyrics)
```

The left stack swaps pages based on mode (the splitters never see mode changes):
- **Music** → `folder_view` (filesystem browser)
- **Podcast** → `podcast_view` (feed subscriptions)
- **Radio** → `radio_view` (saved stations)

Center and right panels are shared across all modes. `PanelManager`
(`panel_manager.py`) is the single source of truth for panel visibility and
remembered splitter sizes: toggles round-trip exactly, drags update the
remembered sizes, and the right column collapses when both its panes hide.

## Module overview

| File | Role |
|------|------|
| `app.py` | `QMainWindow` orchestrator — creates all widgets, wires signals, manages theme/settings/shortcuts, implements display and playback modes |
| `panel_manager.py` | Single source of truth for panel visibility and remembered splitter sizes |
| `max_view.py` | Fullscreen max-mode page — large art plus the borrowed lyrics widget |
| `art_label.py` | `AlbumArtLabel` — cached, debounced, aspect-correct album art rendering with rounded corners |
| `player.py` | Playback controls and album art display. Uses `just_playback` for audio. Has a 200ms `QTimer` for progress updates; memoized SVG icons |
| `album_view.py` | Tracklist panel — shows tracks for the loaded album (or podcast episodes). Right-click a track to look up chords/tab in the browser |
| `folder_view.py` | Filesystem folder browser using `QFileSystemModel`, filters to directories only |
| `album.py` | Parses a folder into a list of `Track` objects using `mutagen` (with `tinytag` fallback) |
| `track.py` | Plain data class for track metadata |
| `grip_splitter.py` | `GripSplitter` — `QSplitter` whose handles paint a faint 1px hairline (accent-colored on hover) |
| `podcast_view.py` | Left panel for podcast mode — feed subscription list with add/remove |
| `podcast_feed.py` | RSS feed parsing, `PodcastFeed`/`PodcastEpisode` data classes, download threads |
| `radio_view.py` | Left panel for radio mode — saved station list with add/remove |
| `radio_player.py` | Thin `QMediaPlayer` wrapper for streaming radio, emits stream metadata |
| `radio_station.py` | `RadioStation` data class (name + stream URL) |
| `marquee_label.py` | Winamp-style horizontally scrolling `QLabel` for long track titles |
| `theme.py` | LIGHT/DARK token dicts plus `build_qss()` — one consolidated stylesheet for the whole app |
| `vim_views.py` | `VimTreeView` / `VimListWidget` with j/k navigation, `/` search, Enter-to-open |
| `lyrics_widget.py` | Lyrics display with synced scrolling, click-to-seek, and description mode |
| `lyrics_fetcher.py` | Fetches lyrics from LRCLIB API in a background thread |
| `artwork_finder.py` | iTunes Search API dialog for finding and downloading album art |
| `color_extract.py` | Extracts a color palette from album art, picks the most readable accent color |
| `progress_bar.py` | `ClickableProgressBar` with click-to-seek and drag-to-scrub |
| `music_icon_provider.py` | Custom `QFileIconProvider` that hides folder icons for a cleaner tree |

## Widget ownership

`App` creates `Player`, `AlbumView`, `LyricsWidget`, `FolderView`, `PodcastView`, `RadioView`, and `RadioPlayer`, then cross-wires them directly (e.g. `player.album_view = self.album_view`). This intentional coupling means widgets reference each other directly rather than communicating exclusively through signals.

## Key dependencies

- **PyQt5** — GUI framework (including `QtMultimedia` for radio streaming, `QtSvg` for icon rendering)
- **just_playback** — audio playback for music and podcasts (important: requires `play()` before `pause()`/`seek()` will work)
- **mutagen** / **tinytag** — audio metadata parsing
- **requests** / **urllib** — API calls for lyrics, artwork, and podcast feeds
- **certifi** — SSL CA bundle (bundled for PyInstaller builds)

## Design patterns

- **Album/Track polymorphism**: Podcasts (`PodcastFeed`/`PodcastEpisode`) and radio (`RadioStation`) mimic the `Album`/`Track` API so the `Player` widget can handle all modes
- **SVG icon rendering**: Icons loaded as SVG text with fill color injected at runtime, enabling dynamic theme-aware coloring without multiple icon files
- **Thread-based async**: Heavy I/O (podcast fetches, image downloads, lyrics searches, palette extraction) uses `QThread` subclasses
- **Focus-aware styling**: the dynamic `paneFocused` widget property drives `[paneFocused="true"]` QSS selectors — focus changes repolish only the two views, never regenerate the stylesheet
