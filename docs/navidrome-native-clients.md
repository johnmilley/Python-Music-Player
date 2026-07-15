# Native iOS clients via Navidrome (Subsonic API)

Goal: get CarPlay, rock-solid background playback, lock-screen controls, and
cellular transcoding on the phone — the things a PWA structurally can't fully
deliver. Instead of teaching `media_server.py` the Subsonic API by hand (a
rewrite-sized job, plus every Subsonic client walks the *entire* library on
first connect — mutagen-per-album on the NAS would take hours), we run
**Navidrome alongside** the existing lp server. It ships its own fast taglib
scanner, ffmpeg transcoding, and works with every Subsonic client.

The lp PWA stays running unchanged — Navidrome doesn't replace it, and the
PWA keeps the two workflows no Subsonic client has: **camera → crop → album-art
upload**, and **on-demand LRCLIB lyrics fetch** into `<album>/lyrics/`.

## What's deployed (this machine)

| Piece | Value |
|---|---|
| Container | `docker.io/deluan/navidrome:latest`, rootless podman Quadlet |
| Quadlet unit | `~/.config/containers/systemd/navidrome.container` |
| Data dir | `~/.local/share/navidrome/` (DB, cache, transcode cache) |
| Music mount | `/mnt/media/02_PLEX_MEDIA/music` → `/music` **read-only** |
| Local bind | `127.0.0.1:4533` (LAN never sees it directly) |
| Tailnet URL | `https://fedora.tailc2dcbd.ts.net:8443` |
| lp PWA (unchanged) | `https://fedora.tailc2dcbd.ts.net` → `:8642` |

Two SELinux/Fedora specifics that made this work and are worth remembering:

- The music mount is **fuseblk (NTFS via ntfs-3g)**. SELinux can't relabel a
  FUSE mount with `:z`/`:Z`, so the container reads it with
  `SecurityLabelDisable=true` (i.e. `--security-opt label=disable`) instead.
  Without that the scanner gets permission-denied on every file.
- Linger was enabled (`loginctl enable-linger`) so the rootless user service
  starts at boot without a login session — matching the "persists across
  reboots" bar the Tailscale serve setup already holds.

Unlike the lp server and desktop app (which have no `.m4a` tag branch and 404
m4a-only folders), Navidrome's taglib scanner handles `.m4a` fine.

## Folder-first browsing → use Gonic, not Navidrome

