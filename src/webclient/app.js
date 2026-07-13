// lp remote — phone client.
//
// iOS rules this file lives by:
//  * The first audio.play() must run synchronously inside a tap handler;
//    after that, advancing tracks from the 'ended' event keeps playing
//    with the screen locked.
//  * ONE persistent <audio> element, src swapped per track — recreating
//    the element drops the background-audio session.
//  * Media Session API (lock-screen art/controls) only exists in secure
//    contexts (https / localhost). Over plain http://<LAN-IP> it is
//    feature-guarded away; screen-off playback itself still works.

'use strict';

const $ = id => document.getElementById(id);
const audio = $('player');

const IDLE_HIDE_MS = 2500;   // mirrors MiniView.IDLE_HIDE_MS

// ── lp's own icons (src/icons/*.svg), inlined on currentColor ────

const ICONS = {
  play: '<path d="M320-200v-560l440 280-440 280Z"/>',
  pause: '<path d="M560-200v-560h160v560H560Zm-320 0v-560h160v560H240Z"/>',
  next: '<path d="M660-240v-480h80v480h-80Zm-440 0v-480l360 240-360 240Z"/>',
  prev: '<path d="M220-240v-480h80v480h-80Zm520 0L380-480l360-240v480Z"/>',
};
const ICONS24 = {
  library: '<path d="M3 3 H10 V10 H3 Z"/><path d="M14 3 H21 V10 H14 Z"/>'
    + '<path d="M3 14 H10 V21 H3 Z"/><path d="M14 14 H21 V21 H14 Z"/>',
  tracklist: '<path d="M3 4 H6 V7 H3 Z"/><path d="M8 4.5 H21 V6.5 H8 Z"/>'
    + '<path d="M3 10.5 H6 V13.5 H3 Z"/><path d="M8 11 H21 V13 H8 Z"/>'
    + '<path d="M3 17 H6 V20 H3 Z"/><path d="M8 17.5 H21 V19.5 H8 Z"/>',
  lyrics: '<path d="M4 4 H20 V6 H4 Z"/><path d="M4 8.5 H16 V10.5 H4 Z"/>'
    + '<path d="M4 13 H19 V15 H4 Z"/><path d="M4 17.5 H12 V19.5 H4 Z"/>',
  heart: '<path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 '
    + '7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 '
    + '5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>',
  heart_outline: '<path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 '
    + '5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 '
    + '19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35zM12 5.09 '
    + '10.94 6.14C10.02 5.09 8.79 4.5 7.5 4.5 5.24 4.5 3.5 6.24 3.5 8.5c0 '
    + '2.89 2.7 5.31 6.79 9.03L12 19.14l1.71-1.61C17.8 13.81 20.5 11.39 '
    + '20.5 8.5c0-2.26-1.74-4-4-4-1.29 0-2.52.59-3.44 1.64L12 5.09z"/>',
};

function setIcon(btn, name) {
  const material = name in ICONS;   // material icons use a -960 viewBox
  btn.innerHTML = `<svg viewBox="${material ? '0 -960 960 960' : '0 0 24 24'}" `
    + `xmlns="http://www.w3.org/2000/svg">${material ? ICONS[name] : ICONS24[name]}</svg>`;
}

setIcon($('menu-btn'), 'library');
setIcon($('tracks-btn'), 'tracklist');
setIcon($('lyrics-btn'), 'lyrics');
setIcon($('prev-btn'), 'prev');
setIcon($('play-btn'), 'play');
setIcon($('next-btn'), 'next');
setIcon($('fav-btn'), 'heart_outline');

// ── token ─────────────────────────────────────────────────────────

let token = '';
{
  const fromUrl = new URLSearchParams(location.search).get('token');
  if (fromUrl) {
    localStorage.setItem('lp-token', fromUrl);
    history.replaceState(null, '', location.pathname);
  }
  token = localStorage.getItem('lp-token') || '';
}

function withToken(url) {
  return url + (url.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token);
}

async function api(path) {
  const res = await fetch(withToken(path));
  if (res.status === 401) { showTokenScreen(); throw new Error('unauthorized'); }
  if (!res.ok) throw new Error('http ' + res.status);
  return res.json();
}

