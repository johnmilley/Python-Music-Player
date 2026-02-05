# Notes and Tasks

## Tasks to review
- [ ] replace mutagen with something that supports system keys
- [ ] responsive UI / multiple UIs

## Class info

1 `Alumb` displays many `Track`s
1 `AlubmView` displays 1 `Album`

## subClasses

### `ProgressBar`

- `ProgressBar` inherits `QProgressBar`
overrides `mousePressEvent()`, `mouseMoveEvent()`
- `_handle_click` and `_handle_release` are internal method, not intended for public use (prefaced with _ by convention)

### `MusicIconProvider`

## Coupling:
- `Player` has an `AlbumView` and `FolderView`
    - toggle controls
    - `AlbumView` current track highlighting


## Signals
`Player` has track_finished that emits when a track finishes playing.
`ProgressBar` has `seek_requested` and `start_playback`
