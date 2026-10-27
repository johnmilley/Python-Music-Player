// lp stats — renders /api/stats as a year-in-review page, with drill-down.
// Charts are single-series magnitude → one validated hue (#cc7511 in CSS),
// no legend, selective labels (the peak), hover/tap tooltips on every bar.
// The calendar is sequential (one hue, opacity steps over the dark surface,
// brighter = more) and carries a less→more key.
//
// Views are addressed by the URL hash, so back/forward and bookmarks work:
//   #period=2026                 overview (period: YYYY, YYYY-MM, YYYY-MM-DD)
//   #period=2026&artist=X        an artist   (&album=KEY, &artist=X&title=T)
//   #period=2026&list=albums     full ranked list (artists|albums|tracks|new)

'use strict';

const $ = id => document.getElementById(id);

// ── token (same convention as app.js) ─────────────────────────────

let token = '';
{
  const fromUrl = new URLSearchParams(location.search).get('token');
  if (fromUrl) {
    localStorage.setItem('lp-token', fromUrl);
    history.replaceState(null, '', location.pathname + location.hash);
  }
  token = localStorage.getItem('lp-token') || '';
}
const withToken = url =>
  url + (url.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token);

async function api(path) {
  const res = await fetch(withToken(path));
  if (res.status === 401) { $('unauth').hidden = false; throw new Error('unauthorized'); }
  if (!res.ok) throw new Error('http ' + res.status);
  return res.json();
}

// ── helpers ───────────────────────────────────────────────────────

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function letterTile(name) {
  return el('div', 'letter', (name || '?').trim().charAt(0).toUpperCase());
}

// img with fallback chain: artist photo -> first album cover -> letter tile
function artistImg(name, albumIds) {
  const wrap = el('div', 'img-wrap');
  const img = document.createElement('img');
  img.alt = name;
  img.loading = 'lazy';
  let step = 0;
  img.onerror = () => {
    step += 1;
    if (step === 1 && albumIds && albumIds.length) {
      img.src = withToken('/api/art/' + encodeURIComponent(albumIds[0]) + '/cover.jpg');
    } else {
      img.replaceWith(letterTile(name));
    }
  };
  img.src = withToken('/api/artist_image?name=' + encodeURIComponent(name));
  wrap.appendChild(img);
  return wrap;
}

function coverImg(id, title) {
  if (!id) return letterTile(title);
  const img = document.createElement('img');
  img.alt = title;
  img.loading = 'lazy';
  img.onerror = () => img.replaceWith(letterTile(title));
  img.src = withToken('/api/art/' + encodeURIComponent(id) + '/cover.jpg');
  return img;
}

const fmtInt = n => Math.round(n).toLocaleString();
const plural = (n, w) => `${fmtInt(n)} ${w}${Math.round(n) === 1 ? '' : 's'}`;
const MONTHS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
  'Saturday', 'Sunday'];

// Dates are read straight off the logged ISO string (local time *where it
// was played*), never re-zoned through the browser's clock — the server
// buckets days the same way.
const dayDate = iso => new Date(iso.slice(0, 10) + 'T12:00:00');
const fmtDate = (iso, opts) => dayDate(iso).toLocaleDateString(undefined,
  opts || { month: 'short', day: 'numeric', year: 'numeric' });
const fmtTime = iso => iso.slice(11, 16);

function periodLabel(p) {
  if (!p) return 'all time';
  if (p.length === 4) return p;
  if (p.length === 7) return `${MONTH_NAMES[+p.slice(5) - 1]} ${p.slice(0, 4)}`;
  return fmtDate(p, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
}

// ── routing ───────────────────────────────────────────────────────

const ENTITY_KEYS = ['artist', 'album', 'title', 'list'];

function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  return {
    period: h.get('period'), artist: h.get('artist'), album: h.get('album'),
    title: h.get('title'), list: h.get('list'),
  };
}

let view = readHash();

// Hash for a view: entity fields replace the current ones, period carries
// over unless given.
function href(over) {
  const v = { period: view.period };
  Object.assign(v, over);
  const h = new URLSearchParams();
  ['period', ...ENTITY_KEYS].forEach(k => { if (v[k]) h.set(k, v[k]); });
  return '#' + h.toString();
}
const artistHref = name => href({ artist: name });
const albumHref = key => href({ album: key });
const trackHref = (artist, title) => href({ artist, title });