function showTokenScreen(msg) {
  $('token-err').textContent = msg || '';
  $('token-screen').hidden = false;
  $('token-input').focus();
}

$('token-go').addEventListener('click', async () => {
  token = $('token-input').value.trim();
  localStorage.setItem('lp-token', token);
  try {
    await api('/api/albums');
    $('token-screen').hidden = true;
    loadLibrary();
  } catch {
    showTokenScreen('Not accepted — check the token and try again.');
  }
});
$('token-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') $('token-go').click();
});

// ── state ─────────────────────────────────────────────────────────

let albums = [];        // /api/albums result
let current = null;     // /api/album result for the loaded album
let tracks = [];
let idx = -1;

// ── library drawer ────────────────────────────────────────────────

async function loadLibrary() {
  const data = await api('/api/albums');
  albums = data.albums;
  renderAlbumList($('filter').value);
}

// Artists whose groups the user has opened (collapsed by default — some
// artists have too many entries to scroll past). The playing artist is
// auto-opened; a filter overrides collapse for its matches.
const openArtists = new Set();

function renderAlbumList(filter) {
  const list = $('album-list');
  list.textContent = '';
  const needle = (filter || '').toLowerCase();
  // Group under the top-level folder (the artist); the rest of the path is
  // the row label, so nested layouts (Artist/Albums/X, multi-disc CD1/CD2)
  // stay under one header instead of interleaving.
  const entries = albums.map(a => {
    const parts = a.id.split('/');
    return {
      id: a.id,
      artist: parts.length > 1 ? parts[0] : '',
      label: parts.length > 1 ? parts.slice(1).join(' / ') : a.name,
    };
  }).sort((a, b) =>
    a.artist.localeCompare(b.artist) || a.label.localeCompare(b.label));

  const groups = new Map();   // artist -> entries (insertion = sorted order)
  for (const a of entries) {
    if (needle && !(a.artist + ' ' + a.label).toLowerCase().includes(needle)) continue;
    if (!groups.has(a.artist)) groups.set(a.artist, []);
    groups.get(a.artist).push(a);
  }

  const playingArtist = current ? current.id.split('/')[0] : null;

  const albumRow = a => {
    const row = document.createElement('div');
    row.className = 'album-row';
    if (current && a.id === current.id) row.classList.add('playing');
    row.textContent = a.label;
    row.addEventListener('click', () => {
      closeDrawer();
      loadAlbum(a.id, true);   // tap = the user gesture that unlocks audio
    });
    return row;
  };

  for (const [artist, items] of groups) {
    if (!artist) {           // root-level albums: no group, always visible
      items.forEach(a => list.appendChild(albumRow(a)));
      continue;
    }
    const group = document.createElement('div');
    group.className = 'artist-group';
    const open = needle !== '' || openArtists.has(artist)
      || artist === playingArtist;
    if (open) group.classList.add('open');

    const header = document.createElement('div');
    header.className = 'artist-header';
    const caret = document.createElement('span');
    caret.className = 'caret';
    caret.textContent = '▶';
    const name = document.createElement('span');
    name.textContent = artist;
    const count = document.createElement('span');
    count.className = 'count';
    count.textContent = items.length;
    header.append(caret, name, count);
    header.addEventListener('click', () => {
      if (group.classList.toggle('open')) openArtists.add(artist);
      else openArtists.delete(artist);
    });

    const body = document.createElement('div');
    body.className = 'albums';
    items.forEach(a => body.appendChild(albumRow(a)));

    group.append(header, body);
    list.appendChild(group);
  }
}

$('filter').addEventListener('input', () => renderAlbumList($('filter').value));

function openDrawer() { document.body.classList.add('drawer-open'); }
function closeDrawer() { document.body.classList.remove('drawer-open'); }
$('menu-btn').addEventListener('click', () => {
  loadLibrary().catch(() => {});
  openDrawer();
});
$('scrim').addEventListener('click', closeDrawer);

// ── album / playback ──────────────────────────────────────────────

async function loadAlbum(id, autoplay) {
  const data = await api('/api/album?id=' + encodeURIComponent(id));
  current = data;
  tracks = data.tracks;
  setArt(data.art.length ? withToken(data.art[0]) : null);
  renderTracklist();
  if (autoplay && tracks.length) playTrack(0);
}

