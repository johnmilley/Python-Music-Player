# Radio station search dialog using Radio Browser API

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


class RadioResult(QWidget):
    """Single radio station result row."""
    add_requested = pyqtSignal(str, str)  # name, stream_url

    def __init__(self, result, index, theme_dict):
        super().__init__()
        t = theme_dict
        self.index = index
        self.station_name = result.get('name', 'Unknown')
        self.stream_url = result.get('url_resolved') or result.get('url', '')

        layout = QHBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        # Favicon placeholder
        self.thumb = QLabel()
        self.thumb.setFixedSize(60, 60)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(f'background: {t["bg_alt"]}; border: 1px solid {t["border"]};')
        self.thumb.setText('...')
        layout.addWidget(self.thumb)

        # Info
        info_layout = QVBoxLayout()
        name_label = QLabel(f'<b>{self.station_name}</b>')
        name_label.setWordWrap(True)
        name_label.setStyleSheet(f'color: {t["fg"]}; font-family: {theme.FONT}; font-size: 12pt; border: none;')

        country = result.get('country', '')
        tags = result.get('tags', '')
        detail_parts = [p for p in [country, tags] if p]
        detail_text = ' - '.join(detail_parts) if detail_parts else ''
        detail_label = QLabel(detail_text)
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet(f'color: {t["fg"]}; font-family: {theme.FONT}; font-size: 10pt; border: none;')

        codec = result.get('codec', '')
        bitrate = result.get('bitrate', 0)
        tech_parts = [p for p in [codec, f'{bitrate}kbps' if bitrate else ''] if p]
        tech_label = QLabel(' '.join(tech_parts))
        tech_label.setStyleSheet(f'color: {t["fg"]}; font-family: {theme.FONT}; font-size: 9pt; border: none; opacity: 0.6;')

        info_layout.addWidget(name_label)
        info_layout.addWidget(detail_label)
        info_layout.addWidget(tech_label)
        info_layout.addStretch()
        layout.addLayout(info_layout, stretch=1)

        # Add button
        btn = QPushButton('Add')
        btn.setMinimumSize(60, 35)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {t['accent']};
                color: {t['selection_text']};
                border: none;
                font-family: {theme.FONT};
                font-size: 11pt;
            }}
            QPushButton:hover {{ opacity: 0.8; }}
        """)
        btn.clicked.connect(lambda: self.add_requested.emit(self.station_name, self.stream_url))
        layout.addWidget(btn)

        self.setLayout(layout)

    def set_thumbnail(self, pixmap):
        if not pixmap.isNull():
            self.thumb.setPixmap(pixmap.scaled(
                60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))


class RadioSearchThread(QThread):
    """Search Radio Browser API for stations."""
    finished = pyqtSignal(list)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        try:
            encoded = urllib.parse.quote(self.query)
            url = (f'https://de1.api.radio-browser.info/json/stations/byname/{encoded}'
                   f'?limit=12&order=clickcount&reverse=true')
            req = urllib.request.Request(url, headers={'User-Agent': 'lp-music-player/1.0'})
            data = urllib.request.urlopen(req, timeout=10, context=_ssl_ctx).read()
            results = json.loads(data)
            self.finished.emit(results)
        except Exception as e:
            print(f'Radio search error: {e}')
            self.finished.emit([])


class RadioSearchDialog(QDialog):
    """Dialog to search for radio stations and add them."""
    station_added = pyqtSignal(str, str)  # name, stream_url

    def __init__(self, initial_query, theme_dict, parent=None):
        super().__init__(parent)
        self.theme_dict = theme_dict
        self._loaders = []

        self.setWindowTitle('Search Radio Stations')
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
        self.search_input.setPlaceholderText('Search for radio stations...')
        self.search_input.setText(initial_query)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {t['bg_alt']};
                color: {t['fg']};
                border: 1px solid {t['border']};
                font-family: {theme.FONT};
                font-size: 11pt;
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
                font-size: 11pt;
            }}
        """)
        search_btn.clicked.connect(self._on_search_submit)
        search_layout.addWidget(search_btn)
        layout.addLayout(search_layout)

        # Status
        self.status = QLabel()
        self.status.setStyleSheet(f'color: {t["fg"]}; font-family: {theme.FONT}; font-size: 11pt;')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        # Scroll area
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
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._loaders.clear()

        self.status.setText(f'Searching for: {query}')
        self._search_thread = RadioSearchThread(query)
        self._search_thread.finished.connect(self._on_results)
        self._search_thread.start()

    def _on_results(self, results):
        if not results:
            self.status.setText('No results found.')
            return

        self.status.setText(f'Found {len(results)} results:')

        for i, result in enumerate(results):
            row = RadioResult(result, i, self.theme_dict)
            row.add_requested.connect(self._on_add)
            self.results_layout.addWidget(row)

            # Load favicon
            favicon = result.get('favicon', '')
            if favicon:
                loader = ImageLoader(i, favicon)
                loader.finished.connect(lambda idx, px: self._set_thumb(idx, px))
                self._loaders.append(loader)
                loader.start()

    def _set_thumb(self, index, pixmap):
        for i in range(self.results_layout.count()):
            widget = self.results_layout.itemAt(i).widget()
            if isinstance(widget, RadioResult) and widget.index == index:
                widget.set_thumbnail(pixmap)
                break

    def _on_add(self, name, stream_url):
        if name and stream_url:
            self.station_added.emit(name, stream_url)
            self.accept()
