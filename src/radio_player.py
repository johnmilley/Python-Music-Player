# Thin wrapper around QMediaPlayer for radio streaming

import hashlib
import json
import os
import urllib.parse
import urllib.request
import ssl
from pathlib import Path

from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtCore import QUrl, pyqtSignal, QObject, QThread, Qt, QSize
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QLineEdit
)

import theme

try:
    import certifi
    _ssl_ctx = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _ssl_ctx = ssl.create_default_context()

# Cache directory — platform-appropriate location
import sys as _sys
if _sys.platform == 'darwin':
    CACHE_DIR = Path.home() / 'Library' / 'Caches' / 'lp' / 'radio'
elif _sys.platform == 'win32':
    CACHE_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'lp' / 'cache' / 'radio'
else:
    CACHE_DIR = Path.home() / '.cache' / 'lp' / 'radio'


def _crop_square(img):
    """Center-crop a QImage to a square."""
    w, h = img.width(), img.height()
    if w == h:
        return img
    side = min(w, h)
    x = (w - side) // 2
    y = (h - side) // 2
    return img.copy(x, y, side, side)
_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'


def station_art_path(station_name):
    """Return the cached art path for a station name."""
    slug = hashlib.md5(station_name.encode()).hexdigest()[:12]
    return CACHE_DIR / f'{slug}_logo.jpg'


# ── Background threads ──────────────────────────────────────────

class _ImageLoader(QThread):
    finished = pyqtSignal(int, QPixmap)

    def __init__(self, index, url):
        super().__init__()
        self.index = index
        self.url = url

    def run(self):
        try:
            req = urllib.request.Request(self.url,
                                        headers={'User-Agent': 'lp-music-player/1.0'})
            data = urllib.request.urlopen(req, timeout=10, context=_ssl_ctx).read()
            img = QImage()
            img.loadFromData(data)
            self.finished.emit(self.index, QPixmap.fromImage(img))
        except Exception:
            self.finished.emit(self.index, QPixmap())


class _SearchThread(QThread):
    """Search DuckDuckGo Images for station logos."""
    finished = pyqtSignal(list)  # list of {'title', 'thumbnail', 'image', 'source'}

    def __init__(self, query):
        super().__init__()
        self.query = query

    def _fetch(self, url, headers=None):
        hdrs = {'User-Agent': _UA}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, headers=hdrs)
        return urllib.request.urlopen(req, timeout=10, context=_ssl_ctx)

    def run(self):
        try:
            # Step 1: get vqd token from DDG search page
            q = urllib.parse.quote(self.query + ' radio logo')
            page = self._fetch(f'https://duckduckgo.com/?q={q}&iax=images&ia=images').read().decode()
            import re
            m = re.search(r'vqd=(["\'])([^"\']+)\1', page)
            if not m:
                # Fallback: try vqd in different format
                m = re.search(r'vqd=([\d-]+)', page)
            if not m:
                self.finished.emit([])
                return
            vqd = m.group(2) if m.lastindex == 2 else m.group(1)

            # Step 2: fetch image results
            params = urllib.parse.urlencode({
                'l': 'us-en', 'o': 'json', 'q': self.query + ' radio logo',
                'vqd': vqd, 'f': ',,,,,', 'p': '1'
            })
            resp = self._fetch(
                f'https://duckduckgo.com/i.js?{params}',
                headers={'Referer': 'https://duckduckgo.com/'}
            ).read()
            data = json.loads(resp)
            results = []
            for r in data.get('results', [])[:12]:
                results.append({
                    'title': r.get('title', ''),
                    'thumbnail': r.get('thumbnail', ''),
                    'image': r.get('image', ''),
                    'source': r.get('source', ''),
                })
            self.finished.emit(results)
        except Exception as e:
            print(f'DDG image search error: {e}')
            self.finished.emit([])


