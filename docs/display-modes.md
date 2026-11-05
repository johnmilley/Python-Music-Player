# Display Modes

Since v2.0 the old mini mode *is* the main window: album art first, with the
library and lyrics opening as side panes. Max mode (`Shift+M`) is the
fullscreen view.

## The main window

```
 ┌──────────────────┬───────────────────────┬────────────────┐
 │ ♪  🎙  〰  ♥      │                       │ Track title    │
 │ ‹  Artist — Album│                       │                │
 │──────────────────│       ALBUM ART       │ lyrics…        │
 │ 1. Track one     │   (always square)     │ ▶ active line  │
 │ 2. Track two     │ ┌───────────────────┐ │ lyrics…        │
 │ 3. Track three   │ │ title           ♥ │ │                │
 │                  │ │ 0:42 ━━━━━━━ 3:10 │ │                │
 │                  │ │ ≡ ⤮ ◀ ▶ ▶ ↻   ¶ ⋯ │ │                │
 │                  │ └───────────────────┘ │                │
 └──────────────────┴───────────────────────┴────────────────┘
   library pane (4)        the stage          lyrics pane (5)
```

- **The art stays square.** With no panes open the window keeps itself
  square while you resize it. Opening a pane *widens the window* by the
  pane's width instead of squeezing the art; the left pane shifts the
  window left so the art doesn't move under the cursor. Maximized windows
  just reflow.
- **Controls float over the art**, shown on hover and hidden after 2.5s
  without mouse movement. `≡` toggles the library pane, `¶` the lyrics
  pane, `⋯` opens the menu.
- **Drag the art** to move the (frameless) window; drag any edge to resize.
  **Double-click the art** for max mode; **right-click** it for the menu.

## Library pane

Mode tabs on top, then a two-level drill-down:

1. **Library page** — the current mode's list: folders (music), feeds
   (podcasts), stations (radio), collections (favourites).
2. **Tracks page** — the album / episodes / collection you opened, with a
   `‹` back arrow and its title.

Opening something (`Enter`, `l`, or a click) drills down; `h` or `‹` goes
back up; `Tab` flips between the two pages.

**Browsing never touches playback.** Opening another album while one plays
leaves the art, accent and lyrics on the playing album; a **Now playing**
link (or `n`) jumps the tracks page back to what's playing.

**Jump to any album with `Ctrl+K`**: a search box over the art lists every
album in the library; type a few letters of the artist and/or album
("big pi"), `Enter` opens it on the tracks page (switching to music mode if
needed).

Clicking the active mode tab (or pressing its number again) toggles the
pane: closed → library page; on the tracks page → back up to the library;
on the library page → closed.

### Music

Folder tree of the library root (Preferences → Music Library...). Album
folders open their tracklist.

### Podcasts

Subscribed feeds; opening one lists its episodes. Prev/next become -30s /
+30s. Episodes download to `~/.cache/lp/podcasts/` before playback and
resume where you left off. The feed description shows in the lyrics pane.

### Radio

Saved stations; opening one starts streaming. Only play/pause is shown —
streams have no duration. Stream metadata (now playing) shows in the panel
title and the lyrics pane. Station art: ⋯ → Change Station Art... (or
right-click the station).

### Favourites

All Favourites plus your playlists, and the shuffle switch.

## The ⋯ menu

Theme (dark/light, accent), Preferences (text size, overlay opacity, album
art, library, remote access, listening stats), **Max Mode**, **Always on
Top** (off by default, remembered), Change Station Art (radio), Help, Quit.

## Max mode (`Shift+M`, or double-click the art)

Fullscreen art beside a side column with the tracklist and lyrics panes
(`4` / `5`), borrowed from the main window — same content, same highlight.
The same control panel floats over the art on mouse movement, ⋯ menu
included (also on right-click); `Esc`, the corner ✕ or the panel's ✕ exits.

Library actions carry on in max mode, landing in its tracklist pane:
`Ctrl+K` to jump to any album, `n` for now playing, `/` to search the
tracklist. Mode keys (`1`/`2`/`3`/`0`) and always-on-top only apply to the
main window.
