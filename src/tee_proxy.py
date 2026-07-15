# tee_proxy — a transparent reverse proxy in front of a Subsonic server
# (Gonic) that re-unifies the phone's activity into lp's own data files.
#
# The phone (Amperfy) points at THIS proxy instead of Gonic directly. Every
# request is forwarded upstream verbatim and the response streamed back
# unchanged — so browsing, artwork, and (critically) ranged audio streaming
# behave exactly as if the phone talked to Gonic. Three endpoints are *also*
# teed, best-effort, into the same files the desktop app owns:
#
#   /rest/star     -> FavoritesStore.add    (favorites.json)
#   /rest/unstar   -> FavoritesStore.remove (favorites.json)
#   /rest/scrobble -> play_log.append       (plays.jsonl, feeds /stats)
#
# Teeing never affects the proxied response: any error resolving/recording is
# logged and swallowed, so a hiccup here can't break playback on the phone.
#
# Both favorites.py and play_log.py are Qt-free, so this daemon imports them
# directly — one source of truth for the on-disk formats, no re-implementation.
#
# ID resolution goes through the *upstream Subsonic API* (getSong), reusing
# the credentials the phone already put on the request — a stable contract
# that doesn't couple us to Gonic's private DB schema, and that keeps working
# if the backing server is ever swapped. Gonic returns Child.path relative to
# its music root; joined onto the real library root it equals the absolute
# path the desktop stores, and its POSIX dirname is the album_id /stats keys.
#
# Standalone, stdlib only (plus the two Qt-free modules):
#   python src/tee_proxy.py --library-root /mnt/media/02_PLEX_MEDIA/music \
#       --listen-port 4748 --upstream-port 4747

import argparse
import http.client
import json
import os
import posixpath
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import play_log
from favorites import FavoritesStore

# Hop-by-hop headers must not be forwarded across a proxy (RFC 7230 §6.1).
# Transfer-Encoding is included: http.client de-chunks on read, so we always
# re-frame the body ourselves (Content-Length passthrough or buffered length).
_HOP = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
        'te', 'trailers', 'transfer-encoding', 'upgrade'}

# Endpoints we tee. Subsonic allows a bare name or a `.view` suffix.
_TEE_ENDPOINTS = {'star', 'unstar', 'scrobble'}

_CHUNK = 65536

# favorites.json is a read-modify-write file; serialize tee mutations so two
# rapid phone actions can't interleave a lost update. (play_log append is
# already atomic under its own lock.)
_TEE_LOCK = threading.Lock()


class _Config:
    upstream_host = '127.0.0.1'
    upstream_port = 4747
    library_root = '/mnt/media/02_PLEX_MEDIA/music'


CFG = _Config()


def _log(msg):
    print(f'[tee] {msg}', file=sys.stderr, flush=True)


# ── upstream helpers ────────────────────────────────────────────────

def _upstream_conn(timeout=30):
    return http.client.HTTPConnection(CFG.upstream_host, CFG.upstream_port,
                                      timeout=timeout)


def _auth_params(params):
    """The subset of the phone's query params needed to re-authenticate a
    server-side getSong call (token auth: u+t+s; or legacy u+p)."""
    out = {}
    for k in ('u', 't', 's', 'p', 'c', 'v'):
        if k in params:
            out[k] = params[k][0]
    out.setdefault('c', 'lp-tee')
    out.setdefault('v', '1.16.1')
    out['f'] = 'json'
    return out


def _get_song(song_id, auth):
    """Resolve a Subsonic track id to its Child dict via upstream getSong,
    or None on any failure."""
    q = dict(auth)
    q['id'] = song_id
    conn = _upstream_conn()
    try:
        conn.request('GET', '/rest/getSong.view?' + urlencode(q))
        resp = conn.getresponse()
        body = resp.read()
        if resp.status != 200:
            return None
        data = json.loads(body).get('subsonic-response', {})
        if data.get('status') != 'ok':
            return None
        return data.get('song')
    except Exception as e:
        _log(f'getSong({song_id}) failed: {e}')
        return None
    finally:
        conn.close()


def _child_to_track(child):
    """Turn a Subsonic Child into (track-like object, album_id) using the
    real library root. Returns (None, None) if the path can't be resolved."""
    rel = (child.get('path') or '').lstrip('/')
    if not rel:
        return None, None
    abspath = os.path.join(CFG.library_root, *rel.split('/'))
    album_id = posixpath.dirname(rel)
    track = SimpleNamespace(
        path=abspath,
        title=child.get('title') or '',
        artist=child.get('artist') or '',
        album=child.get('album') or '',
        tracknumber=child.get('track') or 0,
        length=child.get('duration') or 0,
        filename=posixpath.basename(rel),
        year=child.get('year') or '',
    )
    return track, album_id


# ── tee actions ─────────────────────────────────────────────────────

