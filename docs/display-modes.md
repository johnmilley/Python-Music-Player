# Display Modes

lp has three playback modes, two display modes, and panel toggle controls.

## Playback modes

Switch modes via the toolbar buttons or keyboard shortcuts `1`/`2`/`3`. The
three mode views (folders, podcast feeds, radio stations) live in one stacked
widget in the left pane — switching modes swaps the stack page and never
disturbs the splitter layout. Pressing the current mode's key again toggles
the library panel.

### Music mode (default)

Standard layout with filesystem browser on the left. Navigate folders, load
albums, play tracks with full controls (prev/next, seek, progress bar).

### Podcast mode

Left panel shows subscribed podcast feeds. Click a feed to load its episodes
into the tracklist. Prev/next buttons become ±30s seek. Episodes are
downloaded to `~/.cache/lp/podcasts/` before playback. Episode playback
positions are saved and restored. The tracklist/lyrics visibility you had in
music mode is snapshotted and restored when you switch back.

### Radio mode

Left panel shows saved radio stations (stream URLs). Click a station to start
streaming via `QMediaPlayer`. The player shows:
- A themed radio SVG graphic
- Station name and now-playing metadata in the marquee label (scrolls if too long)
- Now-playing info in the lyrics panel when stream metadata is available

Only the play/pause button is shown — prev/next, progress bar, and time labels
are hidden since streams have no duration.

Switching away from radio mode stops the stream.

## Normal mode

The nested-splitter layout — tracklist over lyrics in the right column:

```
 Library  |  Player   |  Tracklist
 (folders)|  (art +   |------------
          | controls) |  Lyrics
```

Panel toggles:
- `1` — toggle library panel (when already in music mode; `1`/`2`/`3` otherwise switch modes)
- `4` — toggle tracklist panel (+ focus)
- `5` — toggle lyrics panel

Panel sizing is owned by `PanelManager`: hiding a panel remembers its exact
extent, showing it restores that extent, and dragging a splitter handle updates
the remembered size — so toggles always round-trip and never rearrange the
panes you didn't touch. When both tracklist and lyrics are hidden the whole
right column collapses.

## Max mode (`Shift+M`)

A fullscreen page focused on the album art and lyrics:

```
 ┌──────────────────────────────────────┐  <- accent divider
 │                    │   Track title   │
 │    Album Art       │                 │
 │    (2/3 width)     │    Lyrics       │
 │                    │   (1/3 width)   │
 └────────────────────┴─────────────────┘
```

- Album art is scaled to fill available space while keeping aspect ratio
- The app's single lyrics widget is *borrowed* into the max page (larger font,
  +8pt) — the synced highlight continues seamlessly
- Clicking the art exits max mode
- `5` toggles the lyrics column within max mode
- `Shift+M` or `Escape` exits back to normal mode

### State preservation

The normal layout stays untouched behind the view stack while max mode is
active — exiting simply switches back and restores the window geometry.

## Toolbar

A slim, always-visible top bar of icon toggles (replaces the native menu
bar), underlined by a thin accent-colored strip. The active mode and open
panels are marked by the icon glyph itself turning the accent color — no
underline.

```
 [♪] [🎙] [〰]                    [▤] [≡] [☰] [⚙]
   mode toggles           panel toggles + settings menu
 ──────────────────────────────────────────────────────  <- accent strip
```

- **Left**: Mode toggle icons (Music, Podcast, Radio) — checkable, mutually exclusive
- **Right**: Panel toggle icons (Library, Tracklist, Lyrics) and the gear menu (Theme, Preferences, Help)

## Panel toggles

Panel visibility is owned by `PanelManager` — the toolbar buttons and keyboard
shortcuts both call into it, and the buttons just mirror its
`visibility_changed` signal. When toggling a panel:

- If shown, focus moves to it
- If the toggled panel is hidden, focus falls back to the next visible panel
- In max mode, panel toggles are locked (only the max lyrics column can toggle)