function setArt(url) {
  const art = $('art');
  if (url) {
    art.src = url;
    art.classList.add('loaded');
    $('placeholder').style.display = 'none';
  } else {
    art.removeAttribute('src');
    art.classList.remove('loaded');
    $('placeholder').style.display = 'flex';
  }
}

function playTrack(i) {
  if (i < 0 || i >= tracks.length) return;
  idx = i;
  listened = 0;      // per-track listen accumulator (play-count beacon)
  lastT = null;
  beaconSent = false;
  audio.src = withToken(tracks[i].url);
  audio.play().catch(() => {});
  updateNowPlaying();
  if (document.body.classList.contains('lyrics-open')) loadLyrics();
}

// ── play-count beacon ─────────────────────────────────────────────
// Mirrors the desktop scrobble rule: >=50% of the track or 4 minutes of
// actual listening. `listened` sums only small forward deltas of
// currentTime, so seeking never inflates it. Fires once per track load;
// a missed beacon is fine, a double-count is not.

let listened = 0, lastT = null, beaconSent = false;

audio.addEventListener('seeking', () => { lastT = null; });

function beaconTick() {
  const t = audio.currentTime;
  if (lastT !== null && t > lastT && t - lastT < 2) listened += t - lastT;
  lastT = t;
  if (beaconSent || idx < 0 || !current) return;
  if (listened >= 240 || (audio.duration > 0 && listened >= audio.duration / 2)) {
    beaconSent = true;   // flag first — never double-fire
    fetch(withToken('/api/played'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        artist: current.artist, album: current.title,
        title: tracks[idx].title, n: tracks[idx].n,
        length: tracks[idx].length, listened: Math.round(listened),
        album_id: current.id,
      }),
    }).catch(() => {});
  }
}

// ── favourites (heart button) ──────────────────────────────────────
// Mirrors the desktop's tracklist star/heart: favouriting from the phone
// writes to the same favorites.json the desktop reads (see /api/favorite
// in media_server.py), keyed by track path resolved server-side — the
// client only ever sends album id + tracknumber, never a path.

let favBusy = false;

async function refreshFavoriteState() {
  const t = tracks[idx];
  if (!current || !t) { setIcon($('fav-btn'), 'heart_outline'); return; }
  try {
    const d = await api('/api/favorite?id=' + encodeURIComponent(current.id)
      + '&n=' + encodeURIComponent(t.n));
    setIcon($('fav-btn'), d.favorited ? 'heart' : 'heart_outline');
  } catch {
    // offline/error — leave the icon as-is rather than guess
  }
}

$('fav-btn').addEventListener('click', async () => {
  const t = tracks[idx];
  if (!current || !t || favBusy) return;
  favBusy = true;
  try {
    const res = await fetch(withToken('/api/favorite'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: current.id, n: t.n }),
    });
    if (res.ok) {
      const d = await res.json();
      setIcon($('fav-btn'), d.favorited ? 'heart' : 'heart_outline');
    }
  } catch {
    // offline — the tap just doesn't register; no optimistic state to undo
  } finally {
    favBusy = false;
  }
});

function updateNowPlaying() {
  const t = tracks[idx];
  $('track-title').textContent = t ? t.title : '';
  $('track-album').textContent =
    current ? [current.artist, current.title].filter(Boolean).join(' — ') : '';
  renderTracklist();
  renderAlbumList($('filter').value);
  refreshFavoriteState();
  if ('mediaSession' in navigator && current && t) {
    navigator.mediaSession.playbackState = 'playing';
    navigator.mediaSession.metadata = new MediaMetadata({
      title: t.title,
      artist: current.artist || '',
      album: current.title || '',
      artwork: current.art.length
        ? [{ src: new URL(withToken(current.art[0]), location.href).href,
             sizes: '512x512', type: 'image/jpeg' }]
        : [],
    });
  }
}

// Screen-off core: advancing from 'ended' on the SAME element keeps the
// audio session alive while the phone is locked.
audio.addEventListener('ended', () => {
  if (idx + 1 < tracks.length) playTrack(idx + 1);
});

