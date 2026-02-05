# Notes and Tasks

## Tasks to review

- [ ] User Preferences (link stylesheets to ui preferences)
- [ ] Unit testing
- [ ] Diagramming
- [ ] replace mutagen with something that supports system keys
- [ ] responsive UI / multiple UIs

## Classes

`FolderView`
`Player`
`AlbumViewer`

## Class Relationships

1 `Alumb` displays many `Track`s
1 `AlubmView` displays 1 `Album`

## subClasses

### `ProgressBar`

- `ProgressBar` inherits `QProgressBar`
overrides `mousePressEvent()`, `mouseMoveEvent()`
- internal methods: `_handle_click` and `_handle_release`

### `MusicIconProvider`

## Coupling

- `Player` has an `AlbumView` (toggle, track highlighting) and `FolderView` (toggle)

## Signals

- `Player` has track_finished that emits when a track finishes playing.
- `ProgressBar` has `seek_requested` and `start_playback`
