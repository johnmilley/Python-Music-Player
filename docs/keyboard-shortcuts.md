# Keyboard Shortcuts

All global shortcuts are `QShortcut` instances that are suppressed when a `QLineEdit` (search bar) has focus, so typing in a search doesn't trigger playback commands.

## Library pane

| Key | Action |
|-----|--------|
| `j` / `k` | Navigate down / up |
| `Enter` / `l` | Open the album / feed / collection (drills down to its tracks); in the tracklist, `Enter` plays |
| `h` | Folder view: collapse node; at top level: back down to the open tracklist |
| `h` / `l` | In the tracklist: back up to the library |
| `Tab` | Flip between the library and tracklist pages |
| `n` | Go back to what's playing, in any mode — selects it on the library page and lists it (also in max mode) |
| `Ctrl+K` | Jump to any album: type part of the artist/album, `↑`/`↓` (or `Ctrl+J`/`Ctrl+K`), `Enter` opens, `Esc` cancels. Works in max mode too (opens in max's tracklist) |
| `/` | Open search bar in the focused list |

## Playback

| Key | Action |
|-----|--------|
| `p` | Play / Pause (works across all modes including radio) |
| `>` | Next track (podcasts: +30s) |
| `<` | Previous track (podcasts: -30s) |
| `f` | Seek forward 5 seconds |
| `b` | Seek back 5 seconds |
| `.` | Volume up 5% (also: scroll up over the art) |
| `,` | Volume down 5% (also: scroll down over the art) |
| `m` | Mute / unmute |
| `s` | Toggle shuffle |
| `Shift+H` | Favourite / unfavourite the playing track |

## Modes & panes

| Key | Action |
|-----|--------|
| `1` / `2` / `3` / `0` | Music / Podcasts / Radio / Favourites (the active one again: toggle the library pane; not in max mode) |
| `4` | Library pane on its tracklist (again: close it) |
| `5` | Toggle the lyrics pane |
| `Shift+M` | Toggle max mode (also: double-click the art) |
| `Shift+T` | Toggle always on top (not in max mode) |
| `Shift+P` | Pin / unpin the playback controls (also in max mode) |
| `Shift+D` | Toggle dark / light theme |
| `Ctrl++` / `Ctrl+=` | Increase text size |
| `Ctrl+-` | Decrease text size |
| `←` / `→` | Step through the album's art (max mode) |

## Other

| Key | Action |
|-----|--------|
| `?` | Show shortcuts dialog |
| `q` | Quit |
| `Escape` | Exit max mode |
