# MediaServer — LAN/tailnet HTTP server for phone streaming.
#
# Plain threading, not Qt: handlers only read disk (via album.Album) and a
# few strings stashed on the server object, so the server never touches the
# UI thread and App just owns start()/stop(). Bound to 0.0.0.0 it is
# reachable on the LAN IP and on a Tailscale 100.x address with no Tailscale
# integration here at all. Auth is a short shared token passed as ?token= —
# a query param because <audio src>/<img src> can't set headers. Album ids
# are POSIX paths relative to library_root; _resolve() containment-checks
# every one, so absolute paths never cross the wire in either direction.
#
# Runs standalone for curl testing:
#   python src/media_server.py --root ~/Music --port 8642 --token test

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from album import Album
from favorites import FavoritesStore
import play_log

DEFAULT_PORT = 8642
CHUNK = 64 * 1024
CACHE_TTL = 30  # seconds between library re-walks

AUDIO_TYPES = {'.flac': 'audio/flac', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4'}
IMAGE_TYPES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}
STATIC_TYPES = {
    'index.html': 'text/html; charset=utf-8',
    'app.js': 'application/javascript; charset=utf-8',
    'style.css': 'text/css; charset=utf-8',
    'manifest.webmanifest': 'application/manifest+json',
    'icon.png': 'image/png',
    'stats.html': 'text/html; charset=utf-8',
    'stats.js': 'application/javascript; charset=utf-8',
    'stats.css': 'text/css; charset=utf-8',
}

# One-at-a-time Deezer fetches: the stats page requests a handful of artist
# images at once; the lock prevents duplicate downloads of the same artist.
_ARTIST_FETCH_LOCK = threading.Lock()

if getattr(sys, '_MEIPASS', None):
    WEBCLIENT_DIR = Path(sys._MEIPASS) / 'webclient'
else:
    WEBCLIENT_DIR = Path(__file__).parent / 'webclient'


def generate_token():
    """A short, phone-typeable shared token (8 url-safe chars)."""
    return secrets.token_urlsafe(6)


