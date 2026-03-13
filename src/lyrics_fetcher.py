# Lyrics fetcher using LRCLIB API
# Downloads synced (.lrc) or plain (.txt) lyrics to album folder

import json
import re
import ssl
import urllib.request
import urllib.parse
from pathlib import Path

try:
    import certifi
    _ssl_ctx = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _ssl_ctx = ssl.create_default_context()

from PyQt5.QtCore import QThread, pyqtSignal

LRCLIB_GET = 'https://lrclib.net/api/get'
LRCLIB_SEARCH = 'https://lrclib.net/api/search'


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

    @staticmethod
    def _clean(text):
        """Strip edition tags, brackets, feat. info for cleaner search."""
        text = re.sub(r'\(.*?\)|\[.*?\]', '', text)
        text = re.sub(r'\b(19|20)\d{2}\b', '', text)
        text = re.sub(r'[-_]+', ' ', text)
        return ' '.join(text.split()).strip()

    @staticmethod
    def _fetch(url):
        req = urllib.request.Request(url, headers={'User-Agent': 'lp-music-player/1.0'})
        data = urllib.request.urlopen(req, timeout=10, context=_ssl_ctx).read()
        return json.loads(data)

    def _save_and_emit(self, synced, plain):
        """Save lyrics to cache and emit result. Returns True if found."""
        lyrics_dir, base = _lyrics_base(self.track, self.album)
        if synced:
            path = lyrics_dir / f'{base}.lrc'
            path.write_text(synced, encoding='utf-8')
            self.finished.emit(str(path), synced)
            return True
        elif plain:
            path = lyrics_dir / f'{base}.txt'
            path.write_text(plain, encoding='utf-8')
            self.finished.emit(str(path), plain)
            return True
        return False

    def run(self):
        # Check cache first
        cached = lyrics_path_for_track(self.track, self.album)
        if cached.exists():
            text = cached.read_text(encoding='utf-8')
            self.finished.emit(str(cached), text)
            return

        try:
            # 1) Exact match with raw metadata
            params = urllib.parse.urlencode({
                'artist_name': self.artist,
                'track_name': self.track_title,
                'album_name': self.album_title,
            })
            try:
                result = self._fetch(f'{LRCLIB_GET}?{params}')
                if self._save_and_emit(
                    result.get('syncedLyrics', ''),
                    result.get('plainLyrics', '')
                ):
                    return
            except Exception:
                pass

            # 2) Exact match with cleaned album name
            clean_album = self._clean(self.album_title)
            if clean_album != self.album_title:
                params = urllib.parse.urlencode({
                    'artist_name': self.artist,
                    'track_name': self.track_title,
                    'album_name': clean_album,
                })
                try:
                    result = self._fetch(f'{LRCLIB_GET}?{params}')
                    if self._save_and_emit(
                        result.get('syncedLyrics', ''),
                        result.get('plainLyrics', '')
                    ):
                        return
                except Exception:
                    pass

            # 3) Search fallback — artist + track title
            clean_title = self._clean(self.track_title)
            clean_artist = self._clean(self.artist)
            q = f'{clean_artist} {clean_title}'.strip()
            if q:
                params = urllib.parse.urlencode({'q': q})
                results = self._fetch(f'{LRCLIB_SEARCH}?{params}')
                # Pick best match: prefer synced, match artist name
                artist_lower = clean_artist.lower()
                for r in results:
                    if artist_lower and artist_lower not in r.get('artistName', '').lower():
                        continue
                    synced = r.get('syncedLyrics', '')
                    plain = r.get('plainLyrics', '')
                    if self._save_and_emit(synced, plain):
                        return
                # If no artist match, try first result with lyrics
                for r in results:
                    synced = r.get('syncedLyrics', '')
                    plain = r.get('plainLyrics', '')
                    if self._save_and_emit(synced, plain):
                        return

            self.finished.emit('', '')
        except Exception as e:
            print(f'Lyrics fetch error: {e}')
            self.finished.emit('', '')
