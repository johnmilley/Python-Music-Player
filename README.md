# lp

A PyQt5 desktop music player with podcast and internet radio support, synced
lyrics, and vim-style keyboard navigation.

## Features

- **Music** — browse your filesystem, play local audio files (mp3, flac, m4a,
  and anything `mutagen`/`tinytag` can read), tracklist with album art
- **Podcasts** — subscribe to RSS feeds, search via iTunes, download and play
  episodes, resume playback position
- **Radio** — save and stream internet radio stations, search via Radio
  Browser, live now-playing metadata
- **Lyrics** — synced (`.lrc`) or plain lyrics fetched from LRCLIB, auto-scroll
  and click-to-seek on the active line
- **Max mode** (`Shift+M`) — fullscreen album art + lyrics view
- **Vim-style navigation** — `j`/`k`/`h`/`l`, `/` to search, full keyboard
  control over playback (see [docs/keyboard-shortcuts.md](docs/keyboard-shortcuts.md))
- **Theming** — light/dark themes with an accent color auto-extracted from
  album art
- Panel layout (library / tracklist / lyrics) that remembers your sizes
  across toggles — see [docs/display-modes.md](docs/display-modes.md)

See [docs/architecture.md](docs/architecture.md) for a full module breakdown.

## Installing (prebuilt binaries)

Download the latest build for your OS from the
[Releases page](https://github.com/johnmilley/Python-Music-Player/releases):

- **Linux** — `lp-linux.tar.gz`
- **macOS** — `lp-macos.tar.gz`
- **Windows** — `lp-windows.zip`

Extract and run the `lp` executable (`lp.app` on macOS). On Linux, you can
run `install-icon.sh` afterward to install the desktop entry and icon.

## Running from source

Requires Python 3.12.

```bash
git clone https://github.com/johnmilley/Python-Music-Player.git
cd Python-Music-Player
python -m venv venv
source venv/bin/activate  # on Windows: venv\Scripts\activate
pip install -r requirements.txt
python src/app.py
```

Linux additionally needs system packages for audio and windowing:

```bash
sudo apt-get install -y libasound2-dev libxcb-xinerama0 libxkbcommon-x11-0
```

## Building a standalone executable

```bash
pip install -r requirements.txt
pyinstaller lp.spec
```

The build is written to `dist/lp` (`dist/lp.app` on macOS). CI builds and
publishes binaries for Linux, macOS, and Windows automatically whenever a
`v*` tag is pushed (see `.github/workflows/build.yml`).

## License

MIT — see [LICENSE](LICENSE).
