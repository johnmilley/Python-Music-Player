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
  // shuffle / repeat / repeat_one: same paths as src/icons/*.svg — the
  // desktop ControlPanel's own icon set
  shuffle: '<path d="M10.59 9.17 5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 '
    + '4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41-1.41 '
    + '1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"/>',
  repeat: '<path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"/>',
  repeat_one: '<path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 '
    + '4v-3h12v-6h-2v4z"/><path d="M11.1 9.3h1.7v5.7h-1.15v-4.55l-1.15.38z"/>',
  heart: '<path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 '
    + '7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 '
    + '5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>',
  heart_outline: '<path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 '
    + '5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 '
    + '19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35zM12 5.09 '
    + '10.94 6.14C10.02 5.09 8.79 4.5 7.5 4.5 5.24 4.5 3.5 6.24 3.5 8.5c0 '
    + '2.89 2.7 5.31 6.79 9.03L12 19.14l1.71-1.61C17.8 13.81 20.5 11.39 '
    + '20.5 8.5c0-2.26-1.74-4-4-4-1.29 0-2.52.59-3.44 1.64L12 5.09z"/>',
  sun: '<path d="M12 7a5 5 0 100 10 5 5 0 000-10zm0-5a1 1 0 011 1v2a1 1 0 '
    + '11-2 0V3a1 1 0 011-1zm0 18a1 1 0 011 1v2a1 1 0 11-2 0v-2a1 1 0 '
    + '011-1zM4.22 4.22a1 1 0 011.42 0l1.42 1.42a1 1 0 11-1.42 1.42L4.22 '
    + '5.64a1 1 0 010-1.42zm12.72 12.72a1 1 0 011.42 0l1.42 1.42a1 1 0 '
    + '11-1.42 1.42l-1.42-1.42a1 1 0 010-1.42zM1 12a1 1 0 011-1h2a1 1 0 '
    + '110 2H2a1 1 0 01-1-1zm18 0a1 1 0 011-1h2a1 1 0 110 2h-2a1 1 0 '
    + '01-1-1zM4.22 19.78a1 1 0 010-1.42l1.42-1.42a1 1 0 111.42 1.42l-1.42 '
    + '1.42a1 1 0 01-1.42 0zm12.72-12.72a1 1 0 010-1.42l1.42-1.42a1 1 0 '
    + '111.42 1.42l-1.42 1.42a1 1 0 01-1.42 0z"/>',
  moon: '<path d="M20.742 13.045A8.088 8.088 0 0110.955 3.258 8.5 8.5 0 '
    + '1020.742 13.045z"/>',
  camera: '<path d="M9 3 7.17 5H4a2 2 0 00-2 2v11a2 2 0 002 2h16a2 2 0 '
    + '002-2V7a2 2 0 00-2-2h-3.17L15 3H9zm3 15a5 5 0 110-10 5 5 0 010 '
    + '10zm0-2a3 3 0 100-6 3 3 0 000 6z"/>',
};

function setIcon(btn, name) {
  const material = name in ICONS;   // material icons use a -960 viewBox
  btn.innerHTML = `<svg viewBox="${material ? '0 -960 960 960' : '0 0 24 24'}" `
    + `xmlns="http://www.w3.org/2000/svg">${material ? ICONS[name] : ICONS24[name]}</svg>`;
}

setIcon($('menu-btn'), 'library');
setIcon($('tracks-btn'), 'tracklist');
setIcon($('lyrics-btn'), 'lyrics');
setIcon($('shuffle-btn'), 'shuffle');
setIcon($('prev-btn'), 'prev');
setIcon($('play-btn'), 'play');
setIcon($('next-btn'), 'next');
setIcon($('fav-btn'), 'heart_outline');
setIcon($('camera-btn'), 'camera');

// ── theme (light/dark) ──────────────────────────────────────────────

