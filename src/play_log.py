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
    ranked = sorted(counter.values(),
                    key=lambda v: (-v['plays'], -v.get('minutes', 0)))
    return ranked if n is None else ranked[:n]


def album_key(r):
    """Stable drill-down key: the library album id, or (for plays logged
    without one — phone/Subsonic) the artist + album name."""
    return r.get('album_id') or ('name:%s/%s' % (r.get('artist') or 'Unknown',
                                                 r.get('album') or ''))


def matches(r, period=None, artist=None, album=None, title=None):
    """Filter predicate shared by the stats and history APIs. `period` is a
    prefix of the ISO timestamp: '2026', '2026-03' or '2026-03-14'."""
    if period and not r['ts'].startswith(period):
        return False
    if artist is not None and (r.get('artist') or 'Unknown') != artist:
        return False
    if album is not None and album_key(r) != album:
        return False
    if title is not None and (r.get('title') or '') != title:
        return False
    return True


def history(records, offset=0, limit=50, **filters):
    """Newest-first slice of individual plays matching `filters`."""
    hits = [r for r in records if matches(r, **filters)]
    hits.sort(key=lambda r: r['ts'], reverse=True)
    return {'total': len(hits),
            'plays': [dict(r, album_key=album_key(r))
                      for r in hits[offset:offset + limit]]}


def _round(d, *keys):
    return dict(d, **{k: round(d[k], 1) for k in keys})


def aggregate(records, year=None, *, period=None, artist=None, album=None,
              title=None, limit=None):
    """The /stats payload. 'minutes' is summed *listened* time — what was
    actually heard, not track lengths. Filters narrow the records (the
    drill-down views); `limit` overrides the default top-N list sizes."""
    available_years = sorted({r['ts'][:4] for r in records}, reverse=True)
    available_years = [int(y) for y in available_years if y.isdigit()]
    if year is not None and not period:
        period = str(year)

    # First-ever play per artist, over the *unfiltered* log, so "new
    # artists this year" means new to you, not new to the filtered slice.
    first_seen = {}
    for r in records:
        a = r.get('artist') or 'Unknown'
        if a not in first_seen or r['ts'] < first_seen[a]:
            first_seen[a] = r['ts']

    records = [r for r in records
               if matches(r, period, artist, album, title)]

    artists = {}
    albums = {}
    tracks = {}
    minutes_by_month = [0.0] * 12
    minutes_by_year = defaultdict(float)
    plays_by_hour = [0] * 24
    plays_by_weekday = [0] * 7          # Monday first
    day_minutes = defaultdict(float)
    by_source = defaultdict(int)
    completion = []

    def touch(d, ts):
        if not d.get('first') or ts < d['first']:
            d['first'] = ts
        if not d.get('last') or ts > d['last']:
            d['last'] = ts

    for r in records:
        mins = (r.get('listened') or 0) / 60.0
        artist_name = r.get('artist') or 'Unknown'
        akey = album_key(r)
        track_key = (artist_name, r.get('title') or '')

        a = artists.setdefault(artist_name, {
            'name': artist_name, 'plays': 0, 'minutes': 0.0, 'album_ids': [],
            'albums': set(), 'tracks': set()})
        a['plays'] += 1
        a['minutes'] += mins
        a['albums'].add(akey)
        a['tracks'].add(track_key)
        if r.get('album_id') and r['album_id'] not in a['album_ids']:
            a['album_ids'].append(r['album_id'])
        touch(a, r['ts'])

        al = albums.setdefault(akey, {
            'key': akey, 'id': r.get('album_id'),
            'title': r.get('album') or '', 'artist': artist_name,
            'plays': 0, 'minutes': 0.0, 'tracks': set()})
        al['plays'] += 1
        al['minutes'] += mins
        al['tracks'].add(track_key)
        touch(al, r['ts'])

        t = tracks.setdefault(track_key, {
            'title': r.get('title') or '', 'artist': artist_name, 'plays': 0,
            'minutes': 0.0, 'album_id': r.get('album_id'), 'album_key': akey,
            'album': r.get('album') or '', 'n': r.get('n') or 0})
        t['plays'] += 1
        t['minutes'] += mins
        touch(t, r['ts'])

        by_source[r.get('src') or 'other'] += 1     # pre-src logs, Subsonic tee
        length = r.get('length') or 0
        if length > 0:
            completion.append(min(1.0, (r.get('listened') or 0) / length))

        try:
            ts = datetime.fromisoformat(r['ts'])
            minutes_by_month[ts.month - 1] += mins
            minutes_by_year[ts.year] += mins
            plays_by_hour[ts.hour] += 1
            plays_by_weekday[ts.weekday()] += 1
            day_minutes[ts.date()] += mins
        except ValueError:
            pass

    top_artists = _top(artists, limit or 8)
    top_tracks = _top(tracks, limit or 10)

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

    top_artist_names = {a['name'] for a in top_artists[:8]}
    deep_cut = next((t for t in _top(tracks, None)
                     if t['artist'] not in top_artist_names), None)

    stamps = [r['ts'] for r in records]
    new_artists = sorted((a for a in artists.values()
                          if first_seen.get(a['name']) == a['first']),
                         key=lambda a: a['first'])
    total_minutes = sum((r.get('listened') or 0) for r in records) / 60.0

    def artist_out(a):
        return dict(_round(a, 'minutes'), albums=len(a['albums']),
                    tracks=len(a['tracks']))

    def album_out(al):
        return dict(_round(al, 'minutes'), tracks=len(al['tracks']))

    return {
        'year': year,
        'period': period,
        'filters': {'artist': artist, 'album': album, 'title': title},
        'available_years': available_years,
        'totals': {
            'plays': len(records),
            'minutes': round(total_minutes, 1),
            'artists': len(artists),
            'albums': len(albums),
            'tracks': len(tracks),
            'active_days': len(day_minutes),
            'new_artists': len(new_artists),
            'first': min(stamps) if stamps else None,
            'last': max(stamps) if stamps else None,
            'completion': (round(sum(completion) / len(completion), 3)
                           if completion else None),
        },
        'top_artists': [artist_out(a) for a in top_artists],
        'top_albums': [album_out(a) for a in _top(albums, limit or 12)],
        'top_tracks': [_round(t, 'minutes') for t in top_tracks],
        'new_artists': [{'name': a['name'], 'first': a['first'],
                         'plays': a['plays'], 'album_ids': a['album_ids']}
                        for a in new_artists[:limit or 12]],
        'minutes_by_month': [round(m, 1) for m in minutes_by_month],
        'minutes_by_year': {str(y): round(m, 1)
                            for y, m in sorted(minutes_by_year.items())},
        'minutes_by_day': {d.isoformat(): round(m, 1)
                           for d, m in sorted(day_minutes.items())},
        'plays_by_hour': plays_by_hour,
        'plays_by_weekday': plays_by_weekday,
        'by_source': dict(by_source),
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