def _tee(endpoint, params):
    """Best-effort mirror of a star/unstar/scrobble into lp's files."""
    ids = [i for i in params.get('id', []) if i.startswith('tr-')]
    if not ids:
        return  # album/artist stars have no desktop equivalent — ignore
    if endpoint == 'scrobble' and \
            (params.get('submission', ['true'])[0].lower() == 'false'):
        return  # "now playing" ping, not a completed play

    auth = _auth_params(params)
    with _TEE_LOCK:
        store = FavoritesStore() if endpoint in ('star', 'unstar') else None
        for song_id in ids:
            child = _get_song(song_id, auth)
            if not child:
                continue
            track, album_id = _child_to_track(child)
            if track is None:
                continue
            if endpoint == 'star':
                store.add(track)
                _log(f'★ favourited {track.path}')
            elif endpoint == 'unstar':
                store.remove(track.path)
                _log(f'☆ unfavourited {track.path}')
            else:  # scrobble — a completed play the client already counted.
                # We don't get actual seconds-listened over Subsonic, so log
                # the full track length (documented fidelity loss).
                length = float(track.length or 0)
                play_log.append(play_log.make_record(
                    artist=track.artist, album=track.album, title=track.title,
                    n=track.tracknumber, length=length, listened=length,
                    album_id=album_id))
                _log(f'▶ logged play {track.artist} — {track.title}')


# ── proxy handler ───────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'lp-tee'

    def log_message(self, *a):
        pass  # quiet by default; tee actions log themselves

    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_HEAD(self):
        self._proxy()

    def _proxy(self):
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else None

        conn = _upstream_conn(timeout=300)
        try:
            fwd = {k: v for k, v in self.headers.items()
                   if k.lower() not in _HOP}
            fwd['Host'] = f'{CFG.upstream_host}:{CFG.upstream_port}'
            conn.request(self.command, self.path, body=body, headers=fwd)
            resp = conn.getresponse()
        except Exception as e:
            _log(f'upstream error for {self.path}: {e}')
            self.send_error(502, 'Bad Gateway')
            conn.close()
            return

        try:
            self._relay(resp)
        finally:
            conn.close()

        # Tee only after the client response is fully sent, and never let it
        # raise into the connection.
        try:
            self._maybe_tee(body)
        except Exception:
            _log('tee failed:\n' + traceback.format_exc())

    def _relay(self, resp):
        """Stream an upstream response back to the client, preserving status,
        headers, and (for ranged/audio responses) exact Content-Length."""
        self.send_response_only(resp.status, resp.reason)
        content_length = resp.getheader('Content-Length')
        buffered = None
        for k, v in resp.getheaders():
            if k.lower() in _HOP:
                continue
            self.send_header(k, v)
        if self.command == 'HEAD':
            self.end_headers()
            return
        if content_length is None:
            # Chunked/unframed upstream (small JSON): buffer to length so the
            # keep-alive connection stays correctly framed.
            buffered = resp.read()
            self.send_header('Content-Length', str(len(buffered)))
        self.end_headers()

        if buffered is not None:
            self.wfile.write(buffered)
            return
        remaining = int(content_length)
        while remaining > 0:
            chunk = resp.read(min(_CHUNK, remaining))
            if not chunk:
                # Upstream ended before Content-Length was satisfied: the
                # client socket is now under-filled, so don't reuse it.
                self.close_connection = True
                break
            self.wfile.write(chunk)
            remaining -= len(chunk)

    def _maybe_tee(self, body):
        split = urlsplit(self.path)
        endpoint = split.path.rsplit('/', 1)[-1]
        if endpoint.endswith('.view'):
            endpoint = endpoint[:-5]
        if endpoint not in _TEE_ENDPOINTS:
            return
        params = parse_qs(split.query)
        if body:  # merge POST form params (Amperfy uses GET, but be safe)
            for k, v in parse_qs(body.decode('utf-8', 'replace')).items():
                params.setdefault(k, []).extend(v)
        _tee(endpoint, params)


def main():
    ap = argparse.ArgumentParser(description='lp Subsonic tee proxy')
    ap.add_argument('--listen-host', default='127.0.0.1')
    ap.add_argument('--listen-port', type=int, default=4748)
    ap.add_argument('--upstream-host', default='127.0.0.1')
    ap.add_argument('--upstream-port', type=int, default=4747)
    ap.add_argument('--library-root',
                    default=os.environ.get('LP_LIBRARY_ROOT',
                                           _Config.library_root),
                    help='absolute path the /music mount maps to on disk')
    args = ap.parse_args()

    CFG.upstream_host = args.upstream_host
    CFG.upstream_port = args.upstream_port
    CFG.library_root = args.library_root

    httpd = ThreadingHTTPServer((args.listen_host, args.listen_port), Handler)
    _log(f'listening on {args.listen_host}:{args.listen_port} -> '
         f'{CFG.upstream_host}:{CFG.upstream_port}, '
         f'library_root={CFG.library_root}')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