function applyTheme(light) {
  document.body.classList.toggle('light', light);
  setIcon($('theme-btn'), light ? 'sun' : 'moon');
}
applyTheme(localStorage.getItem('lp-theme') === 'light');
$('theme-btn').addEventListener('click', () => {
  const light = !document.body.classList.contains('light');
  applyTheme(light);
  localStorage.setItem('lp-theme', light ? 'light' : 'dark');
});

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
    const label = document.createElement('span');
    label.className = 'label';
    label.textContent = a.label;
    label.style.overflow = 'hidden';
    label.style.textOverflow = 'ellipsis';
    label.style.whiteSpace = 'nowrap';
    label.style.flex = '1';
    row.appendChild(label);
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

function openDrawer() {
  // Deferred from updateNowPlaying — bring the playing-row highlight and
  // auto-opened artist group up to date now that the list is visible.
  renderAlbumList($('filter').value);
  document.body.classList.add('drawer-open');
}
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
  resetShuffleCycle();
  playHistory = [];
  setArt(data.art.length ? withToken(data.art[0]) : null);
  $('tracklist-pane-title').textContent =
    [data.artist, data.title].filter(Boolean).join(' — ');
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

function playTrack(i, record = true) {
  if (i < 0 || i >= tracks.length) return;
  idx = i;
  listened = 0;      // per-track listen accumulator (play-count beacon)
  lastT = null;
  beaconSent = false;
  bagRemove(i);
  if (record) playHistory.push(i);
  audio.src = withToken(tracks[i].url);
  audio.play().catch(() => {});
  updateNowPlaying();
  if (document.body.classList.contains('lyrics-open')) loadLyrics();
}

// ── shuffle / repeat ──────────────────────────────────────────────
// Ports player.py's semantics: shuffle draws each track once per cycle
// from a bag of remaining indices (auto-advance stops when the bag
// empties; a manual next — or repeat 'all' — refills it), and prev walks
// back through the actual play order. Repeat cycles off → all → one; 'one'
// replays the finished track, 'all' keeps auto-advance going past the
// album's end. Both persist, like the desktop's QSettings.

let shuffleOn = localStorage.getItem('lp-shuffle') === '1';
let repeatMode = localStorage.getItem('lp-repeat') || 'off';   // off | all | one
if (!['off', 'all', 'one'].includes(repeatMode)) repeatMode = 'off';

let shuffleBag = [];     // indices not yet played this cycle
let playHistory = [];    // actual play order, for shuffle-aware prev

function resetShuffleCycle() {
  shuffleBag = tracks.map((_, i) => i);
}
function bagRemove(i) {
  const at = shuffleBag.indexOf(i);
  if (at !== -1) shuffleBag.splice(at, 1);
}
function drawFromBag() {
  if (!shuffleBag.length) return -1;
  return shuffleBag[Math.floor(Math.random() * shuffleBag.length)];
}

function syncShuffleRepeatUi() {
  $('shuffle-btn').classList.toggle('on', shuffleOn);
  $('repeat-btn').classList.toggle('on', repeatMode !== 'off');
  setIcon($('repeat-btn'), repeatMode === 'one' ? 'repeat_one' : 'repeat');
}
syncShuffleRepeatUi();

$('shuffle-btn').addEventListener('click', () => {
  shuffleOn = !shuffleOn;
  localStorage.setItem('lp-shuffle', shuffleOn ? '1' : '0');
  // Fresh cycle from here: everything but the current track is undrawn
  resetShuffleCycle();
  if (idx >= 0) bagRemove(idx);
  syncShuffleRepeatUi();
});

$('repeat-btn').addEventListener('click', () => {
  repeatMode = { off: 'all', all: 'one', one: 'off' }[repeatMode];
  localStorage.setItem('lp-repeat', repeatMode);
  syncShuffleRepeatUi();
});

