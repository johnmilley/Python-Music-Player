# Artwork finder using iTunes Search API
# Searches for album artwork and allows downloading to album folder

import json
import urllib.request
import urllib.parse
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QImage

import theme

ITUNES_SEARCH_URL = 'https://itunes.apple.com/search'


class ImageLoader(QThread):
    """Load an image from URL in a background thread."""
    finished = pyqtSignal(int, QPixmap)

    def __init__(self, index, url):
        super().__init__()
        self.index = index
        self.url = url

    def run(self):
        try:
            data = urllib.request.urlopen(self.url, timeout=10).read()
            img = QImage()
            img.loadFromData(data)
            self.finished.emit(self.index, QPixmap.fromImage(img))
        except Exception:
            self.finished.emit(self.index, QPixmap())


class ArtworkResult(QWidget):
    """Single artwork result row with thumbnail and download button."""
    download_requested = pyqtSignal(str, str)  # hi_res_url, album_name

    def __init__(self, result, index, theme_dict):
        super().__init__()
        t = theme_dict
        self.result = result
        self.index = index

        # Build high-res URL (replace 100x100 with 1200x1200)
        art100 = result.get('artworkUrl100', '')
        self.hi_res_url = art100.replace('100x100bb', '1200x1200bb')
        self.preview_url = art100.replace('100x100bb', '300x300bb')

        layout = QHBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        # Thumbnail placeholder
        self.thumb = QLabel()
        self.thumb.setFixedSize(120, 120)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(f'background: {t["bg_alt"]}; border: 1px solid {t["border"]};')
        self.thumb.setText('...')
        layout.addWidget(self.thumb)

        # Info
        info_layout = QVBoxLayout()
        name = result.get('collectionName', 'Unknown')
        artist = result.get('artistName', 'Unknown')
        year = result.get('releaseDate', '')[:4]
        tracks = result.get('trackCount', '?')

        title_label = QLabel(f'<b>{name}</b>')
        title_label.setWordWrap(True)
        title_label.setStyleSheet(f'color: {t["fg"]}; font-family: {theme.FONT}; font-size: 12pt; border: none;')
        detail_label = QLabel(f'{artist} ({year}) - {tracks} tracks')
        detail_label.setStyleSheet(f'color: {t["fg"]}; font-family: {theme.FONT}; font-size: 10pt; border: none;')

        info_layout.addWidget(title_label)
        info_layout.addWidget(detail_label)
        info_layout.addStretch()
        layout.addLayout(info_layout, stretch=1)

        # Download button
        dl_btn = QPushButton('Save')
        dl_btn.setFixedSize(70, 35)
        dl_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t['accent']};
                color: {t['selection_text']};
                border: none;
                font-family: {theme.FONT};
                font-size: 11pt;
            }}
            QPushButton:hover {{ opacity: 0.8; }}
        """)
        dl_btn.clicked.connect(lambda: self.download_requested.emit(
            self.hi_res_url, name
        ))
        layout.addWidget(dl_btn)

        self.setLayout(layout)

    def set_thumbnail(self, pixmap):
        if not pixmap.isNull():
            self.thumb.setPixmap(pixmap.scaled(
                120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))


class ArtworkFinderDialog(QDialog):
    """Dialog to search iTunes for album artwork and save to album folder."""
    artwork_saved = pyqtSignal(str)  # path to saved file

    def __init__(self, artist, album_title, album_path, theme_dict, parent=None):
        super().__init__(parent)
        self.artist = artist or ''
        self.album_title = album_title or ''
        self.album_path = album_path
        self.theme_dict = theme_dict
        self._loaders = []

        self.setWindowTitle('Find Album Artwork')
        self.setMinimumSize(500, 400)
        self.resize(550, 500)

        t = theme_dict
        self.setStyleSheet(f"""
            QDialog {{ background-color: {t['bg']}; }}
            QScrollArea {{ border: none; background: {t['bg']}; }}
            QWidget#results-container {{ background: {t['bg']}; }}
        """)

        layout = QVBoxLayout()

        # Status label
        self.status = QLabel(f'Searching for: {self.artist} - {self.album_title}')
        self.status.setStyleSheet(f'color: {t["fg"]}; font-family: {theme.FONT}; font-size: 11pt;')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        # Scroll area for results
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.results_widget = QWidget()
        self.results_widget.setObjectName('results-container')
        self.results_layout = QVBoxLayout()
        self.results_layout.setAlignment(Qt.AlignTop)
        self.results_widget.setLayout(self.results_layout)
        self.scroll.setWidget(self.results_widget)
        layout.addWidget(self.scroll)

        self.setLayout(layout)

        # Start search
        self._search()

    def _search(self):
        query = f'{self.artist} {self.album_title}'.strip()
        if not query:
            self.status.setText('No artist/album info available.')
            return

        params = urllib.parse.urlencode({
            'term': query,
            'entity': 'album',
            'limit': 8,
        })
        url = f'{ITUNES_SEARCH_URL}?{params}'

        self._search_thread = SearchThread(url)
        self._search_thread.finished.connect(self._on_results)
        self._search_thread.start()

    def _on_results(self, results):
        if not results:
            self.status.setText('No results found.')
            return

        self.status.setText(f'Found {len(results)} results:')

        for i, result in enumerate(results):
            row = ArtworkResult(result, i, self.theme_dict)
            row.download_requested.connect(self._download_artwork)
            self.results_layout.addWidget(row)

            # Load thumbnail in background
            preview_url = row.preview_url
            if preview_url:
                loader = ImageLoader(i, preview_url)
                loader.finished.connect(lambda idx, px: self._set_thumb(idx, px))
                self._loaders.append(loader)
                loader.start()

    def _set_thumb(self, index, pixmap):
        for i in range(self.results_layout.count()):
            widget = self.results_layout.itemAt(i).widget()
            if isinstance(widget, ArtworkResult) and widget.index == index:
                widget.set_thumbnail(pixmap)
                break

    def _download_artwork(self, url, album_name):
        self.status.setText(f'Downloading artwork...')
        self._dl_thread = DownloadThread(url, self.album_path)
        self._dl_thread.finished.connect(self._on_downloaded)
        self._dl_thread.start()

    def _on_downloaded(self, path):
        if path:
            self.status.setText(f'Saved to {path}')
            self.artwork_saved.emit(path)
            self.accept()
        else:
            self.status.setText('Download failed.')


class SearchThread(QThread):
    finished = pyqtSignal(list)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            req = urllib.request.Request(self.url, headers={
                'User-Agent': 'lp-music-player/1.0'
            })
            data = urllib.request.urlopen(req, timeout=10).read()
            parsed = json.loads(data)
            self.finished.emit(parsed.get('results', []))
        except Exception as e:
            print(f'Artwork search error: {e}')
            self.finished.emit([])


class DownloadThread(QThread):
    finished = pyqtSignal(str)

    def __init__(self, url, album_path):
        super().__init__()
        self.url = url
        self.album_path = album_path

    def run(self):
        try:
            dest = Path(self.album_path) / 'cover.jpg'
            # Back up existing cover if present
            if dest.exists():
                n = 1
                while (Path(self.album_path) / f'cover_{n}.jpg').exists():
                    n += 1
                dest.rename(Path(self.album_path) / f'cover_{n}.jpg')
            req = urllib.request.Request(self.url, headers={
                'User-Agent': 'lp-music-player/1.0'
            })
            data = urllib.request.urlopen(req, timeout=30).read()
            dest.write_bytes(data)
            self.finished.emit(str(dest))
        except Exception as e:
            print(f'Artwork download error: {e}')
            self.finished.emit('')