The lp desktop app is folder-first on purpose (tag-based artist grouping
duplicates artists — featuring credits, inconsistent tags, VA compilations).
Navidrome is the opposite by design: its FAQ states folder browsing is against
its vision, and the spec-compliant folder-browsing PR (#5188) is **unmerged as
of 2026-07, so no released Navidrome — including 0.63.2 — exposes a real folder
tree.** Amperfy *does* have a folder/directory browse mode, but a client can
only show what the server sends; pointed at Navidrome it gets the tag-derived
artist tree, with the duplication intact. The fix is the server, not the client.

**Gonic** (`sentriz/gonic`) is the folder-first Subsonic server: `getIndexes`/
`getMusicDirectory` return the real on-disk tree, and it transcodes via bundled
ffmpeg (per-user Opus profiles incl. `opus_128`/`opus_192`/`opus_car`) — so it
covers both folder browsing *and* cellular transcoding. No web-streaming UI, but
lp's desktop app + PWA already cover that; Gonic is purely the phone backend.

Deployed alongside Navidrome (both kept for a head-to-head; retire whichever
loses):

| Piece | Value |
|---|---|
| Quadlet unit | `~/.config/containers/systemd/gonic.container` |
| Data dir | `~/.local/share/gonic/` (db, cache, playlists, podcasts) |
| Local bind | `127.0.0.1:4747` |
| Tailnet URL | `https://fedora.tailc2dcbd.ts.net:8444` |
| Version | gonic 0.22.0, ffmpeg 8.0.1 bundled |

Verified against the live server (admin/admin default): `getIndexes` returned
the real top-level folders — including a stray `.claude` dir that only a
filesystem walk would ever surface — and `getMusicDirectory` returned album
folders with their full `{year, country, catalog#}` name annotations, which
exist only in the folder names, never in tags. Proof it browses real folders.

Manage/rollback same as Navidrome, `gonic` for `navidrome`:
`systemctl --user {status,restart,stop} gonic`, logs
`podman logs -f systemd-gonic`, disable
`tailscale serve --https=8444 off` + remove the quadlet + `~/.local/share/gonic`.

> **First action required:** Gonic boots with a default `admin`/`admin`. Log in
> at `https://fedora.tailc2dcbd.ts.net:8444` (or `http://127.0.0.1:4747` on the
> desktop — Gonic has a minimal admin web UI), change the password, and set your
> transcoding preference (e.g. `opus_128` for cellular). Then add the server in
> Amperfy (same URL + new credentials) and browse by folder.

## Remaining manual steps

1. **Create the admin account.** Open `https://fedora.tailc2dcbd.ts.net:8443`
   (or `http://127.0.0.1:4533` on the desktop) once — first run shows a
   create-admin form. Pick your own username/password; nothing is preset.
2. **Install Amperfy** (free, App Store — CarPlay + offline downloads). Add a
   server: URL `https://fedora.tailc2dcbd.ts.net:8443`, plus the username and
   password from step 1. Phone must be on the tailnet (Tailscale app
   connected). *play:Sub is the paid fallback if Amperfy's UX disappoints.*
3. **Cellular transcoding.** In Amperfy's settings, set the streaming format
   for cellular to Opus or MP3 at ~192–256 kbps (keep lossless on Wi-Fi).
   Navidrome's bundled ffmpeg does the transcode on the fly; lossless still
   streams raw at home.

## Tee proxy — re-unifying phone activity (built, in trial)

`src/tee_proxy.py` is a transparent reverse proxy that sits between the phone
and Gonic so phone favourites and plays land back in the desktop's own files.
Amperfy points at the proxy; every request is forwarded to Gonic verbatim and
the response streamed back unchanged (ranged audio included), while three
endpoints are *also* teed, best-effort, into lp's files:

- `/rest/star`   → `FavoritesStore.add`   (`favorites.json`)
- `/rest/unstar` → `FavoritesStore.remove` (`favorites.json`)
- `/rest/scrobble` → `play_log.append`     (`plays.jsonl`, feeds `/stats`)

Design notes: stdlib-only, imports the Qt-free `favorites.py`/`play_log.py`
directly (one source of truth for the formats). Track ids are resolved via the
upstream `getSong` API reusing the phone's own per-request credentials — a
stable Subsonic contract, not Gonic's private DB schema — and Gonic's
`Child.path` (relative to its music root) joined onto the real library root
equals the absolute path the desktop stores; its POSIX dirname is the
`album_id` `/stats` keys on. Teeing is wrapped so any failure is logged and
swallowed — it can never break playback. Scrobbles don't carry actual
seconds-listened, so a play logs the full track length (documented fidelity
loss); album/artist stars are ignored (no desktop equivalent).

Deployed as a systemd **user** service `lp-tee.service`
(`~/.config/systemd/user/`), `127.0.0.1:4748` → Gonic `4747`.

**Committed (2026-07-14):** `https://fedora.tailc2dcbd.ts.net:8444` now proxies
to the tee (`4748`), so Amperfy stays on its existing `:8444` URL and all phone
star/scrobble traffic flows through. The trial `:8445` has been removed.

Rollback (send Amperfy straight back to Gonic if the proxy ever misbehaves):
```bash
tailscale serve --bg --https=8444 http://127.0.0.1:4747   # 8444 -> Gonic direct
systemctl --user disable --now lp-tee
```

Manage: `systemctl --user {status,restart,stop} lp-tee`, logs
`journalctl --user -u lp-tee -f` (tee actions log each ★/☆/▶).

Remaining one-directional gap: desktop→phone. A heart set on the *desktop*
won't reflect on the phone until Gonic is told (`star`) — a future small
reconcile step if it matters. Phone→desktop (the common direction) is covered.

## Data-of-record caveat (the unity question)

Right now the phone's **favourites, playlists, and play history live in
Navidrome's DB**, *not* in `favorites.json` / `plays.jsonl`. So phone hearts
don't show on the desktop tracklist, and `/stats` is blind to phone listening.

Next phase to re-unify (deliberately deferred until CarPlay/reliability are
confirmed worth it): a small Qt-free **tee proxy** in front of Navidrome that
forwards every `/rest/*` request untouched but tees three of them —
`scrobble` → `plays.jsonl`, `star`/`unstar` → `favorites.json` — resolving
Navidrome song IDs back to file paths. That gives near-real-time unity with
real play timestamps. Note Navidrome stores only play *count* + *last played*,
not per-play history, so a periodic-poll sync (the simpler alternative) would
lose timestamps and blur `/stats` — the tee is the better design if we do it.
Two fidelity losses are unavoidable either way: the *client* decides what
counts as a play, and scrobbles don't carry seconds-listened (they'd log track
duration, not the measured ≥50%/4-min figure the lp accumulator computes).

## Managing it

```bash
systemctl --user status navidrome           # health
systemctl --user restart navidrome           # restart
podman logs -f systemd-navidrome             # live logs / scan progress
systemctl --user stop navidrome              # stop
```

Update the image: `podman pull docker.io/deluan/navidrome:latest` then
`systemctl --user restart navidrome` (the unit also has `AutoUpdate=registry`
for `podman auto-update`). Rescan on demand from the web UI, or it auto-scans
hourly (`ND_SCANSCHEDULE=1h`).

## Full rollback

```bash
systemctl --user disable --now navidrome
rm ~/.config/containers/systemd/navidrome.container
systemctl --user daemon-reload
tailscale serve --https=8443 off
rm -rf ~/.local/share/navidrome          # optional: drop the index/DB
```

The lp PWA and its `tailscale serve` on `/` are untouched by any of this.