// auto=true is the 'ended' path: it respects the empty bag / album end
// (stopping unless repeat 'all'), while a manual tap always advances.
function advanceTrack(auto) {
  if (shuffleOn) {
    if (!shuffleBag.length) {
      if (auto && repeatMode !== 'all') return;   // cycle done — stop
      resetShuffleCycle();
      if (tracks.length > 1) bagRemove(idx);      // don't redraw what just played
    }
    const next = drawFromBag();
    if (next !== -1) playTrack(next);
    return;
  }
  if (idx + 1 < tracks.length) playTrack(idx + 1);
  else if (tracks.length && (!auto || repeatMode === 'all')) playTrack(0);
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

// ── camera upload (additional album art) ────────────────────────────
// Mirrors the desktop's "Find More Album Art..." extra-art flow — covers
// are already handled elsewhere, so a phone photo is always saved under a
// unique art_N name (mode=extra, artwork_finder.py's naming) rather than
// overwriting cover.jpg. Before upload the user adjusts a crop box over
// the whole photo — drag inside to move it, grab any edge or corner to
// resize. Free aspect ratio; it starts as the largest centered square
// (the most likely shape for album art) but doesn't have to stay one.

const CROP_OUTPUT_MAX = 1600;   // cap the uploaded crop's longest edge
const CROP_MIN_SIDE = 40;       // display px — keeps the box grabbable

let cropScale = 1;              // source px per display px
let cropBox = { x: 0, y: 0, w: 0, h: 0 };   // display px, relative to frame
let cropFrameW = 0, cropFrameH = 0;
let cropObjectUrl = null;
let cropDrag = null;            // {mode, x, y, box0} during a drag

function cropApplyBox() {
  const el = $('crop-box');
  el.style.left = cropBox.x + 'px';
  el.style.top = cropBox.y + 'px';
  el.style.width = cropBox.w + 'px';
  el.style.height = cropBox.h + 'px';
}

async function openCropScreen(file) {
  const img = $('crop-img');
  if (cropObjectUrl) URL.revokeObjectURL(cropObjectUrl);   // failed prior load
  cropObjectUrl = URL.createObjectURL(file);
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = reject;
    img.src = cropObjectUrl;
  });
  $('crop-screen').hidden = false;
  // Fit the whole photo on screen; the frame hugs the displayed image
  // exactly, so box coordinates are image coordinates (just scaled).
  const availW = Math.min(window.innerWidth * 0.92, 520);
  const availH = window.innerHeight * 0.58;
  const fit = Math.min(availW / img.naturalWidth, availH / img.naturalHeight);
  cropFrameW = Math.round(img.naturalWidth * fit);
  cropFrameH = Math.round(img.naturalHeight * fit);
  cropScale = img.naturalWidth / cropFrameW;
  const frame = $('crop-frame');
  frame.style.width = cropFrameW + 'px';
  frame.style.height = cropFrameH + 'px';
  // Largest centered square as the starting box
  const side = Math.min(cropFrameW, cropFrameH);
  cropBox = {
    x: (cropFrameW - side) / 2,
    y: (cropFrameH - side) / 2,
    w: side, h: side,
  };
  cropApplyBox();
}

function closeCropScreen() {
  $('crop-screen').hidden = true;
  $('crop-img').removeAttribute('src');
  if (cropObjectUrl) { URL.revokeObjectURL(cropObjectUrl); cropObjectUrl = null; }
  cropDrag = null;
}

