# Radio Mode

lp can stream internet radio stations via `QMediaPlayer`.

## Adding stations

Paste a stream URL into the input field at the top of the radio panel and press Enter or click `+`. A dialog prompts for a station name. Stations are saved to QSettings and persist across sessions.

Right-click a station to remove it.

## Playback

Click a station to start streaming. The radio player (`RadioPlayer`) wraps `QMediaPlayer` and provides:
- Play/pause toggle (the only visible control — prev/next and progress bar are hidden)
- Stream metadata extraction via `QMediaPlayer.metaDataChanged` signal

When a station is playing, switching to another mode (music or podcast) **stops the radio stream**. This is intentional — radio does not continue in the background.

## Display

When streaming, the player panel shows:

- **Radio art**: A themed SVG graphic with concentric signal rings and a cell tower icon, rendered using the current theme's accent and background colors
- **Track info**: Station name followed by now-playing metadata (e.g. `CBC Radio One  •  As It Happens`), displayed in a `MarqueeLabel` that scrolls if the text overflows
- **Lyrics panel**: Shows the current now-playing title and station name in a centered layout when stream metadata is available

## Stream metadata

Many internet radio stations broadcast ICY metadata (current song/program title) within the stream. `RadioPlayer` listens for `QMediaPlayer.metaDataChanged` and emits a `metadata_changed(str)` signal when the title changes. This updates the track info label and lyrics panel in real-time.

## State restoration

On startup, if the last mode was radio, the last-played station name and URL are restored from settings. The radio art and station name are displayed, but playback does not auto-start — the user must click play or re-select the station.

## Components

| File | Class | Purpose |
|------|-------|---------|
| `radio_view.py` | `RadioView` | Left panel — station list with add/remove |
| `radio_player.py` | `RadioPlayer` | `QMediaPlayer` wrapper for streaming + metadata |
| `radio_station.py` | `RadioStation` | Data class: `name`, `stream_url`, plus Track-compatible fields |
