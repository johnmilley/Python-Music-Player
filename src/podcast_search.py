# Podcast search dialog using iTunes Search API

import json
import urllib.request
import urllib.parse

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QLineEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap

from artwork_finder import _ssl_ctx, ImageLoader
import theme


class PodcastResult(QWidget):
    """Single podcast result row with thumbnail, info, and subscribe button."""
    subscribe_requested = pyqtSignal(str)  # feedUrl

    def __init__(self, result, index, theme_dict, fs=None):
        super().__init__()
        t = theme_dict
        fs = fs or theme.DEFAULT_SIZE
        self.index = index
        self.feed_url = result.get('feedUrl', '')

        layout = QHBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        # Thumbnail placeholder
        self.thumb = QLabel()
        self.thumb.setFixedSize(100, 100)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(f'background: {t["bg_alt"]}; border: 1px solid {t["border"]};')
        self.thumb.setText('...')
        layout.addWidget(self.thumb)

        # Info
        info_layout = QVBoxLayout()
        name = result.get('collectionName', 'Unknown')
        artist = result.get('artistName', 'Unknown')
        count = result.get('trackCount', '?')

        title_label = QLabel(f'<b>{name}</b>')
        title_label.setWordWrap(True)
        title_label.setStyleSheet(f'color: {t["fg"]}; font-family: {theme.FONT}; font-size: {fs + 2}pt; border: none;')
        detail_label = QLabel(f'{artist} - {count} episodes')
        detail_label.setStyleSheet(f'color: {t["fg"]}; font-family: {theme.FONT}; font-size: {fs}pt; border: none;')

        info_layout.addWidget(title_label)
        info_layout.addWidget(detail_label)
        info_layout.addStretch()
        layout.addLayout(info_layout, stretch=1)

        # Subscribe button
        btn = QPushButton('Subscribe')
        btn.setMinimumSize(80, 35)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {t['accent']};
                color: {t['selection_text']};
                border: none;
                font-family: {theme.FONT};
                font-size: {fs + 1}pt;
            }}
            QPushButton:hover {{ opacity: 0.8; }}
        """)
        btn.clicked.connect(lambda: self.subscribe_requested.emit(self.feed_url))
        layout.addWidget(btn)

        self.setLayout(layout)

    def set_thumbnail(self, pixmap):
        if not pixmap.isNull():
            self.thumb.setPixmap(pixmap.scaled(
                100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))


class PodcastSearchThread(QThread):
    """Search iTunes for podcasts."""
    finished = pyqtSignal(list)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        try:
            params = urllib.parse.urlencode({
                'term': self.query,
                'entity': 'podcast',
                'limit': 12,
            })
            url = f'https://itunes.apple.com/search?{params}'
            req = urllib.request.Request(url, headers={'User-Agent': 'lp-music-player/1.0'})
            data = urllib.request.urlopen(req, timeout=10, context=_ssl_ctx).read()
            results = json.loads(data).get('results', [])
            self.finished.emit(results)
        except Exception as e:
            print(f'Podcast search error: {e}')
            self.finished.emit([])


class PodcastSearchDialog(QDialog):
    """Dialog to search iTunes for podcasts and subscribe."""
    feed_subscribed = pyqtSignal(str)  # feedUrl

    def __init__(self, initial_query, theme_dict, parent=None, fs=None):
        super().__init__(parent)
        self.theme_dict = theme_dict
        self.fs = fs = fs or theme.DEFAULT_SIZE
        self._loaders = []

        self.setWindowTitle('Search Podcasts')
        self.setMinimumSize(500, 400)
        self.resize(550, 500)

        t = theme_dict
        self.setStyleSheet(f"""
            QDialog {{ background-color: {t['bg']}; }}
            QScrollArea {{ border: none; background: {t['bg']}; }}
            QWidget#results-container {{ background: {t['bg']}; }}
        """)

        layout = QVBoxLayout()

        # Search bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Search for podcasts...')
        self.search_input.setText(initial_query)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {t['bg_alt']};
                color: {t['fg']};
                border: 1px solid {t['border']};
                font-family: {theme.FONT};
                font-size: {fs + 1}pt;
                padding: 6px;
            }}
        """)
        self.search_input.returnPressed.connect(self._on_search_submit)
        self.search_input.installEventFilter(self)
        search_layout.addWidget(self.search_input)

        search_btn = QPushButton('Search')
        search_btn.setFixedSize(70, 35)
        search_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t['accent']};
                color: {t['selection_text']};
                border: none;
                font-family: {theme.FONT};
                font-size: {fs + 1}pt;
            }}
        """)
        search_btn.clicked.connect(self._on_search_submit)
        search_layout.addWidget(search_btn)
        layout.addLayout(search_layout)

        # Status
        self.status = QLabel()
        self.status.setStyleSheet(f'color: {t["fg"]}; font-family: {theme.FONT}; font-size: {fs + 1}pt;')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        # Scroll area for results
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

        # Start search
        if initial_query:
            self._search(initial_query)

    def eventFilter(self, obj, event):
        if obj is self.search_input and event.type() == event.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._on_search_submit()
                return True
        return super().eventFilter(obj, event)

    def _on_search_submit(self):
        query = self.search_input.text().strip()
        if query:
            self._search(query)

    def _search(self, query):
        # Clear previous results
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._loaders.clear()

        self.status.setText(f'Searching for: {query}')
        self._search_thread = PodcastSearchThread(query)
        self._search_thread.finished.connect(self._on_results)
        self._search_thread.start()

    def _on_results(self, results):
        if not results:
            self.status.setText('No results found.')
            return

        self.status.setText(f'Found {len(results)} results:')

        for i, result in enumerate(results):
            row = PodcastResult(result, i, self.theme_dict, self.fs)
            row.subscribe_requested.connect(self._on_subscribe)
            self.results_layout.addWidget(row)

            # Load thumbnail
            art_url = result.get('artworkUrl100', '')
            if art_url:
                loader = ImageLoader(i, art_url)
                loader.finished.connect(lambda idx, px: self._set_thumb(idx, px))
                self._loaders.append(loader)
                loader.start()

    def _set_thumb(self, index, pixmap):
        for i in range(self.results_layout.count()):
            widget = self.results_layout.itemAt(i).widget()
            if isinstance(widget, PodcastResult) and widget.index == index:
                widget.set_thumbnail(pixmap)
                break

    def _on_subscribe(self, feed_url):
        if feed_url:
            self.feed_subscribed.emit(feed_url)
            self.accept()
