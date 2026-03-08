# Lyrics fetcher using LRCLIB API
# Downloads plain lyrics and saves as .txt files in the album folder

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


def lyrics_path_for_track(track, album):
    """Return the expected .txt path for a track's lyrics."""
    title = sanitize_filename(track.title or 'unknown')
    num = getattr(track, 'tracknumber', 0) or 0
    lyrics_dir = Path(album.path) / 'lyrics'
    lyrics_dir.mkdir(exist_ok=True)
    filename = f'{num:02d}_{title}.txt'
    return lyrics_dir / filename


class LyricsFetchThread(QThread):
    """Fetch lyrics from LRCLIB in background, save to disk."""
    finished = pyqtSignal(str, str)  # (file_path, lyrics_text)

    def __init__(self, artist, track_title, album_title, save_path):
        super().__init__()
        self.artist = artist or ''
        self.track_title = track_title or ''
        self.album_title = album_title or ''
        self.save_path = Path(save_path)

    def run(self):
        # Check cache first
        if self.save_path.exists():
            text = self.save_path.read_text(encoding='utf-8')
            self.finished.emit(str(self.save_path), text)
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
            lyrics = result.get('plainLyrics') or ''

            if lyrics:
                self.save_path.write_text(lyrics, encoding='utf-8')
                self.finished.emit(str(self.save_path), lyrics)
            else:
                self.finished.emit('', '')
        except Exception as e:
            print(f'Lyrics fetch error: {e}')
            self.finished.emit('', '')
