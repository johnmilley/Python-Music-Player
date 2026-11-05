# Keyboard Shortcuts

All global shortcuts are `QShortcut` instances that are suppressed when a `QLineEdit` (search bar) has focus, so typing in a search doesn't trigger playback commands.

## Library pane

| Key | Action |
|-----|--------|
| `j` / `k` or `↓` / `↑` | Navigate down / up |
| `Enter`, `l` or `→` | Open the selected item: an album, feed or collection drills down to its tracks; a station plays; a folder that isn't an album expands. In the tracklist, `Enter` plays |
| `←`, `h` or `Backspace` | In the tracklist: back up to the library. In the folder tree: collapse / go to parent; at the top level (and in the feed/collection lists), `←`/`h` go over to the open tracklist |
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
| `1` / `2` / `3` / `4` | Music / Podcasts / Radio / Favourites (the active one again: toggle the library pane; in max mode: toggle the tracklist pane) |
| `0` | Toggle the lyrics / show-info pane |
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
