# play_log — the listening history: append-only JSONL of counted plays,
# plus the pure aggregation behind the /stats page.
#
# Deliberately Qt-free: App appends from the UI thread, the media server's
# handler threads append (phone beacons) and read (stats API), and the CLI
# below works standalone — all three must agree on paths and locking, so
# the data dir is computed here without QStandardPaths.
#
# A play "counts" by the Last.fm scrobble rule: at least half the track, or
# 4 minutes, of *actual* listening time (an accumulator ticked while audio
# advances — seeking around never inflates it).
#
# CLI:
#   python src/play_log.py --stats [YYYY] [--file F]     # aggregate report
#   python src/play_log.py --fake 500 --out F            # synthetic log

import argparse
import json
import os
import sys
import threading
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

_LOCK = threading.Lock()

COUNT_SECONDS = 240          # absolute threshold (the "4 minutes" rule)
COUNT_FRACTION = 0.5         # fraction-of-track threshold


def data_dir():
    """Per-user app data dir (created on demand): the JSONL log and the
    artist-image cache live here, next door to QSettings' identity."""
    if sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    elif sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA',
                                   Path.home() / 'AppData' / 'Local'))
    else:
        base = Path(os.environ.get('XDG_DATA_HOME',
                                   Path.home() / '.local' / 'share'))
    d = base / 'lp' / 'music-player'
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_path():
    return data_dir() / 'plays.jsonl'


def should_count(length, listened):
    """The scrobble rule. Tracks with unknown length only count via the
    absolute threshold."""
    if listened >= COUNT_SECONDS:
        return True
    return length > 0 and listened >= COUNT_FRACTION * length


def make_record(*, artist, album, title, n, length, listened, album_id):
    return {
        'ts': datetime.now().astimezone().isoformat(timespec='seconds'),
        'artist': artist or '',
        'album': album or '',
        'title': title or '',
        'n': n or 0,
        'length': round(float(length or 0), 1),
        'listened': round(float(listened or 0), 1),
        'album_id': album_id,
    }


