# Display Modes

lp has three playback modes, two display modes, and panel toggle controls.

## Playback modes

Switch modes via the toolbar buttons or keyboard shortcuts `1`/`2`/`3`:

### Music mode (default)

Standard three-panel layout with filesystem browser on the left. Navigate folders, load albums, play tracks with full controls (prev/next, seek, progress bar).

### Podcast mode

Left panel shows subscribed podcast feeds. Click a feed to load its episodes into the tracklist. Prev/next buttons become ±30s seek. Episodes are downloaded to `~/.cache/lp/podcasts/` before playback. Episode playback positions are saved and restored.

### Radio mode

Left panel shows saved radio stations (stream URLs). Click a station to start streaming via `QMediaPlayer`. The player shows:
- A themed radio SVG graphic (concentric signal rings with the station icon)
- Station name and now-playing metadata in the marquee label (scrolls if too long)
- Now-playing info in the lyrics panel when stream metadata is available

Only the play/pause button is shown — prev/next, progress bar, and time labels are hidden since streams have no duration.

Switching away from radio mode stops the stream.

## Normal mode

The default three-panel layout:

```
 Library  |  Player  |  Tracklist
 (folders)|  (art +  |  ---------
          | controls)|  Lyrics
```

Each side panel can be toggled independently:
- `1` — toggle library panel
- `2` — toggle tracklist panel
- `3` — toggle lyrics panel

The right splitter auto-sizes so lyrics sit just below the tracklist (capped at 50% of the right panel height).

## Max mode (`Shift+M`)

A fullscreen mode focused on the album art and lyrics:

```
 ┌──────────────────────────────────────┐
 │     Artist      Album      Track     │  <- info bar
 ├────────────────────┬─────────────────┤
 │                    │                 │
 │    Album Art       │    Lyrics       │
 │    (2/3 width)     │   (1/3 width)   │
 │                    │                 │
 └────────────────────┴─────────────────┘
```

- The info bar shows artist, album, and current track name
- Album art is scaled to fill available space while keeping aspect ratio
- Lyrics display in a larger font size (+8pt)
- Lyrics scroll position is aligned vertically with the album art edges
- Clicking the art exits max mode
- `3` toggles lyrics visibility within max mode
- `Shift+M` or `Escape` exits back to normal mode

### State preservation

Entering max mode saves the current window geometry, splitter positions, and panel visibility. Exiting restores everything to its previous state.

## Toolbar

A custom hover-accessible toolbar at the top of the window (replaces the native menu bar):

```
 [♫] [◎] [📶]      Preferences  Theme  Help      [1] [2] [3]
  mode toggles              menus               panel toggles
```

- **Left**: Mode toggle buttons (Music, Podcast, Radio) — checkable, mutually exclusive
- **Center**: Drop-down menus (Preferences, Theme, Help)
- **Right**: Panel toggle buttons (Library, Tracklist, Lyrics)

## Panel toggles

Panel visibility uses the `isVisible()` check as the source of truth. When toggling a panel:

- If shown, focus moves to it
- If the toggled panel is hidden, focus falls back to the next visible panel
- In max mode, library and tracklist toggles are disabled (only lyrics can toggle)
