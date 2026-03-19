# Lyrics

lp fetches and displays song lyrics with synced scrolling support.

## Fetching

Lyrics are fetched from the [LRCLIB API](https://lrclib.net) in a background `QThread` when a track starts playing. The fetcher:

1. Tries the `/api/get` endpoint first (exact match by artist, title, album)
2. Falls back to `/api/search` if the exact match fails
3. Prefers **synced lyrics** (`.lrc` format with timestamps) over plain text
4. Saves the result to disk for caching

If a fetch fails for a track, it's added to `_failed_lyrics` so lp won't re-attempt it during the same session.

## Caching

Lyrics are cached as files in a `lyrics/` subdirectory inside the album folder:

```
~/Music/Artist/Album/lyrics/01_Song Title.lrc    (synced)
~/Music/Artist/Album/lyrics/01_Song Title.txt    (plain)
```

The filename is `{track_number:02d}_{title}` with invalid filename characters replaced by underscores. On subsequent plays, the cached file is loaded directly without hitting the API.

## Synced scrolling

When synced `.lrc` lyrics are available:

- Each line has a timestamp (e.g. `[01:23.45] Some lyrics`)
- The lyrics widget highlights the current line based on playback position
- The view auto-scrolls to keep the active line centered
- Clicking a lyrics line seeks playback to that timestamp

## Display modes

- **Normal mode**: lyrics appear in the right panel below the tracklist
- **Max mode**: lyrics appear in a larger font to the right of the album art, with their top/bottom edges aligned to the artwork
