// lp stats — renders /api/stats as a year-in-review page.
// Charts are single-series magnitude → one validated hue (#cc7511 in CSS),
// no legend, selective labels (the peak), hover/tap tooltips on every bar.

'use strict';

const $ = id => document.getElementById(id);

// ── token (same convention as app.js) ─────────────────────────────

let token = '';
{
  const fromUrl = new URLSearchParams(location.search).get('token');
  if (fromUrl) {
    localStorage.setItem('lp-token', fromUrl);
    history.replaceState(null, '', location.pathname);
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
  const wrap = el('div');
  const img = document.createElement('img');
  img.alt = name;
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
const MONTHS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];

// ── tooltip (shared, hover + tap) ─────────────────────────────────

const tip = $('tooltip');
function showTip(target, text) {
  tip.textContent = text;
  tip.hidden = false;
  const r = target.getBoundingClientRect();
  tip.style.left = (r.left + r.width / 2) + 'px';
  tip.style.top = r.top + 'px';
}
function hideTip() { tip.hidden = true; }
document.addEventListener('scroll', hideTip, { passive: true });

// ── bar chart (single series, flex bars) ──────────────────────────

function barChart(container, values, labels, tipText, labelEvery) {
  container.textContent = '';
  const max = Math.max(...values, 1);
  const peakIdx = values.indexOf(Math.max(...values));

  if (values[peakIdx] > 0) {
    container.appendChild(el('div', 'peak-label', tipText(peakIdx, true)));
  }
  const bars = el('div', 'bars');
  values.forEach((v, i) => {
    const slot = el('div', 'bar-slot');
    const bar = el('div', 'bar');
    bar.style.height = Math.max(1, (v / max) * 100) + '%';
    slot.appendChild(bar);
    slot.addEventListener('mouseenter', () => showTip(slot, tipText(i, false)));
    slot.addEventListener('mouseleave', hideTip);
    slot.addEventListener('click', () => showTip(slot, tipText(i, false)));
    bars.appendChild(slot);
  });
  container.appendChild(bars);

  const lab = el('div', 'bar-labels');
  labels.forEach((l, i) => lab.appendChild(
    el('span', '', labelEvery && i % labelEvery !== 0 ? '' : l)));
  container.appendChild(lab);
}

// ── render ────────────────────────────────────────────────────────

let currentYear;   // undefined until first load; null = all time

function renderYears(years) {
  const nav = $('years');
  nav.textContent = '';
  const mk = (label, y) => {
    const b = el('button', 'year-chip' + (y === currentYear ? ' active' : ''), label);
    b.addEventListener('click', () => load(y));
    nav.appendChild(b);
  };
  years.forEach(y => mk(String(y), y));
  mk('All time', null);
}

function render(d) {
  renderYears(d.available_years);
  const label = d.year === null ? 'all time' : d.year;
  $('hero-title').textContent =
    d.year === null ? 'Your music, all time' : `Your ${d.year} in music`;

  if (!d.totals.plays) {
    $('page').hidden = true;
    $('empty').hidden = false;
    $('empty-msg').textContent = d.year === null
      ? 'Nothing logged yet — plays are recorded once you listen to at least half a track.'
      : `Nothing played in ${d.year} yet.`;
    return;
  }
  $('empty').hidden = true;
  $('page').hidden = false;

  // hero
  $('hero-minutes').textContent = fmtInt(d.totals.minutes);
  const kpis = $('kpis');
  kpis.textContent = '';
  [['plays', d.totals.plays], ['artists', d.totals.artists],
   ['albums', d.totals.albums], ['tracks', d.totals.tracks]]
    .forEach(([l, v]) => {
      const k = el('div', 'kpi');
      k.appendChild(el('div', 'v', fmtInt(v)));
      k.appendChild(el('div', 'l', l));
      kpis.appendChild(k);
    });

  // top artist + runners
  const arts = d.top_artists;
  $('artist-section').hidden = !arts.length;
  if (arts.length) {
    const a = arts[0];
    const imgWrap = $('top-artist-img');
    imgWrap.textContent = '';
    imgWrap.appendChild(artistImg(a.name, a.album_ids));
    $('top-artist-name').textContent = a.name;
    $('top-artist-meta').textContent =
      `${fmtInt(a.plays)} plays · ${fmtInt(a.minutes)} minutes`;
    const run = $('runners');
    run.textContent = '';
    arts.slice(1, 5).forEach(r => {
      const c = el('div', 'runner');
      c.appendChild(artistImg(r.name, r.album_ids));
      c.appendChild(el('div', 'n', r.name));
      c.appendChild(el('div', 'p', fmtInt(r.plays) + ' plays'));
      run.appendChild(c);
    });
  }

  // albums
  const albums = d.top_albums;
  $('albums-section').hidden = !albums.length;
  const grid = $('album-grid');
  grid.textContent = '';
  albums.forEach((al, i) => {
    const t = el('div', 'album-tile');
    t.appendChild(coverImg(al.id, al.title));
    t.appendChild(el('div', 'rank', '#' + (i + 1)));
    t.appendChild(el('div', 't', al.title));
    t.appendChild(el('div', 'a', `${al.artist} · ${fmtInt(al.plays)} plays`));
    grid.appendChild(t);
  });

  // tracks
  const tracks = d.top_tracks;
  $('tracks-section').hidden = !tracks.length;
  const list = $('track-list');
  list.textContent = '';
  const maxPlays = tracks.length ? tracks[0].plays : 1;
  tracks.forEach((t, i) => {
    const li = el('li', 'track-row');
    const fill = el('div', 'fill');
    fill.style.transform = `scaleX(${t.plays / maxPlays})`;
    li.appendChild(fill);
    li.appendChild(el('span', 'r', String(i + 1)));
    const title = el('span', 't', t.title);
    const sub = el('small', '', t.artist);
    title.appendChild(sub);
    li.appendChild(title);
    li.appendChild(el('span', 'p', fmtInt(t.plays) + ' plays'));
    list.appendChild(li);
  });

  // charts
  const months = d.minutes_by_month;
  $('months-section').hidden = !months.some(v => v > 0);
  barChart($('month-chart'), months, MONTHS,
    (i, peak) => peak
      ? `Biggest month: ${MONTH_NAMES[i]} — ${fmtInt(months[i])} minutes`
      : `${MONTH_NAMES[i]}: ${fmtInt(months[i])} minutes`);

  const hours = d.plays_by_hour;
  $('hours-section').hidden = !hours.some(v => v > 0);
  barChart($('hour-chart'), hours,
    hours.map((_, i) => String(i)),
    (i, peak) => peak
      ? `Peak hour: ${i}:00 — ${fmtInt(hours[i])} plays`
      : `${i}:00 — ${fmtInt(hours[i])} plays`,
    6);

  // facts
  const facts = $('facts');
  facts.textContent = '';
  const addFact = (l, v, s) => {
    const f = el('div', 'fact');
    f.appendChild(el('div', 'l', l));
    f.appendChild(el('div', 'v', v));
    if (s) f.appendChild(el('div', 's', s));
    facts.appendChild(f);
  };
  if (d.peak_day) {
    const dt = new Date(d.peak_day.date + 'T12:00:00');
    addFact('Peak day', dt.toLocaleDateString(undefined,
      { month: 'short', day: 'numeric' }), `${fmtInt(d.peak_day.minutes)} minutes`);
  }
  if (d.streak && d.streak.days > 1) {
    addFact('Longest streak', `${d.streak.days} days`, 'in a row');
  }
  if (d.deep_cut) {
    addFact('Deep cut', d.deep_cut.title,
      `${d.deep_cut.artist} · ${fmtInt(d.deep_cut.plays)} plays`);
  }
  $('facts-section').hidden = !facts.children.length;
}

async function load(year) {
  currentYear = year;
  const q = year === null || year === undefined ? '' : '?year=' + year;
  const d = await api('/api/stats' + q);
  if (year === undefined) {
    // First load: land on the newest year with data, else all-time
    currentYear = d.available_years.length ? d.available_years[0] : null;
    if (currentYear !== null && d.year === null) return load(currentYear);
  }
  render(d);
}

load(undefined).catch(e => {
  if (e.message !== 'unauthorized') {
    $('unauth').hidden = false;
    $('unauth').firstElementChild.textContent = 'Could not reach the server.';
  }
});