function link(cls, hash, ...children) {
  const a = el('a', cls);
  a.href = hash;
  children.forEach(c => a.appendChild(typeof c === 'string' ? document.createTextNode(c) : c));
  return a;
}

// "← back": real history when we navigated here inside the page, else the
// parent view (so a bookmarked drill-down still has somewhere to go).
let internalNavs = 0;
window.addEventListener('hashchange', () => { internalNavs += 1; route(); });

function parentHash() {
  if (view.list) return href({});
  if (view.title) return href({ artist: view.artist });
  if (view.album || view.artist) return href({});
  if (view.period && view.period.length > 4) {
    return '#period=' + view.period.slice(0, view.period.length === 10 ? 7 : 4);
  }
  return null;
}

function setupBack() {
  const back = $('back');
  const parent = parentHash();
  back.onclick = null;
  if (!parent) {
    back.href = '/';
    back.textContent = '← player';
    return;
  }
  back.href = parent;
  back.textContent = '← back';
  back.onclick = e => {
    if (internalNavs > 0) { e.preventDefault(); history.back(); }
  };
}

// ── tooltip (shared, hover + tap) ─────────────────────────────────

const tip = $('tooltip');
function showTip(target, text) {
  tip.textContent = text;
  tip.hidden = false;
  const r = target.getBoundingClientRect();
  tip.style.left = Math.min(Math.max(r.left + r.width / 2, 80), innerWidth - 80) + 'px';
  tip.style.top = r.top + 'px';
}
function hideTip() { tip.hidden = true; }
document.addEventListener('scroll', hideTip, { passive: true });

// ── bar chart (single series, flex bars) ──────────────────────────
// onPick(i) makes bars drill-down links; without it a tap shows the tip.

function barChart(container, values, labels, tipText, labelEvery, onPick) {
  container.textContent = '';
  const max = Math.max(...values, 1);
  const peakIdx = values.indexOf(Math.max(...values));

  if (values[peakIdx] > 0) {
    container.appendChild(el('div', 'peak-label', tipText(peakIdx, true)));
  }
  const bars = el('div', 'bars');
  values.forEach((v, i) => {
    const slot = el('div', 'bar-slot' + (onPick && v > 0 ? ' pick' : ''));
    const bar = el('div', 'bar');
    bar.style.height = Math.max(1, (v / max) * 100) + '%';
    slot.appendChild(bar);
    slot.addEventListener('mouseenter', () => showTip(slot, tipText(i, false)));
    slot.addEventListener('mouseleave', hideTip);
    slot.addEventListener('click', () => {
      if (onPick && v > 0) { hideTip(); onPick(i); } else showTip(slot, tipText(i, false));
    });
    bars.appendChild(slot);
  });
  container.appendChild(bars);

  const lab = el('div', 'bar-labels');
  labels.forEach((l, i) => lab.appendChild(
    el('span', '', labelEvery && i % labelEvery !== 0 ? '' : l)));
  container.appendChild(lab);
}

// ── calendar heatmap (one year, weeks × weekdays) ─────────────────

const HEAT = [0.28, 0.5, 0.75, 1];     // opacity steps of the data hue

