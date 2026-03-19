# Architecture

lp is a PyQt5 desktop music player with a flat source layout — all files live in `src/` with no subpackages.

## Layout

The main window uses a multi-panel `QSplitter` with a custom toolbar at the top:

```
 ┌─ ToolBar ──────────────────────────────────────────────┐
 │ [♫] [◎] [📶]     Preferences  Theme  Help    [1][2][3] │
 ├────────────┬────────────┬──────────────────────────────┤
 │ left panel │   player   │  right_splitter              │
 │ (mode-     │   (art +   │    album_view (tracklist)    │
 │  specific) │  controls) │    ─────────────────         │
 │            │            │    lyrics_widget              │
 └────────────┴────────────┴──────────────────────────────┘
```

The left panel swaps based on mode:
- **Music** → `folder_view` (filesystem browser)
- **Podcast** → `podcast_view` (feed subscriptions)
- **Radio** → `radio_view` (saved stations)

Center and right panels are shared across all modes.

## Module overview

| File | Role |
|------|------|
| `app.py` | `QMainWindow` orchestrator — creates all widgets, wires signals, manages theme/settings/shortcuts, implements display and playback modes |
| `player.py` | Playback controls and album art display. Uses `just_playback` for audio. Has a 20ms `QTimer` for progress updates |
| `album_view.py` | Tracklist panel — shows tracks for the loaded album (or podcast episodes) |
| `folder_view.py` | Filesystem folder browser using `QFileSystemModel`, filters to directories only |
| `album.py` | Parses a folder into a list of `Track` objects using `mutagen` (with `tinytag` fallback) |
| `track.py` | Plain data class for track metadata |
| `podcast_view.py` | Left panel for podcast mode — feed subscription list with add/remove |
| `podcast_feed.py` | RSS feed parsing, `PodcastFeed`/`PodcastEpisode` data classes, download threads |
| `radio_view.py` | Left panel for radio mode — saved station list with add/remove |
| `radio_player.py` | Thin `QMediaPlayer` wrapper for streaming radio, emits stream metadata |
| `radio_station.py` | `RadioStation` data class (name + stream URL) |
| `marquee_label.py` | Winamp-style horizontally scrolling `QLabel` for long track titles |
| `theme.py` | LIGHT/DARK theme dicts with color tokens, plus QSS generator functions |
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
- **Thread-based async**: Heavy I/O (podcast fetches, image downloads, lyrics searches) uses `QThread` subclasses
- **Focus-aware styling**: QSS regenerated on focus change to update selection background color