async function confirmCrop() {
  const img = $('crop-img');
  const sx = cropBox.x * cropScale, sy = cropBox.y * cropScale;
  const sw = cropBox.w * cropScale, sh = cropBox.h * cropScale;
  const scale = Math.min(1, CROP_OUTPUT_MAX / Math.max(sw, sh));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(sw * scale);
  canvas.height = Math.round(sh * scale);
  canvas.getContext('2d')
    .drawImage(img, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
  closeCropScreen();
  if (blob) await uploadArtPhoto(blob);
}

async function uploadArtPhoto(blob) {
  if (!current) return;
  try {
    const res = await fetch(
      withToken('/api/art_upload?id=' + encodeURIComponent(current.id) + '&mode=extra'),
      { method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body: blob });
    if (res.ok) {
      const d = await res.json();
      current.art = d.art;
      $('camera-btn').classList.add('saved');
      setTimeout(() => $('camera-btn').classList.remove('saved'), 900);
    }
  } catch {
    // offline/error — the tap just doesn't register, matches the
    // favourite button's best-effort style above
  }
}

// One pointer, mode picked by what was grabbed: a .crop-handle carries its
// edges in data-handle ('nw'..'se'); anywhere else inside the box moves it.
// Handles hang OUTSIDE the box edges so they stay grabbable even when the
// box is pushed against the frame — pointer events are captured by the
// frame, and moves are clamped to it.
const cropFrame = $('crop-frame');

function cropPointerPos(e) {
  const rect = cropFrame.getBoundingClientRect();
  return { x: e.clientX - rect.left, y: e.clientY - rect.top };
}

cropFrame.addEventListener('pointerdown', e => {
  if (cropDrag) return;                    // single-pointer interaction
  const handle = e.target.closest('.crop-handle');
  const mode = handle ? handle.dataset.handle
    : (e.target.closest('#crop-box') ? 'move' : null);
  if (!mode) return;
  cropFrame.setPointerCapture(e.pointerId);
  const p = cropPointerPos(e);
  cropDrag = { mode, pointerId: e.pointerId, x: p.x, y: p.y, box0: { ...cropBox } };
});

cropFrame.addEventListener('pointermove', e => {
  if (!cropDrag || e.pointerId !== cropDrag.pointerId) return;
  const p = cropPointerPos(e);
  const dx = p.x - cropDrag.x, dy = p.y - cropDrag.y;
  const b0 = cropDrag.box0;
  if (cropDrag.mode === 'move') {
    cropBox.x = Math.min(cropFrameW - b0.w, Math.max(0, b0.x + dx));
    cropBox.y = Math.min(cropFrameH - b0.h, Math.max(0, b0.y + dy));
  } else {
    // Edges move independently; each clamps to the frame on one side and
    // to the opposite edge (minus the minimum size) on the other.
    let x1 = b0.x, y1 = b0.y, x2 = b0.x + b0.w, y2 = b0.y + b0.h;
    if (cropDrag.mode.includes('w')) x1 = Math.min(x2 - CROP_MIN_SIDE, Math.max(0, x1 + dx));
    if (cropDrag.mode.includes('e')) x2 = Math.max(x1 + CROP_MIN_SIDE, Math.min(cropFrameW, x2 + dx));
    if (cropDrag.mode.includes('n')) y1 = Math.min(y2 - CROP_MIN_SIDE, Math.max(0, y1 + dy));
    if (cropDrag.mode.includes('s')) y2 = Math.max(y1 + CROP_MIN_SIDE, Math.min(cropFrameH, y2 + dy));
    cropBox = { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
  }
  cropApplyBox();
});

function cropPointerEnd(e) {
  if (cropDrag && e.pointerId === cropDrag.pointerId) cropDrag = null;
}
cropFrame.addEventListener('pointerup', cropPointerEnd);
cropFrame.addEventListener('pointercancel', cropPointerEnd);

$('crop-cancel').addEventListener('click', closeCropScreen);
$('crop-retake').addEventListener('click', () => {
  closeCropScreen();
  $('camera-input').click();
});
$('crop-use').addEventListener('click', () => { confirmCrop().catch(() => {}); });

$('camera-btn').addEventListener('click', () => {
  if (current) $('camera-input').click();
});
$('camera-input').addEventListener('change', () => {
  const file = $('camera-input').files[0];
  $('camera-input').value = '';
  if (!file || !current) return;
  openCropScreen(file).catch(() => {});
});

// ── offline-downloads cleanup ───────────────────────────────────────
// The per-album offline download feature is gone (needs a connection to
// reach the app at all, and lossless albums are too big for Cache
// Storage to be worth it). Unregister the old service worker and drop
// its cache so previously-installed clients don't keep serving stale
// audio/art from it.

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations()
    .then(regs => regs.forEach(r => r.unregister()))
    .catch(() => {});
}
if ('caches' in window) caches.delete('lp-downloads-v1').catch(() => {});

function updateNowPlaying() {
  const t = tracks[idx];
  // Three titles, mirroring mini mode: the panel's own (track), the
  // tracklist pane's (artist — album) and the lyrics pane's (track).
  $('panel-title').textContent = t ? t.title : '';
  $('lyrics-pane-title').textContent = t ? t.title : '';
  renderTracklist();
  // The drawer rebuild (hundreds of rows for a big library) can wait
  // until it's actually opened — openDrawer refreshes it anyway.
  if (document.body.classList.contains('drawer-open')) {
    renderAlbumList($('filter').value);
  }
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
  if (repeatMode === 'one') { playTrack(idx, false); return; }
  advanceTrack(true);
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
  if (audio.currentTime > 3) { audio.currentTime = 0; return; }
  if (shuffleOn) {
    // Walk back through the actual play order (player.py's prev_track).
    // The abandoned track goes back in the bag so the cycle stays complete.
    if (playHistory.length >= 2) {
      const abandoned = playHistory.pop();
      if (!shuffleBag.includes(abandoned)) shuffleBag.push(abandoned);
      playTrack(playHistory[playHistory.length - 1], false);
    } else {
      audio.currentTime = 0;
    }
    return;
  }
  if (idx <= 0) audio.currentTime = 0;
  else playTrack(idx - 1);
}
function nextTrack() { advanceTrack(false); }

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

// ── lyrics ─────────────────────────────────────────────────────────
// Cached .lrc/.txt served by GET /api/lyrics; on a cache miss the panel
// asks the server to find them on LRCLIB (POST /api/lyrics_fetch — same
// search logic and cache files as the desktop's lyrics_fetcher, so a
// fetch from the phone shows up on the desktop too).

let lyricLines = [];        // [{t: seconds|null, el}] for the loaded track
let lyricActive = -1;
let lyricTrackUrl = null;   // which track the panel currently shows

function renderLyricsText(text) {
  const panel = $('lyrics');
  panel.textContent = '';
  for (const raw of text.split('\n')) {
    let time = null, line = raw;
    const m = raw.match(/^\[(\d+):(\d+(?:\.\d+)?)\](.*)$/);
    if (m) { time = parseInt(m[1], 10) * 60 + parseFloat(m[2]); line = m[3].trim(); }
    const el = document.createElement('div');
    el.className = 'lyric-line';
    el.textContent = line;
    panel.appendChild(el);
    lyricLines.push({ t: time, el });
  }
}

function lyricsMessage(text, retryTrack) {
  const panel = $('lyrics');
  panel.innerHTML = '';
  const el = document.createElement('div');
  el.className = 'none';
  el.textContent = text;
  if (retryTrack) {
    el.textContent += ' — tap to search again';
    el.addEventListener('click', () => {
      lyricTrackUrl = null;
      loadLyrics();
    });
  }
  panel.appendChild(el);
}

async function fetchLyricsFromServer(t) {
  // Server-side LRCLIB search; slow-ish (two API calls worst case)
  const res = await fetch(withToken('/api/lyrics_fetch'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: current.id, n: t.n }),
  });
  if (!res.ok) throw new Error('http ' + res.status);
  return res.json();
}

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
    renderLyricsText(d.text);
    return;
  } catch (e) {
    if (e.message === 'unauthorized') { lyricTrackUrl = null; return; }
    // fall through: not cached yet — try a live search
  }
  lyricsMessage('Searching for lyrics…');
  try {
    const d = await fetchLyricsFromServer(t);
    if (lyricTrackUrl !== t.url) return;  // user skipped ahead meanwhile
    renderLyricsText(d.text);
  } catch {
    if (lyricTrackUrl !== t.url) return;
    lyricsMessage('No lyrics found', true);
    lyricTrackUrl = null;   // stale marker — a re-open retries
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

// ── progress bar / time ───────────────────────────────────────────
// A div-based ClickableProgressBar (progress_bar.py): tap to seek, drag
// to scrub — the fill previews during the drag, the seek commits on
// release, matching the desktop's seek_requested/start_playback split.

const fmt = s => {
  s = Math.max(0, Math.floor(s || 0));
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
};

const progress = $('progress');
let scrubbing = false;
let scrubFrac = 0;
let lastPosUpdate = 0;

function setProgressFill(frac) {
  $('progress-fill').style.width = (frac * 100).toFixed(2) + '%';
}

function progressFrac(e) {
  const r = progress.getBoundingClientRect();
  return Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
}

progress.addEventListener('pointerdown', e => {
  scrubbing = true;
  progress.setPointerCapture(e.pointerId);
  scrubFrac = progressFrac(e);
  setProgressFill(scrubFrac);
  if (audio.duration) $('time-cur').textContent = fmt(scrubFrac * audio.duration);
});
progress.addEventListener('pointermove', e => {
  if (!scrubbing) return;
  scrubFrac = progressFrac(e);
  setProgressFill(scrubFrac);
  if (audio.duration) $('time-cur').textContent = fmt(scrubFrac * audio.duration);
});
function progressCommit() {
  if (!scrubbing) return;
  scrubbing = false;
  if (audio.duration) audio.currentTime = scrubFrac * audio.duration;
}
progress.addEventListener('pointerup', progressCommit);
progress.addEventListener('pointercancel', progressCommit);

audio.addEventListener('timeupdate', () => {
  beaconTick();
  syncLyrics();
  if (!scrubbing && audio.duration) {
    setProgressFill(audio.currentTime / audio.duration);
  }
  if (!scrubbing) $('time-cur').textContent = fmt(audio.currentTime);
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

// ── tracklist pane ────────────────────────────────────────────────

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
    title.className = 't';
    title.textContent = t.title;
    const len = document.createElement('span');
    len.className = 'len';
    len.textContent = fmt(t.length);
    row.append(n, title, len);
    row.addEventListener('click', () => playTrack(i));
    el.appendChild(row);
  });
}