function calendar(container, year, byDay) {
  container.textContent = '';
  const vals = Object.values(byDay).filter(v => v > 0).sort((a, b) => a - b);
  // quartile thresholds over active days, so one marathon day doesn't wash
  // out everything else
  const q = [0.25, 0.5, 0.75].map(p => vals[Math.floor(p * (vals.length - 1))] || 0);
  const level = v => (v <= 0 ? -1 : v <= q[0] ? 0 : v <= q[1] ? 1 : v <= q[2] ? 2 : 3);

  const scroller = el('div', 'cal-scroll');
  const months = el('div', 'cal-months');
  const grid = el('div', 'cal-grid');
  const jan1 = new Date(year, 0, 1);
  const lead = (jan1.getDay() + 6) % 7;            // Monday-first offset
  for (let i = 0; i < lead; i++) grid.appendChild(el('div', 'cal-cell pad'));

  const today = new Date().toISOString().slice(0, 10);
  for (let d = new Date(jan1); d.getFullYear() === year; d.setDate(d.getDate() + 1)) {
    const iso = `${year}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const idx = lead + Math.round((d - jan1) / 864e5);
    if (d.getDate() === 1) {
      const m = el('span', '', MONTH_NAMES[d.getMonth()].slice(0, 3));
      m.style.gridColumn = String(Math.floor(idx / 7) + 1);
      months.appendChild(m);
    }
    const v = byDay[iso] || 0;
    const lv = level(v);
    const cell = el(lv >= 0 ? 'a' : 'div', 'cal-cell' + (iso > today ? ' future' : ''));
    if (lv >= 0) {
      cell.href = '#period=' + iso;
      cell.style.background = `rgba(204, 117, 17, ${HEAT[lv]})`;
    }
    const text = `${fmtDate(iso, { weekday: 'short', month: 'short', day: 'numeric' })}: ` +
      (v ? plural(v, 'minute') : 'nothing');
    cell.setAttribute('aria-label', text);
    cell.addEventListener('mouseenter', () => showTip(cell, text));
    cell.addEventListener('mouseleave', hideTip);
    grid.appendChild(cell);
  }
  scroller.appendChild(months);
  scroller.appendChild(grid);
  container.appendChild(scroller);

  const key = el('div', 'cal-key');
  key.appendChild(el('span', '', 'less'));
  [null, ...HEAT].forEach(a => {
    const s = el('i', 'cal-cell');
    if (a) s.style.background = `rgba(204, 117, 17, ${a})`;
    key.appendChild(s);
  });
  key.appendChild(el('span', '', 'more'));
  container.appendChild(key);
  // land on the most recent weeks when the grid overflows (phones)
  requestAnimationFrame(() => { scroller.scrollLeft = scroller.scrollWidth; });
}

// ── shared row builder (track list, full lists, history) ──────────

function rankRow({ hash, rank, img, title, sub, value, frac }) {
  const li = el('li', 'row');
  const a = link('row-link', hash);
  if (frac !== undefined) {
    const fill = el('div', 'fill');
    fill.style.transform = `scaleX(${frac})`;
    a.appendChild(fill);
  }
  if (rank !== undefined) a.appendChild(el('span', 'r', String(rank)));
  if (img) { const w = el('span', 'thumb'); w.appendChild(img); a.appendChild(w); }
  const t = el('span', 't', title);
  if (sub) t.appendChild(el('small', '', sub));
  a.appendChild(t);
  if (value) a.appendChild(el('span', 'p', value));
  li.appendChild(a);
  return li;
}

// ── render ────────────────────────────────────────────────────────

function renderYears(years) {
  const nav = $('years');
  nav.textContent = '';
  const curYear = view.period ? view.period.slice(0, 4) : null;
  const mk = (label, y) => {
    const a = link('year-chip' + (y === curYear ? ' active' : ''),
      href({ period: y, artist: view.artist, album: view.album,
             title: view.title, list: view.list }), label);
    nav.appendChild(a);
  };
  years.forEach(y => mk(String(y), String(y)));
  mk('All time', null);
}

function show(id, on) { $(id).hidden = !on; return on; }

function setMore(section, n, shown, noun) {
  const a = $(section).querySelector('.more');
  if (!a) return;
  a.hidden = n <= shown;
  a.textContent = `All ${fmtInt(n)} ${noun} ›`;
  a.href = href({ artist: view.artist, album: view.album, list: a.dataset.list });
}

function kpi(container, label, value, hash) {
  const k = hash ? link('kpi', hash) : el('div', 'kpi');
  k.appendChild(el('div', 'v', value));
  k.appendChild(el('div', 'l', label));
  container.appendChild(k);
}

function renderHero(d) {
  const t = d.totals;
  const art = $('hero-art');
  art.textContent = '';
  const byline = $('hero-byline');
  byline.textContent = '';
  const p = periodLabel(view.period);
  let kicker = '';
  let title;

  if (view.list) {
    kicker = p;
    title = { artists: 'All artists', albums: 'All albums', tracks: 'All tracks',
              new: 'New to you' }[view.list] || 'All';
    if (view.artist) byline.appendChild(link('', artistHref(view.artist), view.artist));
    if (view.album && d.top_albums[0]) {
      byline.appendChild(link('', albumHref(view.album), d.top_albums[0].title));
    }
  } else if (view.title) {
    const tr = d.top_tracks[0];
    kicker = 'Track · ' + p;
    title = view.title;
    art.appendChild(coverImg(tr && tr.album_id, view.title));
    byline.appendChild(link('', artistHref(view.artist), view.artist));
    if (tr && tr.album) {
      byline.appendChild(document.createTextNode(' · '));
      byline.appendChild(link('', albumHref(tr.album_key), tr.album));
    }
  } else if (view.album) {
    const al = d.top_albums[0];
    kicker = 'Album · ' + p;
    title = (al && al.title) || 'Unknown album';
    art.appendChild(coverImg(al && al.id, title));
    if (al) byline.appendChild(link('', artistHref(al.artist), al.artist));
  } else if (view.artist) {
    const ar = d.top_artists[0];
    kicker = 'Artist · ' + p;
    title = view.artist;
    art.appendChild(artistImg(view.artist, ar && ar.album_ids));
    art.classList.add('round');
  } else if (view.period && view.period.length > 4) {
    title = periodLabel(view.period);
  } else {
    title = view.period ? `Your ${view.period} in music` : 'Your music, all time';
  }
  art.classList.toggle('round', !!view.artist && !view.title && !view.list);
  art.hidden = !art.children.length;
  $('hero-kicker').textContent = kicker;
  $('hero-title').textContent = title;
  byline.hidden = !byline.children.length;
  $('hero').classList.toggle('compact', !!view.list);
  $('hero').classList.toggle('detail', !view.list &&
    !!(view.artist || view.album || view.title || (view.period && view.period.length > 4)));

  $('hero-minutes').textContent = fmtInt(t.minutes);
  $('hero-sub').textContent = t.minutes >= 120
    ? `minutes · about ${fmtInt(t.minutes / 60)} hours`
    : 'minutes with your music';
  $('hero-minutes').hidden = $('hero-sub').hidden = !!view.list;

  const kpis = $('kpis');
  kpis.textContent = '';
  if (view.list) return;
  kpi(kpis, 'plays', fmtInt(t.plays));
  if (!view.artist) kpi(kpis, 'artists', fmtInt(t.artists), href({ album: view.album, list: 'artists' }));
  if (!view.album && !view.title) {
    kpi(kpis, 'albums', fmtInt(t.albums),
      href({ artist: view.artist, list: 'albums' }));
  }
  if (!view.title) {
    kpi(kpis, 'tracks', fmtInt(t.tracks),
      href({ artist: view.artist, album: view.album, list: 'tracks' }));
  }
  if (!view.period || view.period.length < 10) {
    kpi(kpis, 'days listened', fmtInt(t.active_days));
    kpi(kpis, 'min / day listened', fmtInt(t.minutes / Math.max(1, t.active_days)));
  }
  if (t.completion !== null && t.completion !== undefined) {
    kpi(kpis, 'avg. heard of a track', Math.round(t.completion * 100) + '%');
  }
  if (view.title && t.plays) {
    const tr = d.top_tracks[0];
    if (tr) kpi(kpis, 'minutes / play', (tr.minutes / tr.plays).toFixed(1));
  }
}

function renderTopArtists(d) {
  const arts = d.top_artists;
  if (!show('artist-section', !view.artist && !view.album && arts.length > 0)) return;
  const a = arts[0];
  $('top-artist').href = artistHref(a.name);
  const imgWrap = $('top-artist-img');
  imgWrap.textContent = '';
  imgWrap.appendChild(artistImg(a.name, a.album_ids));
  $('top-artist-name').textContent = a.name;
  $('top-artist-meta').textContent =
    `${plural(a.plays, 'play')} · ${plural(a.minutes, 'minute')} · ` +
    `${Math.round(100 * a.plays / d.totals.plays)}% of all plays`;
  const run = $('runners');
  run.textContent = '';
  arts.slice(1, 8).forEach(r => {
    run.appendChild(link('runner', artistHref(r.name),
      artistImg(r.name, r.album_ids), el('div', 'n', r.name),
      el('div', 'p', plural(r.plays, 'play'))));
  });
  setMore('artist-section', d.totals.artists, arts.length, 'artists');
}

function renderTopAlbums(d) {
  const albums = d.top_albums;
  if (!show('albums-section', !view.album && !view.title && albums.length > 0)) return;
  $('albums-h').textContent = view.artist ? 'Albums' : 'Top albums';
  const grid = $('album-grid');
  grid.textContent = '';
  albums.forEach((al, i) => {
    const t = link('album-tile', albumHref(al.key), coverImg(al.id, al.title),
      el('div', 'rank', '#' + (i + 1)), el('div', 't', al.title || 'Unknown album'),
      el('div', 'a', view.artist
        ? `${plural(al.plays, 'play')} · ${plural(al.tracks, 'track')}`
        : `${al.artist} · ${plural(al.plays, 'play')}`));
    grid.appendChild(t);
  });
  setMore('albums-section', d.totals.albums, albums.length, 'albums');
}

function renderTopTracks(d) {
  let tracks = d.top_tracks;
  if (!show('tracks-section', !view.title && tracks.length > 0)) return;
  // An album reads best in running order; elsewhere rank by plays.
  if (view.album) tracks = [...tracks].sort((a, b) => (a.n || 999) - (b.n || 999));
  $('tracks-h').textContent = view.album ? 'Tracks' : 'Top tracks';
  const list = $('track-list');
  list.textContent = '';
  const maxPlays = Math.max(...tracks.map(t => t.plays), 1);
  tracks.forEach((t, i) => list.appendChild(rankRow({
    hash: trackHref(t.artist, t.title),
    rank: view.album ? (t.n || '·') : i + 1,
    title: t.title || 'Untitled',
    sub: view.album ? '' : view.artist ? t.album : t.artist,
    value: plural(t.plays, 'play'),
    frac: t.plays / maxPlays,
  })));
  setMore('tracks-section', d.totals.tracks, tracks.length, 'tracks');
}

function renderNewArtists(d) {
  const n = d.totals.new_artists;
  // Only meaningful when some of the period's artists are *not* new.
  const on = !view.artist && !view.album && n > 0 && n < d.totals.artists;
  if (!show('new-section', on)) return;
  const wrap = $('new-list');
  wrap.textContent = '';
  d.new_artists.slice(0, 8).forEach(a => wrap.appendChild(
    link('runner', artistHref(a.name), artistImg(a.name, a.album_ids),
      el('div', 'n', a.name), el('div', 'p', 'since ' + fmtDate(a.first, { month: 'short', day: 'numeric' })))));
  setMore('new-section', n, 8, 'new artists');
}

function renderCharts(d) {
  const p = view.period;

  const years = Object.keys(d.minutes_by_year);
  if (show('years-section', !p && years.length > 1)) {
    const vals = years.map(y => d.minutes_by_year[y]);
    barChart($('year-chart'), vals, years,
      (i, peak) => `${peak ? 'Biggest year: ' : ''}${years[i]} — ${plural(vals[i], 'minute')}`,
      0, i => { location.hash = href({ period: years[i], artist: view.artist,
                                       album: view.album, title: view.title }); });
  }

  const months = d.minutes_by_month;
  if (show('months-section', (!p || p.length === 4) && months.some(v => v > 0))) {
    barChart($('month-chart'), months, MONTHS,
      (i, peak) => peak
        ? `Biggest month: ${MONTH_NAMES[i]} — ${plural(months[i], 'minute')}`
        : `${MONTH_NAMES[i]}: ${plural(months[i], 'minute')}`,
      0, p ? i => { location.hash = href({ period: `${p}-${String(i + 1).padStart(2, '0')}`,
        artist: view.artist, album: view.album, title: view.title }); } : null);
  }

  // A month: one bar per day, each drilling into that day.
  if (show('days-section', !!p && p.length === 7)) {
    const [y, m] = p.split('-').map(Number);
    const n = new Date(y, m, 0).getDate();
    const isos = Array.from({ length: n }, (_, i) => `${p}-${String(i + 1).padStart(2, '0')}`);
    const vals = isos.map(iso => d.minutes_by_day[iso] || 0);
    barChart($('day-chart'), vals, isos.map((_, i) => String(i + 1)),
      (i, peak) => `${peak ? 'Biggest day: ' : ''}${fmtDate(isos[i], { weekday: 'short', month: 'short', day: 'numeric' })} — ${plural(vals[i], 'minute')}`,
      5, i => { location.hash = '#period=' + isos[i]; });
  }

  // A year (or all-time with a single year of data): the full calendar.
  const calYear = p && p.length === 4 ? +p
    : !p && d.available_years.length === 1 ? d.available_years[0] : null;
  if (show('calendar-section', calYear !== null && Object.keys(d.minutes_by_day).length > 0)) {
    calendar($('calendar'), calYear, d.minutes_by_day);
  }

  const hours = d.plays_by_hour;
  if (show('hours-section', hours.filter(v => v > 0).length > 1)) {
    barChart($('hour-chart'), hours, hours.map((_, i) => String(i)),
      (i, peak) => peak
        ? `Peak hour: ${i}:00 — ${plural(hours[i], 'play')}`
        : `${i}:00 — ${plural(hours[i], 'play')}`,
      6);
  }

  const wd = d.plays_by_weekday;
  if (show('weekdays-section', (!p || p.length < 10) && wd.filter(v => v > 0).length > 1)) {
    barChart($('weekday-chart'), wd, WEEKDAYS.map(w => w.charAt(0)),
      (i, peak) => `${peak ? 'Busiest: ' : ''}${WEEKDAYS[i]}s — ${plural(wd[i], 'play')}`);
  }
}

function renderFacts(d) {
  const facts = $('facts');
  facts.textContent = '';
  const t = d.totals;
  const addFact = (l, v, s, hash) => {
    const f = hash ? link('fact', hash) : el('div', 'fact');
    f.appendChild(el('div', 'l', l));
    f.appendChild(el('div', 'v', v));
    if (s) f.appendChild(el('div', 's', s));
    facts.appendChild(f);
  };
  const day = !!view.period && view.period.length === 10;
  const entity = view.artist || view.album;

  if (d.peak_day && !day && t.active_days > 1) {
    addFact('Peak day', fmtDate(d.peak_day.date, { month: 'short', day: 'numeric', year: 'numeric' }),
      plural(d.peak_day.minutes, 'minute'), '#period=' + d.peak_day.date);
  }
  if (d.streak && d.streak.days > 1) {
    addFact('Longest streak', `${d.streak.days} days`,
      `${fmtDate(d.streak.start, { month: 'short', day: 'numeric' })} – ` +
      fmtDate(d.streak.end, { month: 'short', day: 'numeric' }));
  }
  if (d.deep_cut && !entity) {
    addFact('Deep cut', d.deep_cut.title,
      `${d.deep_cut.artist} · ${plural(d.deep_cut.plays, 'play')}`,
      trackHref(d.deep_cut.artist, d.deep_cut.title));
  }
  if (t.first && !day) {
    addFact(entity || view.title ? 'First listen' : 'First play', fmtDate(t.first),
      fmtTime(t.first));
    addFact(entity || view.title ? 'Latest listen' : 'Latest play', fmtDate(t.last),
      fmtTime(t.last));
  }
  const src = d.by_source || {};
  if (src.web && t.plays) {
    addFact('On your phone', Math.round(100 * src.web / t.plays) + '%',
      `${plural(src.web, 'play')} via the web player`);
  }
  if (!entity && !view.title && t.plays && t.artists) {
    const top = d.top_artists[0];
    if (top && t.artists > 1) {
      const top5 = d.top_artists.slice(0, 5).reduce((s, a) => s + a.plays, 0);
      addFact('Top 5 artists', Math.round(100 * top5 / t.plays) + '%', 'of all your plays');
    }
  }
  show('facts-section', facts.children.length > 0);
}

// ── history (individual plays, paged) ─────────────────────────────

let historyOffset = 0;
let historyToken = 0;

function filterQuery(extra) {
  const q = new URLSearchParams();
  ['period', 'artist', 'album', 'title'].forEach(k => { if (view[k]) q.set(k, view[k]); });
  Object.entries(extra || {}).forEach(([k, v]) => q.set(k, v));
  const s = q.toString();
  return s ? '?' + s : '';
}

async function loadHistory(reset) {
  const my = reset ? ++historyToken : historyToken;
  if (reset) { historyOffset = 0; $('history').textContent = ''; }
  const day = !!view.period && view.period.length === 10;
  const page = day ? 200 : 25;
  const h = await api('/api/history' + filterQuery({ offset: historyOffset, limit: page }));
  if (my !== historyToken) return;           // view changed mid-flight
  show('history-section', h.total > 0);
  $('history-h').textContent = day ? 'What you played' : 'Recent plays';
  $('history-count').textContent = plural(h.total, 'play');
  const list = $('history');
  h.plays.forEach(r => list.appendChild(rankRow({
    hash: trackHref(r.artist || 'Unknown', r.title || ''),
    rank: day ? fmtTime(r.ts) : fmtDate(r.ts, { month: 'short', day: 'numeric' }) + ' ' + fmtTime(r.ts),
    title: r.title || 'Untitled',
    sub: view.title ? (r.album || '') : [r.artist, r.album].filter(Boolean).join(' · '),
    value: r.src === 'web' ? 'phone' : '',
  })));
  historyOffset += h.plays.length;
  $('history-more').hidden = historyOffset >= h.total;
}
$('history-more').addEventListener('click', () => loadHistory(false));

// ── full lists ────────────────────────────────────────────────────

let listRows = [];
let listSort = 'plays';

const LIST_SORTS = {
  artists: [['plays', 'Plays'], ['minutes', 'Minutes'], ['last', 'Recent'], ['name', 'A–Z']],
  albums: [['plays', 'Plays'], ['minutes', 'Minutes'], ['last', 'Recent'], ['name', 'A–Z']],
  tracks: [['plays', 'Plays'], ['minutes', 'Minutes'], ['last', 'Recent'], ['name', 'A–Z']],
  new: [['first', 'Newest'], ['plays', 'Plays'], ['name', 'A–Z']],
};

function buildListRows(d) {
  const kind = view.list;
  if (kind === 'artists') {
    return d.top_artists.map(a => ({
      name: a.name, sub: `${plural(a.albums, 'album')} · ${plural(a.tracks, 'track')}`,
      plays: a.plays, minutes: a.minutes, last: a.last,
      hash: artistHref(a.name), img: () => artistImg(a.name, a.album_ids), round: true }));
  }
  if (kind === 'albums') {
    return d.top_albums.map(a => ({
      name: a.title || 'Unknown album', sub: a.artist, plays: a.plays,
      minutes: a.minutes, last: a.last, hash: albumHref(a.key),
      img: () => coverImg(a.id, a.title) }));
  }
  if (kind === 'tracks') {
    return d.top_tracks.map(t => ({
      name: t.title || 'Untitled',
      sub: (view.artist ? [t.album] : [t.artist, t.album]).filter(Boolean).join(' · '),
      plays: t.plays, minutes: t.minutes, last: t.last,
      hash: trackHref(t.artist, t.title) }));
  }
  return d.new_artists.map(a => ({
    name: a.name, sub: 'first played ' + fmtDate(a.first), plays: a.plays,
    first: a.first, hash: artistHref(a.name),
    img: () => artistImg(a.name, a.album_ids), round: true }));
}

function renderList() {
  const filter = $('list-filter').value.trim().toLowerCase();
  const rows = listRows.filter(r => !filter ||
    r.name.toLowerCase().includes(filter) || (r.sub || '').toLowerCase().includes(filter));
  const cmp = {
    plays: (a, b) => b.plays - a.plays || (b.minutes || 0) - (a.minutes || 0),
    minutes: (a, b) => b.minutes - a.minutes,
    last: (a, b) => (b.last || '').localeCompare(a.last || ''),
    first: (a, b) => (b.first || '').localeCompare(a.first || ''),
    name: (a, b) => a.name.localeCompare(b.name),
  }[listSort];
  rows.sort(cmp);
  const metric = listSort === 'minutes' ? 'minutes' : 'plays';
  const max = Math.max(...rows.map(r => r[metric] || 0), 1);
  const list = $('full-list');
  list.textContent = '';
  // Rank is position in the *unfiltered* plays ranking, so filtering
  // doesn't renumber things.
  rows.forEach((r, i) => {
    const value = listSort === 'minutes' ? plural(r.minutes, 'min')
      : listSort === 'last' ? fmtDate(r.last, { month: 'short', day: 'numeric' })
      : plural(r.plays, 'play');
    const li = rankRow({
      hash: r.hash, rank: listSort === 'plays' ? r.rank : i + 1,
      img: r.img ? r.img() : null, title: r.name, sub: r.sub, value,
      frac: (r[metric] || 0) / max,
    });
    if (r.round) li.classList.add('round');
    list.appendChild(li);
  });
  if (!rows.length) list.appendChild(el('li', 'none', 'No matches.'));
}

function setupList(d) {
  listRows = buildListRows(d);
  [...listRows].sort((a, b) => b.plays - a.plays).forEach((r, i) => { r.rank = i + 1; });
  const sorts = LIST_SORTS[view.list] || LIST_SORTS.artists;
  listSort = sorts[0][0];
  const bar = $('list-sort');
  bar.textContent = '';
  sorts.forEach(([key, label]) => {
    const b = el('button', 'year-chip' + (key === listSort ? ' active' : ''), label);
    b.addEventListener('click', () => {
      listSort = key;
      bar.querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
      renderList();
    });
    bar.appendChild(b);
  });
  $('list-filter').value = '';
  $('list-filter').hidden = listRows.length < 12;
  renderList();
}
$('list-filter').addEventListener('input', renderList);

// ── top level ─────────────────────────────────────────────────────

const OVERVIEW_SECTIONS = ['artist-section', 'albums-section', 'tracks-section',
  'new-section', 'years-section', 'months-section', 'days-section',
  'calendar-section', 'hours-section', 'weekdays-section', 'facts-section',
  'history-section'];

function render(d) {
  renderYears(d.available_years);
  setupBack();

  if (!d.totals.plays) {
    $('page').hidden = true;
    $('empty').hidden = false;
    const what = view.title || view.artist || (view.album ? 'this album' : '');
    $('empty-msg').textContent = what
      ? `No plays of ${what} in ${periodLabel(view.period)}.`
      : !view.period
        ? 'Nothing logged yet — plays are recorded once you listen to at least half a track.'
        : `Nothing played in ${periodLabel(view.period)}.`;
    return;
  }
  $('empty').hidden = true;
  $('page').hidden = false;

  renderHero(d);
  if (view.list) {
    OVERVIEW_SECTIONS.forEach(id => show(id, false));
    show('list-section', true);
    setupList(d);
    return;
  }
  show('list-section', false);
  renderTopArtists(d);
  renderTopAlbums(d);
  renderTopTracks(d);
  renderNewArtists(d);
  renderCharts(d);
  renderFacts(d);
  show('history-section', false);
  loadHistory(true).catch(() => {});
}

let routeToken = 0;

async function route() {
  view = readHash();
  hideTip();
  const my = ++routeToken;
  const extra = {};
  // Full lists want everything; an album wants every played track.
  if (view.list || view.album) extra.limit = 2000;
  const d = await api('/api/stats' + filterQuery(extra));
  if (my !== routeToken) return;             // a newer navigation won
  render(d);
  window.scrollTo(0, 0);
}

async function start() {
  if (!location.hash) {
    // First visit: land on the newest year with data, else all-time
    const d = await api('/api/stats');
    if (d.available_years.length) {
      history.replaceState(null, '', '#period=' + d.available_years[0]);
    } else {
      view = readHash();
      return render(d);
    }
  }
  return route();
}

start().catch(e => {
  if (e.message !== 'unauthorized') {
    $('unauth').hidden = false;
    $('unauth').firstElementChild.textContent = 'Could not reach the server.';
  }
});
