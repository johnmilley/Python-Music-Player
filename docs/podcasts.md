# Podcast Mode

lp can subscribe to and play podcast feeds.

## Adding feeds

Paste an Apple Podcasts link or direct RSS feed URL into the input field at the top of the podcast panel. The app:

1. If it's an Apple Podcasts link, extracts the podcast ID and resolves it to an RSS feed URL via the iTunes Lookup API
2. Fetches and parses the RSS feed XML (supports `itunes:` and `media:` namespaces)
3. Extracts feed metadata: title, description, artwork URL, and episode list
4. Downloads the feed artwork in a background thread
5. Saves the feed URL to QSettings for persistence

Right-click a feed to remove or refresh it.

## Episodes

Each episode is represented as a `PodcastEpisode` (Track-compatible data class) with:
- Title, description, publication date, duration
- Audio URL and GUID (for cache identification)
- Download status and local cache path

Episodes are displayed in the tracklist (AlbumView) when a feed is selected. Double-click to play.

## Downloading

Episodes are downloaded to `~/.cache/lp/podcasts/` before playback:
- Filename: MD5 hash of the episode GUID + original extension
- Download runs in a background `EpisodeDownloadThread`
- A context menu option allows pre-downloading episodes

## Playback controls

In podcast mode, the prev/next buttons change to ±30s seek buttons (with `fast_rewind`/`fast_forward` icons and "30s" labels). The progress bar, play/pause, and time labels work the same as music mode.

## Position tracking

Episode playback positions are saved per-episode (keyed by GUID) in QSettings. When returning to a previously-played episode, playback resumes from the saved position.

## State restoration

On startup, if the last mode was podcast, the app restores:
- The last-played feed URL (auto-selects it in the feed list)
- The last episode index and seek position
- Playback resumes automatically if the episode is already downloaded

## Components

| File | Class | Purpose |
|------|-------|---------|
| `podcast_view.py` | `PodcastView` | Left panel — feed subscription list with add/remove/refresh |
| `podcast_feed.py` | `PodcastFeed` | Album-compatible feed container with episode list |
| `podcast_feed.py` | `PodcastEpisode` | Track-compatible episode data class |
| `podcast_feed.py` | `FeedFetchThread` | Background thread for fetching/parsing RSS |
| `podcast_feed.py` | `EpisodeDownloadThread` | Background thread for downloading episode audio |
| `podcast_feed.py` | `ImageDownloadThread` | Background thread for downloading feed artwork |
