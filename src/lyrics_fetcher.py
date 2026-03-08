# Lyrics fetcher using LRCLIB API
# Downloads synced (.lrc) or plain (.txt) lyrics to album folder

import json
import re
import urllib.request
import urllib.parse
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

LRCLIB_API = 'https://lrclib.net/api/get'


def sanitize_filename(name):
    """Replace characters that are invalid in filenames."""
    return re.sub(r'[\\/:*?"<>|]', '_', name)


def _lyrics_base(track, album):
    """Return (lyrics_dir, base_name) for a track."""
    title = sanitize_filename(track.title or 'unknown')
    num = getattr(track, 'tracknumber', 0) or 0
    lyrics_dir = Path(album.path) / 'lyrics'
    lyrics_dir.mkdir(exist_ok=True)
    base = f'{num:02d}_{title}'
    return lyrics_dir, base


def lyrics_path_for_track(track, album):
    """Return the cached lyrics path (.lrc preferred, then .txt)."""
    lyrics_dir, base = _lyrics_base(track, album)
    lrc = lyrics_dir / f'{base}.lrc'
    if lrc.exists():
        return lrc
    txt = lyrics_dir / f'{base}.txt'
    return txt


class LyricsFetchThread(QThread):
    """Fetch lyrics from LRCLIB in background, save to disk."""
    finished = pyqtSignal(str, str)  # (file_path, lyrics_text)

    def __init__(self, artist, track_title, album_title, track, album):
        super().__init__()
        self.artist = artist or ''
        self.track_title = track_title or ''
        self.album_title = album_title or ''
        self.track = track
        self.album = album

    def run(self):
        # Check cache first
        cached = lyrics_path_for_track(self.track, self.album)
        if cached.exists():
            text = cached.read_text(encoding='utf-8')
            self.finished.emit(str(cached), text)
            return

        # Query LRCLIB
        params = urllib.parse.urlencode({
            'artist_name': self.artist,
            'track_name': self.track_title,
            'album_name': self.album_title,
        })
        url = f'{LRCLIB_API}?{params}'

        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'lp-music-player/1.0',
            })
            data = urllib.request.urlopen(req, timeout=10).read()
            result = json.loads(data)

            # Prefer synced lyrics
            synced = result.get('syncedLyrics') or ''
            plain = result.get('plainLyrics') or ''

            lyrics_dir, base = _lyrics_base(self.track, self.album)

            if synced:
                path = lyrics_dir / f'{base}.lrc'
                path.write_text(synced, encoding='utf-8')
                self.finished.emit(str(path), synced)
            elif plain:
                path = lyrics_dir / f'{base}.txt'
                path.write_text(plain, encoding='utf-8')
                self.finished.emit(str(path), plain)
            else:
                self.finished.emit('', '')
        except Exception as e:
            print(f'Lyrics fetch error: {e}')
            self.finished.emit('', '')
