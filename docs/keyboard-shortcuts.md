# Keyboard Shortcuts

All global shortcuts are `QShortcut` instances that are suppressed when a `QLineEdit` (search bar) has focus, so typing in a search doesn't trigger playback commands.

## Navigation

| Key | Action |
|-----|--------|
| `j` / `k` | Navigate down / up in the focused pane |
| `h` | Folder view: collapse node; at top level: switch to tracklist |
| `l` | Folder view: expand node, or load album if it's a music folder and switch to tracklist |
| `h` / `l` | In tracklist: switch to folder view |
| `Tab` | Toggle focus between folder view and tracklist |
| `Enter` | Load album (folder view) or play track (tracklist) |
| `/` | Open search bar in the focused pane |

## Playback

| Key | Action |
|-----|--------|
| `p` | Play / Pause (works across all modes including radio) |
| `>` | Next track (music/podcast) |
| `<` | Previous track (music/podcast) |
| `f` | Seek forward 5 seconds |
| `b` | Seek back 5 seconds |
| `.` | Volume up 5% |
| `,` | Volume down 5% |

## Modes & panels

| Key | Action |
|-----|--------|
| `1` | Music mode (or toggle library panel if already in music mode) |
| `2` | Podcast mode (or toggle library panel if already in podcast mode) |
| `3` | Radio mode (or toggle library panel if already in radio mode) |
| `4` | Toggle tracklist panel (+ focus) |
| `5` | Toggle lyrics panel (also toggles the lyrics column in max mode) |
| `Shift+M` | Toggle max mode |
| `Shift+D` | Toggle dark / light theme |
| `Ctrl++` / `Ctrl+=` | Increase font size |
| `Ctrl+-` | Decrease font size |

## Other

| Key | Action |
|-----|--------|
| `?` | Show shortcuts dialog |
| `q` | Quit |
| `Escape` | Exit max mode (when in max mode) |
