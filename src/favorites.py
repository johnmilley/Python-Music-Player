# favorites — persistent store for favourited tracks and the playlists
# built from them.
#
# Deliberately Qt-free (same reasoning as play_log): one JSON file in the
# app data dir, written atomically on every mutation. Favourites are the
# pool: playlists only reference favourite tracks by path, so unfavouriting
# a song also removes it from every playlist.
#
# File shape (<appdata>/favorites.json):
#   {
#     "favorites": [ {path, title, artist, album, tracknumber,
#                     length, filename, year}, ... ],        # insertion order
#     "playlists": { "name": [path, ...], ... }               # user order
#   }

import json
import threading
from pathlib import Path

from play_log import data_dir

_LOCK = threading.Lock()


def store_path():
    return data_dir() / 'favorites.json'


class FavoritesStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else store_path()
        self.favorites = []   # list of dicts, insertion order
        self.playlists = {}   # name -> [favorite path, ...]
        self._by_path = {}
        self.load()

    # ── Persistence ─────────────────────────────────────────────────

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
        self.favorites = [f for f in (data.get('favorites') or [])
                          if isinstance(f, dict) and f.get('path')]
        self.playlists = {str(k): [p for p in v if isinstance(p, str)]
                          for k, v in (data.get('playlists') or {}).items()
                          if isinstance(v, list)}
        self._by_path = {f['path']: f for f in self.favorites}

    def save(self):
        payload = json.dumps({'favorites': self.favorites,
                              'playlists': self.playlists},
                             ensure_ascii=False, indent=2)
        with _LOCK:
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(payload, encoding='utf-8')
            tmp.replace(self.path)

    # ── Favourites ──────────────────────────────────────────────────

    def is_favorite(self, path):
        return str(path) in self._by_path

    def add(self, track):
        """Snapshot the track's metadata at favouriting time — no file
        parsing is ever needed to list or play favourites later."""
        rec = {'path': str(track.path),
               'title': track.title, 'artist': track.artist,
               'album': track.album, 'tracknumber': track.tracknumber,
               'length': track.length, 'filename': track.filename,
               'year': track.year}
        if rec['path'] in self._by_path:
            return
        self.favorites.append(rec)
        self._by_path[rec['path']] = rec
        self.save()

    def remove(self, path):
        path = str(path)
        if path not in self._by_path:
            return
        self.favorites = [f for f in self.favorites if f['path'] != path]
        del self._by_path[path]
        for name in self.playlists:
            self.playlists[name] = [p for p in self.playlists[name]
                                    if p != path]
        self.save()

    def toggle(self, track):
        """Flip a track's favourite state; returns True if now favourited."""
        if self.is_favorite(track.path):
            self.remove(track.path)
            return False
        self.add(track)
        return True

    # ── Playlists ───────────────────────────────────────────────────

    def playlist_names(self):
        return list(self.playlists.keys())

    def create_playlist(self, name):
        name = name.strip()
        if not name or name in self.playlists:
            return False
        self.playlists[name] = []
        self.save()
        return True

    def rename_playlist(self, old, new):
        new = new.strip()
        if old not in self.playlists or not new or new in self.playlists:
            return False
        self.playlists = {new if k == old else k: v
                          for k, v in self.playlists.items()}
        self.save()
        return True

    def delete_playlist(self, name):
        if self.playlists.pop(name, None) is not None:
            self.save()

    def in_playlist(self, name, path):
        return str(path) in self.playlists.get(name, ())

    def add_to_playlist(self, name, track):
        """Add a track to a playlist, favouriting it first if it isn't
        already (playlists only ever reference favourite tracks by path —
        see module docstring — so a song doesn't need to be favourited by
        hand before it can join a list)."""
        self.add(track)  # no-op if already a favourite
        path = str(track.path)
        pl = self.playlists.setdefault(name, [])
        if path not in pl:
            pl.append(path)
            self.save()

    def remove_from_playlist(self, name, path):
        pl = self.playlists.get(name)
        path = str(path)
        if pl and path in pl:
            pl.remove(path)
            self.save()

    def records_for(self, name=''):
        """Track records for a collection: '' = all favourites, otherwise
        the named playlist (in its stored order)."""
        if not name:
            return list(self.favorites)
        return [self._by_path[p] for p in self.playlists.get(name, ())
                if p in self._by_path]