def _probe_ip(target):
    """Local IP the OS would use to reach `target` (UDP connect sends no
    packets — it just resolves the route)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target, 1))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def local_addresses():
    """[(label, ip)] for the URLs dialog: the default-route LAN address and,
    if Tailscale is up, the 100.x tailnet address."""
    found = []
    for target in ('8.8.8.8', '100.100.100.100'):
        ip = _probe_ip(target)
        if not ip or any(ip == have for _, have in found):
            continue
        try:
            ts = ipaddress.ip_address(ip) in ipaddress.ip_network('100.64.0.0/10')
        except ValueError:
            continue
        found.append(('Tailscale' if ts else 'LAN', ip))
    return found


class _LibraryCache:
    """Album-folder listing, stale-while-revalidate: a request never waits
    on a re-walk once a listing exists — it gets the cached list and a
    background thread refreshes when older than CACHE_TTL. Matters because
    walking a big library on a network mount can take tens of seconds.
    A folder is an album if any direct child is an audio file — the same
    rule as the desktop folder view."""

    def __init__(self):
        self._lock = threading.Lock()
        self._albums = None   # None = never walked
        self._stamp = 0.0
        self._root = None
        self._refreshing = False

    def invalidate(self):
        with self._lock:
            self._albums = None
            self._stamp = 0.0

    def warm(self, root):
        """Kick off the first walk without blocking (called at start())."""
        threading.Thread(target=self.albums, args=(root,),
                         name='lp-library-warmup', daemon=True).start()

    def albums(self, root):
        with self._lock:
            if self._albums is not None and self._root == root:
                stale = (time.monotonic() - self._stamp) >= CACHE_TTL
                if stale and not self._refreshing:
                    self._refreshing = True
                    threading.Thread(target=self._refresh, args=(root,),
                                     name='lp-library-refresh',
                                     daemon=True).start()
                return self._albums
        # Never walked (or root changed): this request pays for the walk.
        albums = self._walk(root)
        with self._lock:
            self._albums = albums
            self._stamp = time.monotonic()
            self._root = root
            return self._albums

    def _refresh(self, root):
        try:
            albums = self._walk(root)
            with self._lock:
                # A root change while walking wins over this stale result
                if self._root in (root, None):
                    self._albums = albums
                    self._stamp = time.monotonic()
                    self._root = root
        finally:
            with self._lock:
                self._refreshing = False

    @staticmethod
    def _walk(root):
        albums = []
        root_path = Path(root)
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames.sort()
            if not any(f.lower().endswith(tuple(AUDIO_TYPES)) for f in filenames):
                continue
            rel = Path(dirpath).relative_to(root_path)
            if rel == Path('.'):
                rel_id, parent = root_path.name, ''
            else:
                rel_id = rel.as_posix()
                parent = rel.parent.as_posix() if rel.parent != Path('.') else ''
            albums.append({
                'id': rel.as_posix() if rel != Path('.') else '.',
                'name': rel_id if rel == Path('.') else rel.name,
                'parent': parent,
                'art': 'cover.jpg' in filenames,
            })
        albums.sort(key=lambda a: a['id'].lower())
        return albums


class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'  # keep-alive; Content-Length always set

    # The app runs windowed (console=False) and phones abort connections on
    # every seek — silence both request logging and error spam.
    def log_message(self, *args):
        pass

    # ── plumbing ────────────────────────────────────────────────────

    def _check_token(self, query):
        supplied = (query.get('token') or [''])[0]
        return hmac.compare_digest(supplied, self.server.token)

    def _resolve(self, rel):
        """Resolve a client-supplied relative id against library_root; raise
        ValueError unless the result stays inside it."""
        base = Path(self.server.library_root).resolve()
        target = (base / rel).resolve()
        if target != base and not target.is_relative_to(base):
            raise ValueError(rel)
        return target

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _send_error_json(self, status, message):
        self._send_json({'error': message}, status)

    # ── ranged file streaming ───────────────────────────────────────

    @staticmethod
    def _parse_range(header, size):
        """Single-range parse -> (start, end) inclusive, None for 'send full
        200', or 'invalid' for an unsatisfiable range (416)."""
        if not header or not header.startswith('bytes='):
            return None
        spec = header[len('bytes='):]
        if ',' in spec:  # multi-range: RFC allows ignoring — send full
            return None
        start_s, _, end_s = spec.partition('-')
        try:
            if start_s == '' and end_s != '':      # bytes=-suffix
                suffix = int(end_s)
                if suffix <= 0:
                    return 'invalid'
                return max(0, size - suffix), size - 1
            start = int(start_s)
            if start >= size:
                return 'invalid'
            end = int(end_s) if end_s else size - 1
            if end < start:
                return None
            return start, min(end, size - 1)
        except ValueError:
            return None

    def _send_file_ranged(self, path, ctype):
        try:
            size = path.stat().st_size
        except OSError:
            self._send_error_json(404, 'not found')
            return
        rng = self._parse_range(self.headers.get('Range'), size)
        if rng == 'invalid':
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if rng is None:
            start, end, status = 0, size - 1, 200
        else:
            start, end, status = rng[0], rng[1], 206
        length = end - start + 1
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(length))
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        if self.command == 'HEAD':
            return
        try:
            with open(path, 'rb') as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            # Phones abort the connection on every seek/skip — normal.
            self.close_connection = True

    # ── routes ──────────────────────────────────────────────────────

    def do_GET(self):
        try:
            self._route()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception:
            try:
                self._send_error_json(500, 'internal error')
            except OSError:
                self.close_connection = True

    do_HEAD = do_GET

    def _route(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        # Path segments are split BEFORE unquoting so %2F inside an album id
        # stays within one segment.
        segments = [unquote(s) for s in url.path.split('/') if s]

        if url.path == '/' or url.path == '/index.html':
            return self._serve_static('index.html')
        if url.path == '/stats':
            return self._serve_static('stats.html')
        if len(segments) == 1 and segments[0] in STATIC_TYPES:
            return self._serve_static(segments[0])

        if not segments or segments[0] != 'api':
            return self._send_error_json(404, 'not found')
        if not self._check_token(query):
            return self._send_error_json(401, 'unauthorized')

        if segments[1:] == ['albums']:
            return self._api_albums()
        if segments[1:] == ['album']:
            return self._api_album(query)
        if segments[1:] == ['stats']:
            return self._api_stats(query)
        if segments[1:] == ['lyrics']:
            return self._api_lyrics(query)
        if segments[1:] == ['artist_image']:
            return self._api_artist_image(query)
        if segments[1:] == ['favorite']:
            return self._api_favorite_get(query)
        if len(segments) == 4 and segments[1] in ('stream', 'art'):
            return self._api_file(segments[1], segments[2], segments[3])
        return self._send_error_json(404, 'not found')

    def do_POST(self):
        try:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path not in ('/api/played', '/api/favorite'):
                return self._send_error_json(404, 'not found')
            if not self._check_token(query):
                return self._send_error_json(401, 'unauthorized')
            if url.path == '/api/favorite':
                return self._api_favorite_toggle()
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 8192:
                return self._send_error_json(400, 'bad body')
            try:
                data = json.loads(self.rfile.read(length))
                # Whitelist + clamp: the record is client-supplied, the
                # timestamp is not
                record = play_log.make_record(
                    artist=str(data.get('artist', ''))[:300],
                    album=str(data.get('album', ''))[:300],
                    title=str(data.get('title', ''))[:300],
                    n=int(data.get('n') or 0),
                    length=float(data.get('length') or 0),
                    listened=float(data.get('listened') or 0),
                    album_id=(str(data['album_id'])[:500]
                              if data.get('album_id') else None))
            except (ValueError, TypeError, json.JSONDecodeError):
                return self._send_error_json(400, 'bad record')
            record['src'] = 'web'
            play_log.append(record, self.server.plays_path)
            self._send_json({'ok': True})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception:
            try:
                self._send_error_json(500, 'internal error')
            except OSError:
                self.close_connection = True

    def _api_lyrics(self, query):
        """Cached lyrics for a track: <album>/lyrics/NN_title.lrc|.txt —
        the same naming lyrics_fetcher writes (mirrored here read-only:
        importing it would pull Qt in, and its path helper mkdirs into the
        library, which a GET must never do)."""
        rel = (query.get('id') or [''])[0]
        n_s = (query.get('n') or ['0'])[0]
        title = (query.get('title') or [''])[0]
        if not rel or not title:
            return self._send_error_json(400, 'missing id/title')
        try:
            n = int(n_s)
            folder = self._resolve(rel)
        except (ValueError, OSError):
            return self._send_error_json(400, 'bad request')
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)
        base = folder / 'lyrics' / f'{n:02d}_{safe_title}'
        for suffix, synced in (('.lrc', True), ('.txt', False)):
            path = base.with_name(base.name + suffix)
            try:
                if path.is_file():
                    return self._send_json(
                        {'synced': synced,
                         'text': path.read_text(encoding='utf-8',
                                                errors='replace')})
            except OSError:
                pass
        return self._send_error_json(404, 'no lyrics')

    def _resolve_track(self, rel, n):
        """The track at album `rel`, tracknumber `n` — same identity the
        desktop app keys favourites by (Track.path), resolved fresh from
        disk rather than trusting a client-supplied path (mirrors _resolve's
        containment check; absolute paths never cross the wire)."""
        try:
            n = int(n)
            folder = self._resolve(rel)
        except (ValueError, OSError, TypeError):
            return None
        if not folder.is_dir():
            return None
        album = Album(folder)
        for t in album.tracklist:
            if int(t.tracknumber or 0) == n:
                return t
        return None

    def _api_favorite_get(self, query):
        rel = (query.get('id') or [''])[0]
        n = (query.get('n') or [''])[0]
        track = self._resolve_track(rel, n)
        if track is None:
            return self._send_error_json(404, 'not found')
        store = FavoritesStore(self.server.favorites_path)
        self._send_json({'favorited': store.is_favorite(track.path)})

    def _api_favorite_toggle(self):
        length = int(self.headers.get('Content-Length', 0))
        if not 0 < length <= 2048:
            return self._send_error_json(400, 'bad body')
        try:
            data = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return self._send_error_json(400, 'bad body')
        track = self._resolve_track(data.get('id', ''), data.get('n'))
        if track is None:
            return self._send_error_json(404, 'not found')
        store = FavoritesStore(self.server.favorites_path)
        self._send_json({'favorited': store.toggle(track)})

    def _api_stats(self, query):
        year_s = (query.get('year') or [''])[0]
        try:
            year = int(year_s) if year_s else None
        except ValueError:
            return self._send_error_json(400, 'bad year')
        records = play_log.load(self.server.plays_path)
        self._send_json(play_log.aggregate(records, year))

    def _api_artist_image(self, query):
        name = (query.get('name') or [''])[0].strip()
        if not name:
            return self._send_error_json(400, 'missing name')
        cache = play_log.data_dir() / 'artist_images'
        cache.mkdir(exist_ok=True)
        slug = re.sub(r'[^\w\- ]', '', name).strip().lower().replace(' ', '_')
        stem = f'{slug[:40]}_{hashlib.sha1(name.lower().encode()).hexdigest()[:8]}'
        jpg, miss = cache / f'{stem}.jpg', cache / f'{stem}.miss'
        if not jpg.is_file():
            if miss.is_file():   # negative-cached — no repeat API hits
                return self._send_error_json(404, 'no image')
            with _ARTIST_FETCH_LOCK:
                if not jpg.is_file() and not miss.is_file():
                    self._fetch_artist_image(name, jpg, miss)
            if not jpg.is_file():
                return self._send_error_json(404, 'no image')
        body = jpg.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'image/jpeg')
        self.send_header('Cache-Control', 'private, max-age=86400')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    @staticmethod
    def _fetch_artist_image(name, jpg, miss):
        """Deezer artist search (free, keyless) -> cache the photo, or a
        .miss marker so a missing artist never triggers repeat lookups."""
        import requests
        try:
            r = requests.get('https://api.deezer.com/search/artist',
                             params={'q': name, 'limit': 1}, timeout=5)
            r.raise_for_status()
            results = r.json().get('data') or []
            pic = results and (results[0].get('picture_xl')
                               or results[0].get('picture_big'))
            if not pic:
                raise ValueError('no picture')
            img = requests.get(pic, timeout=10)
            img.raise_for_status()
            tmp = jpg.with_suffix('.jpg.tmp')
            tmp.write_bytes(img.content)
            os.replace(tmp, jpg)
        except Exception:
            try:
                miss.touch()
            except OSError:
                pass

    def _serve_static(self, name):
        path = self.server.static_dir / name
        if not path.is_file():
            return self._send_error_json(404, 'not found')
        body = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', STATIC_TYPES[name])
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _api_albums(self):
        albums = self.server.cache.albums(self.server.library_root)
        self._send_json({'albums': albums})

    def _api_album(self, query):
        rel = (query.get('id') or [''])[0]
        if not rel:
            return self._send_error_json(400, 'missing id')
        try:
            folder = self._resolve(rel)
        except (ValueError, OSError):
            return self._send_error_json(400, 'bad id')
        if not folder.is_dir():
            return self._send_error_json(404, 'not found')
        album = Album(folder)
        if not album.tracklist:
            return self._send_error_json(404, 'no tracks')
        enc_id = quote(rel, safe='')
        art = [f'/api/art/{enc_id}/{quote(Path(p).name, safe="")}'
               for p in album.art_list]
        tracks = [{
            'n': t.tracknumber,
            'title': t.title or t.filename,
            'length': t.length,
            'url': f'/api/stream/{enc_id}/{quote(t.filename, safe="")}',
        } for t in album.tracklist]
        self._send_json({
            'id': rel,
            'title': album.title,
            'artist': album.artist,
            'year': album.year,
            'art': art,
            'tracks': tracks,
        })

    def _api_file(self, kind, rel, filename):
        types = AUDIO_TYPES if kind == 'stream' else IMAGE_TYPES
        ctype = types.get(Path(filename).suffix.lower())
        if ctype is None or '/' in filename or filename in ('.', '..'):
            return self._send_error_json(404, 'not found')
        try:
            folder = self._resolve(rel)
            path = (folder / filename).resolve()
            if path.parent != folder:
                raise ValueError(filename)
        except (ValueError, OSError):
            return self._send_error_json(400, 'bad path')
        if not path.is_file():
            return self._send_error_json(404, 'not found')
        self._send_file_ranged(path, ctype)


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Phones reset keep-alive sockets constantly (every seek, every
        # screen lock). That surfaces here, outside the handler — swallow
        # it; let real bugs print as usual.
        exc = sys.exception()
        if isinstance(exc, (BrokenPipeError, ConnectionResetError,
                            TimeoutError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


class MediaServer:
    """Owns the ThreadingHTTPServer + its thread. All state the handlers
    need lives on the server object (library_root/token/cache/static_dir)
    so it can be updated live without a restart."""

    def __init__(self, library_root, port=DEFAULT_PORT, token='',
                 plays_path=None, favorites_path=None):
        self.library_root = str(library_root)
        self.port = int(port)
        self.token = token or generate_token()
        self.plays_path = plays_path   # None = play_log's default location
        self.favorites_path = favorites_path   # None = FavoritesStore's default
        self._httpd = None
        self._thread = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        """Bind and serve on a daemon thread. OSError (e.g. port in use)
        propagates to the caller."""
        httpd = _Server(('0.0.0.0', self.port), _Handler)
        httpd.library_root = self.library_root
        httpd.token = self.token
        httpd.cache = _LibraryCache()
        httpd.static_dir = WEBCLIENT_DIR
        httpd.plays_path = self.plays_path
        httpd.favorites_path = self.favorites_path
        self._httpd = httpd
        self._thread = threading.Thread(
            target=httpd.serve_forever, name='lp-media-server', daemon=True)
        self._thread.start()
        # Big libraries on network mounts can take tens of seconds to walk —
        # do the first walk now so the first phone request doesn't pay it.
        httpd.cache.warm(self.library_root)

    def stop(self):
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._thread.join(2)
        self._httpd.server_close()
        self._httpd = None
        self._thread = None

    def set_library_root(self, root):
        self.library_root = str(root)
        if self._httpd is not None:
            self._httpd.library_root = self.library_root
            self._httpd.cache.invalidate()

    def set_token(self, token):
        self.token = token
        if self._httpd is not None:
            self._httpd.token = token


def main():
    ap = argparse.ArgumentParser(description='lp media server (curl test harness)')
    ap.add_argument('--root', required=True, help='music library root folder')
    ap.add_argument('--port', type=int, default=DEFAULT_PORT)
    ap.add_argument('--token', default='test')
    ap.add_argument('--plays', help='plays log file (default: the real log)')
    args = ap.parse_args()
    server = MediaServer(args.root, args.port, args.token,
                         plays_path=args.plays)
    server.start()
    print(f'serving {args.root} on port {args.port} (token: {args.token})')
    for label, ip in local_addresses():
        print(f'  {label}: http://{ip}:{args.port}/?token={args.token}')
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()


if __name__ == '__main__':
    main()