// One bad file shouldn't kill the album — skip after a beat.
audio.addEventListener('error', () => {
  if (idx >= 0 && idx + 1 < tracks.length) setTimeout(() => playTrack(idx + 1), 2000);
});

function togglePlay() {
  if (!audio.src) {                    // fresh open: start the loaded album
    if (tracks.length) playTrack(0);
    return;
  }
  if (audio.paused) audio.play().catch(() => {});
  else audio.pause();
}

function prevTrack() {
  if (audio.currentTime > 3 || idx <= 0) audio.currentTime = 0;
  else playTrack(idx - 1);
}
function nextTrack() { if (idx + 1 < tracks.length) playTrack(idx + 1); }

$('play-btn').addEventListener('click', togglePlay);
$('prev-btn').addEventListener('click', prevTrack);
$('next-btn').addEventListener('click', nextTrack);

// playbackState keeps the OS media session bound to this page while
// paused — without it, pausing releases the session and the lock-screen
// play button falls back to the phone's previous media app.
audio.addEventListener('play', () => {
  setIcon($('play-btn'), 'pause');
  if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'playing';
});
audio.addEventListener('pause', () => {
  setIcon($('play-btn'), 'play');
  if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'paused';
});

// ── lyrics (cached .lrc/.txt served by /api/lyrics) ───────────────

let lyricLines = [];        // [{t: seconds|null, el}] for the loaded track
let lyricActive = -1;
let lyricTrackUrl = null;   // which track the panel currently shows

async function loadLyrics() {
  const panel = $('lyrics');
  if (idx < 0 || !current) {
    panel.innerHTML = '<div class="none">Nothing playing</div>';
    return;
  }
  const t = tracks[idx];
  if (lyricTrackUrl === t.url) return;    // already showing this track
  lyricTrackUrl = t.url;
  lyricLines = [];
  lyricActive = -1;
  panel.innerHTML = '<div class="none">…</div>';
  try {
    const d = await api('/api/lyrics?id=' + encodeURIComponent(current.id)
      + '&n=' + encodeURIComponent(t.n)
      + '&title=' + encodeURIComponent(t.title));
    panel.textContent = '';
    for (const raw of d.text.split('\n')) {
      let time = null, text = raw;
      const m = raw.match(/^\[(\d+):(\d+(?:\.\d+)?)\](.*)$/);
      if (m) { time = parseInt(m[1], 10) * 60 + parseFloat(m[2]); text = m[3].trim(); }
      const line = document.createElement('div');
      line.className = 'lyric-line';
      line.textContent = text;
      panel.appendChild(line);
      lyricLines.push({ t: time, el: line });
    }
  } catch {
    panel.innerHTML = '<div class="none">No lyrics for this track</div>';
    lyricTrackUrl = null;   // allow retry (e.g. after desktop fetches them)
  }
}