def append(record, path=None):
    p = Path(path) if path else log_path()
    line = json.dumps(record, ensure_ascii=False)
    with _LOCK:
        with open(p, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def load(path=None):
    p = Path(path) if path else log_path()
    records = []
    try:
        with open(p, encoding='utf-8') as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue    # torn/garbled line — skip
                if isinstance(rec, dict) and rec.get('ts'):
                    records.append(rec)
    except OSError:
        pass
    return records


# ── aggregation (pure) ─────────────────────────────────────────────

def _top(counter, n):
    return sorted(counter.values(),
                  key=lambda v: (-v['plays'], -v.get('minutes', 0)))[:n]


def aggregate(records, year=None):
    """The /stats payload. 'minutes' is summed *listened* time — what was
    actually heard, not track lengths."""
    available_years = sorted({r['ts'][:4] for r in records}, reverse=True)
    available_years = [int(y) for y in available_years if y.isdigit()]
    if year is not None:
        records = [r for r in records if r['ts'][:4] == str(year)]

    artists = {}
    albums = {}
    tracks = {}
    minutes_by_month = [0.0] * 12
    plays_by_hour = [0] * 24
    day_minutes = defaultdict(float)

    for r in records:
        mins = (r.get('listened') or 0) / 60.0
        artist = r.get('artist') or 'Unknown'
        album_key = r.get('album_id') or (artist, r.get('album') or '')
        track_key = (artist, r.get('title') or '')

        a = artists.setdefault(artist, {
            'name': artist, 'plays': 0, 'minutes': 0.0, 'album_ids': []})
        a['plays'] += 1
        a['minutes'] += mins
        if r.get('album_id') and r['album_id'] not in a['album_ids']:
            a['album_ids'].append(r['album_id'])

        al = albums.setdefault(album_key, {
            'id': r.get('album_id'), 'title': r.get('album') or '',
            'artist': artist, 'plays': 0, 'minutes': 0.0})
        al['plays'] += 1
        al['minutes'] += mins

        t = tracks.setdefault(track_key, {
            'title': r.get('title') or '', 'artist': artist, 'plays': 0,
            'album_id': r.get('album_id')})
        t['plays'] += 1

        try:
            ts = datetime.fromisoformat(r['ts'])
            minutes_by_month[ts.month - 1] += mins
            plays_by_hour[ts.hour] += 1
            day_minutes[ts.date()] += mins
        except ValueError:
            pass

    top_artists = _top(artists, 8)
    top_tracks = _top(tracks, 10)

    peak_day = None
    if day_minutes:
        d, m = max(day_minutes.items(), key=lambda kv: kv[1])
        peak_day = {'date': d.isoformat(), 'minutes': round(m, 1)}

    streak = None
    if day_minutes:
        days = sorted(day_minutes)
        best_start = run_start = days[0]
        best_len = run_len = 1
        for prev, cur in zip(days, days[1:]):
            if cur - prev == timedelta(days=1):
                run_len += 1
            else:
                run_start, run_len = cur, 1
            if run_len > best_len:
                best_len, best_start = run_len, run_start
        streak = {'days': best_len, 'start': best_start.isoformat(),
                  'end': (best_start + timedelta(days=best_len - 1)).isoformat()}

    top_artist_names = {a['name'] for a in top_artists}
    deep_cut = next((t for t in _top(tracks, len(tracks))
                     if t['artist'] not in top_artist_names), None)

    return {
        'year': year,
        'available_years': available_years,
        'totals': {
            'plays': len(records),
            'minutes': round(sum((r.get('listened') or 0) for r in records) / 60.0, 1),
            'artists': len(artists),
            'albums': len(albums),
            'tracks': len(tracks),
        },
        'top_artists': [dict(a, minutes=round(a['minutes'], 1)) for a in top_artists],
        'top_albums': [dict(a, minutes=round(a['minutes'], 1)) for a in _top(albums, 12)],
        'top_tracks': top_tracks,
        'minutes_by_month': [round(m, 1) for m in minutes_by_month],
        'plays_by_hour': plays_by_hour,
        'peak_day': peak_day,
        'streak': streak,
        'deep_cut': deep_cut,
    }


# ── CLI ────────────────────────────────────────────────────────────

def _write_fakes(n, out):
    """Synthetic log for developing the stats page — never the real log."""
    import random
    fake = [
        ('Adrianne Lenker', '2018 Abysskiss', 'Adrianne Lenker/2018 Abysskiss',
         ['Terminal Paradise', 'Cradle', 'Symbol', 'Womb', 'Blue and Red Horses']),
        ('Radiohead', 'In Rainbows', 'Radiohead/In Rainbows',
         ['15 Step', 'Nude', 'Reckoner', 'Weird Fishes', 'All I Need']),
        ('The Band', 'The Band', 'The Band/1969 The Band',
         ['Rag Mama Rag', 'Up on Cripple Creek', 'Whispering Pines']),
        ('Air', 'Moon Safari', 'Air/Albums/Air - 1998 - Moon Safari',
         ['La Femme d’Argent', 'Sexy Boy', 'All I Need', 'Kelly Watch the Stars']),
        ('Carly Rae Jepsen', 'Emotion', None,
         ['Run Away with Me', 'Boy Problems', 'Your Type']),
        ('Neil Young', 'Harvest', 'Neil Young/1972 - Harvest',
         ['Heart of Gold', 'Old Man', 'The Needle and the Damage Done']),
    ]
    now = datetime.now().astimezone()
    with open(out, 'w', encoding='utf-8') as f:
        for _ in range(n):
            artist, album, album_id, titles = random.choice(fake)
            title = random.choice(titles)
            length = random.uniform(150, 420)
            listened = random.uniform(0.55, 1.0) * length
            ts = now - timedelta(days=random.random() * 730,
                                 hours=random.random() * 24)
            # cluster listening into evenings a bit so plays_by_hour looks real
            ts = ts.replace(hour=random.choice(
                [8, 9, 12, 17, 18, 19, 20, 20, 21, 21, 22, 23]))
            rec = {
                'ts': ts.isoformat(timespec='seconds'),
                'artist': artist, 'album': album, 'title': title,
                'n': titles.index(title) + 1,
                'length': round(length, 1), 'listened': round(listened, 1),
                'album_id': album_id, 'src': 'fake',
            }
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(f'wrote {n} fake records to {out}')


def main():
    ap = argparse.ArgumentParser(description='lp play log tools')
    ap.add_argument('--stats', nargs='?', const='all', metavar='YYYY',
                    help='print aggregate stats (optionally for one year)')
    ap.add_argument('--file', help='log file (default: the real log)')
    ap.add_argument('--fake', type=int, metavar='N',
                    help='write N synthetic records (requires --out)')
    ap.add_argument('--out', help='output file for --fake')
    args = ap.parse_args()
    if args.fake:
        if not args.out:
            ap.error('--fake requires --out (refusing to touch the real log)')
        _write_fakes(args.fake, args.out)
        return
    if args.stats:
        year = None if args.stats == 'all' else int(args.stats)
        print(json.dumps(aggregate(load(args.file), year), indent=2,
                         ensure_ascii=False))
        return
    ap.print_help()


if __name__ == '__main__':
    main()