// ── accordion panes (tracklist / lyrics toggles) ──────────────────
// Landscape: independent panes, left and right of the art — either,
// neither, or both, exactly like mini mode. Portrait: they fold from the
// top (tracklist) and bottom (lyrics), one at a time — opening one closes
// the other, since both plus the panel would squeeze the art to nothing.

const portraitMq = matchMedia('(orientation: portrait)');

$('tracks-btn').addEventListener('click', e => {
  e.stopPropagation();
  if (document.body.classList.toggle('tracks-open') && portraitMq.matches) {
    document.body.classList.remove('lyrics-open');
  }
});
$('lyrics-btn').addEventListener('click', e => {
  e.stopPropagation();
  if (document.body.classList.toggle('lyrics-open')) {
    if (portraitMq.matches) document.body.classList.remove('tracks-open');
    loadLyrics();
    syncLyrics();
  }
});
// Rotating to portrait with both panes open: keep the tracklist, fold lyrics
portraitMq.addEventListener('change', e => {
  if (e.matches && document.body.classList.contains('tracks-open')) {
    document.body.classList.remove('lyrics-open');
  }
});

// ── auto-hiding chrome: the two corner buttons ────────────────────
// Only #menu-btn/#camera-btn fade on idle now — the control panel is
// always visible (the whole point of this layout vs. desktop mini mode).

let idleTimer = null;

function showChrome() {
  document.body.classList.remove('idle');
  clearTimeout(idleTimer);
  idleTimer = setTimeout(() => {
    if (!document.body.classList.contains('drawer-open') && !audio.paused) {
      document.body.classList.add('idle');
    } else {
      showChrome();   // re-arm while the drawer is open or paused
    }
  }, IDLE_HIDE_MS);
}

['pointerdown', 'pointermove', 'keydown'].forEach(ev =>
  document.addEventListener(ev, showChrome, { passive: true }));

// Tapping the bare art closes any open pane (mirrors the desktop's
// click-art-exits gestures) and wakes the corner buttons.
$('stage').addEventListener('click', e => {
  if (e.target === $('center') || e.target === $('art-area') ||
      e.target === $('art') || e.target === $('placeholder')) {
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