function syncLyrics() {
  if (!document.body.classList.contains('lyrics-open') || !lyricLines.length) return;
  const now = audio.currentTime;
  let active = -1;
  for (let i = 0; i < lyricLines.length; i++) {
    if (lyricLines[i].t !== null && lyricLines[i].t <= now) active = i;
    else if (lyricLines[i].t !== null && lyricLines[i].t > now) break;
  }
  if (active === lyricActive) return;
  if (lyricActive >= 0) lyricLines[lyricActive].el.classList.remove('active');
  lyricActive = active;
  if (active >= 0) {
    lyricLines[active].el.classList.add('active');
    lyricLines[active].el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
}

// ── media session (lock-screen controls) ──────────────────────────

if ('mediaSession' in navigator) {
  const ms = navigator.mediaSession;
  ms.setActionHandler('play', () => audio.play().catch(() => {}));
  ms.setActionHandler('pause', () => audio.pause());
  ms.setActionHandler('previoustrack', prevTrack);
  ms.setActionHandler('nexttrack', nextTrack);
  try {
    ms.setActionHandler('seekto', d => { audio.currentTime = d.seekTime; });
  } catch { /* older browsers */ }
}

// ── seek bar / time ───────────────────────────────────────────────

const fmt = s => {
  s = Math.max(0, Math.floor(s || 0));
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
};

let scrubbing = false;
let lastPosUpdate = 0;

audio.addEventListener('timeupdate', () => {
  beaconTick();
  syncLyrics();
  if (!scrubbing && audio.duration) {
    $('seek').value = Math.round(audio.currentTime / audio.duration * 1000);
  }
  $('time-cur').textContent = fmt(audio.currentTime);
  $('time-len').textContent = fmt(audio.duration);
  const now = Date.now();
  if ('mediaSession' in navigator && audio.duration && now - lastPosUpdate > 1000) {
    lastPosUpdate = now;
    try {
      navigator.mediaSession.setPositionState({
        duration: audio.duration,
        position: audio.currentTime,
        playbackRate: audio.playbackRate,
      });
    } catch { /* NaN duration race */ }
  }
});

$('seek').addEventListener('input', () => {
  scrubbing = true;
  if (audio.duration) {
    $('time-cur').textContent = fmt($('seek').value / 1000 * audio.duration);
  }
});
$('seek').addEventListener('change', () => {
  if (audio.duration) audio.currentTime = $('seek').value / 1000 * audio.duration;
  scrubbing = false;
});

// ── tracklist overlay ─────────────────────────────────────────────

function renderTracklist() {
  const el = $('tracklist');
  el.textContent = '';
  tracks.forEach((t, i) => {
    const row = document.createElement('div');
    row.className = 'track-row' + (i === idx ? ' playing' : '');
    const n = document.createElement('span');
    n.className = 'n';
    n.textContent = t.n || i + 1;
    const title = document.createElement('span');
    title.textContent = t.title;
    const len = document.createElement('span');
    len.className = 'len';
    len.textContent = fmt(t.length);
    row.append(n, title, len);
    row.addEventListener('click', () => playTrack(i));
    el.appendChild(row);
  });
}

// Tracklist and lyrics share the right-side slot — opening one closes the
// other (mirrors max/mini mode's independent-but-tidy panes on a screen
// with room for only one)
$('tracks-btn').addEventListener('click', e => {
  e.stopPropagation();
  document.body.classList.remove('lyrics-open');
  document.body.classList.toggle('tracks-open');
});
$('lyrics-btn').addEventListener('click', e => {
  e.stopPropagation();
  document.body.classList.remove('tracks-open');
  if (document.body.classList.toggle('lyrics-open')) {
    loadLyrics();
    syncLyrics();
  }
});

// ── auto-hiding chrome (mirrors MiniView's idle timer) ────────────

let idleTimer = null;

function showChrome() {
  document.body.classList.remove('idle');
  clearTimeout(idleTimer);
  idleTimer = setTimeout(() => {
    if (!document.body.classList.contains('drawer-open') &&
        !document.body.classList.contains('tracks-open') &&
        !document.body.classList.contains('lyrics-open') &&
        !audio.paused) {
      document.body.classList.add('idle');
    } else {
      showChrome();   // re-arm while a panel is open or paused
    }
  }, IDLE_HIDE_MS);
}

['pointerdown', 'pointermove', 'keydown'].forEach(ev =>
  document.addEventListener(ev, showChrome, { passive: true }));

$('stage').addEventListener('click', e => {
  if (e.target === $('stage') || e.target === $('art') ||
      e.target === $('placeholder')) {
    document.body.classList.remove('tracks-open');
    document.body.classList.remove('lyrics-open');
    showChrome();
  }
});

// Edge swipes: right from left edge opens the drawer, left closes it.
let touchX = null, touchEdge = false;
document.addEventListener('touchstart', e => {
  touchX = e.touches[0].clientX;
  touchEdge = touchX < 24;
}, { passive: true });
document.addEventListener('touchend', e => {
  if (touchX === null) return;
  const dx = e.changedTouches[0].clientX - touchX;
  if (touchEdge && dx > 60) openDrawer();
  else if (dx < -60 && document.body.classList.contains('drawer-open')) closeDrawer();
  touchX = null;
}, { passive: true });

// ── boot ──────────────────────────────────────────────────────────

(async function boot() {
  showChrome();
  if (!token) { showTokenScreen(); return; }
  try {
    await loadLibrary();
    openDrawer();   // nothing loaded yet — start in the browser
  } catch (e) {
    if (e.message !== 'unauthorized') showTokenScreen('Could not reach the server.');
  }
})();