class _DownloadThread(QThread):
    finished = pyqtSignal(QPixmap, str)  # pixmap, local path

    def __init__(self, url, dest_path):
        super().__init__()
        self.url = url
        self.dest_path = dest_path

    def run(self):
        try:
            dest = Path(self.dest_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(self.url,
                                        headers={'User-Agent': _UA})
            data = urllib.request.urlopen(req, timeout=15, context=_ssl_ctx).read()
            img = QImage()
            if img.loadFromData(data) and not img.isNull():
                img = _crop_square(img)
                img.save(str(dest), 'JPEG')
                self.finished.emit(QPixmap.fromImage(img), str(dest))
                return
        except Exception:
            pass
        self.finished.emit(QPixmap(), '')


# ── Station art picker dialog ───────────────────────────────────

class StationArtDialog(QDialog):
    """Search for a station image via DuckDuckGo Images."""
    art_selected = pyqtSignal(QPixmap)  # emitted when user picks an image

    def __init__(self, station_name, theme_dict, parent=None):
        super().__init__(parent)
        self.station_name = station_name
        self.theme_dict = theme_dict
        self._loaders = []
        self._dest = str(station_art_path(station_name))

        self.setWindowTitle(f'Find image — {station_name}')
        self.setMinimumSize(480, 380)
        self.resize(520, 460)

        t = theme_dict
        self.setStyleSheet(f"""
            QDialog {{ background-color: {t['bg']}; }}
            QScrollArea {{ border: none; background: {t['bg']}; }}
            QWidget#results-container {{ background: {t['bg']}; }}
        """)

        layout = QVBoxLayout()

        # Search bar
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Search for station image...')
        self.search_input.setText(station_name)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {t['bg_alt']}; color: {t['fg']};
                border: 1px solid {t['border']};
                font-family: {theme.FONT}; font-size: 11pt; padding: 6px;
            }}
        """)
        self.search_input.returnPressed.connect(self._do_search)
        self.search_input.installEventFilter(self)
        search_row.addWidget(self.search_input)

        search_btn = QPushButton('Search')
        search_btn.setFixedSize(70, 35)
        search_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t['accent']}; color: {t['selection_text']};
                border: none; font-family: {theme.FONT}; font-size: 11pt;
            }}
        """)
        search_btn.clicked.connect(self._do_search)
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)

        # Status
        self.status = QLabel()
        self.status.setStyleSheet(
            f'color: {t["fg"]}; font-family: {theme.FONT}; font-size: 11pt;')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        # Results scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results_widget = QWidget()
        self.results_widget.setObjectName('results-container')
        self.results_layout = QVBoxLayout()
        self.results_layout.setAlignment(Qt.AlignTop)
        self.results_widget.setLayout(self.results_layout)
        self.scroll.setWidget(self.results_widget)
        layout.addWidget(self.scroll)

        self.setLayout(layout)
        self._do_search()

    def eventFilter(self, obj, event):
        if obj is self.search_input and event.type() == event.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._do_search()
                return True
        return super().eventFilter(obj, event)

    def _do_search(self):
        query = self.search_input.text().strip()
        if not query:
            return
        # Clear old results
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._loaders.clear()
        self.status.setText(f'Searching: {query}')
        self._search_thread = _SearchThread(query)
        self._search_thread.finished.connect(self._on_results)
        self._search_thread.start()

    def _on_results(self, results):
        if not results:
            self.status.setText('No results found.')
            return
        self.status.setText(f'{len(results)} results:')
        t = self.theme_dict
        for i, r in enumerate(results):
            row = self._make_row(i, r, t)
            self.results_layout.addWidget(row)
            thumb_url = r.get('thumbnail', '')
            if thumb_url:
                loader = _ImageLoader(i, thumb_url)
                loader.finished.connect(self._set_thumb)
                self._loaders.append(loader)
                loader.start()

    def _make_row(self, index, result, t):
        row = QWidget()
        row.setProperty('_index', index)
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        thumb = QLabel()
        thumb.setFixedSize(100, 100)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet(
            f'background: {t["bg_alt"]}; border: 1px solid {t["border"]};')
        thumb.setText('...')
        thumb.setObjectName(f'thumb-{index}')
        layout.addWidget(thumb)

        info = QVBoxLayout()
        title = result.get('title', '')
        source = result.get('source', '')
        title_lbl = QLabel(f'<b>{title}</b>')
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f'color: {t["fg"]}; font-family: {theme.FONT}; font-size: 11pt; border:none;')
        source_lbl = QLabel(source)
        source_lbl.setStyleSheet(
            f'color: {t["fg"]}; font-family: {theme.FONT}; font-size: 9pt; border:none; opacity:0.6;')
        info.addWidget(title_lbl)
        info.addWidget(source_lbl)
        info.addStretch()
        layout.addLayout(info, stretch=1)

        choose_btn = QPushButton('Use')
        choose_btn.setMinimumSize(60, 32)
        choose_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t['accent']}; color: {t['selection_text']};
                border: none; font-family: {theme.FONT}; font-size: 11pt;
            }}
        """)
        img_url = result.get('image', '')
        choose_btn.clicked.connect(lambda checked, u=img_url: self._choose(u))
        layout.addWidget(choose_btn)

        row.setLayout(layout)
        return row

    def _set_thumb(self, index, pixmap):
        for i in range(self.results_layout.count()):
            w = self.results_layout.itemAt(i).widget()
            if w and w.property('_index') == index:
                thumb = w.findChild(QLabel, f'thumb-{index}')
                if thumb and not pixmap.isNull():
                    thumb.setPixmap(pixmap.scaled(
                        100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                break

    def _choose(self, url):
        if not url:
            return
        self.status.setText('Downloading...')
        self._dl_thread = _DownloadThread(url, self._dest)
        self._dl_thread.finished.connect(self._on_downloaded)
        self._dl_thread.start()

    def _on_downloaded(self, pixmap, path):
        if pixmap.isNull():
            self.status.setText('Download failed.')
            return
        self.art_selected.emit(pixmap)
        self.accept()


# ── Radio player ────────────────────────────────────────────────

class RadioPlayer(QObject):
    """Streams radio URLs via QMediaPlayer."""

    state_changed = pyqtSignal(bool)  # True = playing
    metadata_changed = pyqtSignal(str)  # now-playing title string

    error_occurred = pyqtSignal(str)  # error message string

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer()
        self._player.stateChanged.connect(self._on_state)
        self._player.metaDataChanged.connect(self._on_metadata)
        self._player.error.connect(self._on_error)
        self._last_title = ''

    def _on_state(self, state):
        self.state_changed.emit(state == QMediaPlayer.PlayingState)

    def _on_error(self, error):
        if error != QMediaPlayer.NoError:
            msg = self._player.errorString() or 'Unknown playback error'
            print(f'LOG: Radio error: {msg}')
            self._player.stop()
            self.error_occurred.emit(msg)

    def _on_metadata(self):
        title = self._player.metaData('Title') or ''
        if isinstance(title, list):
            title = title[0] if title else ''
        title = str(title).strip()
        if title and title != self._last_title:
            self._last_title = title
            self.metadata_changed.emit(title)

    def play_stream(self, url):
        self._last_title = ''
        self._player.setMedia(QMediaContent(QUrl(url)))
        self._player.play()

    def pause(self):
        self._player.pause()

    def resume(self):
        self._player.play()

    def stop(self):
        self._player.stop()
        self._last_title = ''

    @property
    def is_playing(self):
        return self._player.state() == QMediaPlayer.PlayingState

    @property
    def volume(self):
        return self._player.volume()

    @volume.setter
    def volume(self, val):
        self._player.setVolume(int(val))
