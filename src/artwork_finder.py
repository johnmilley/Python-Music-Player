# Artwork finder using iTunes Search API
# Searches for album artwork and allows downloading to album folder

import json
import os
import re
import ssl
import sys
import urllib.request
import urllib.parse
from pathlib import Path


def _make_ssl_ctx():
    if getattr(sys, 'frozen', False):
        bundle_dir = sys._MEIPASS
        ca = os.path.join(bundle_dir, 'certifi', 'cacert.pem')
        if os.path.isfile(ca):
            return ssl.create_default_context(cafile=ca)
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_ssl_ctx = _make_ssl_ctx()

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QSizePolicy, QLineEdit, QProgressBar, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QImage

import theme

ITUNES_SEARCH_URL = 'https://itunes.apple.com/search'
DISCOGS_API = 'https://api.discogs.com'
USER_AGENT = 'lp-music-player/1.0'


class ImageLoader(QThread):
    """Load an image from URL in a background thread."""
    finished = pyqtSignal(int, QPixmap)

    def __init__(self, index, url):
        super().__init__()
        self.index = index
        self.url = url

    def run(self):
        try:
            req = urllib.request.Request(self.url,
                                         headers={'User-Agent': USER_AGENT})
            data = urllib.request.urlopen(req, timeout=10, context=_ssl_ctx).read()
            img = QImage()
            img.loadFromData(data)
            self.finished.emit(self.index, QPixmap.fromImage(img))
        except Exception:
            self.finished.emit(self.index, QPixmap())


class DiscogsSearchThread(QThread):
    """Search Discogs for vinyl releases and collect their scanned images.

    Discogs catalogs physical pressings, so releases carry collector scans
    of the whole package — back covers, labels, gatefolds, inserts — which
    is exactly what the 'extra art' flow wants. Works unauthenticated
    (rate limit 25 req/min; one search here costs ~4 requests).
    """
    finished = pyqtSignal(list)  # dicts: thumb, url, title, detail

    MAX_RELEASES = 3   # release lookups per search (1 request each)
    MAX_IMAGES = 18

    def __init__(self, artist, album, query=''):
        super().__init__()
        self.artist = artist
        self.album = album
        self.query = query  # user-typed free text overrides artist/album

    def _get_json(self, url):
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        data = urllib.request.urlopen(req, timeout=10, context=_ssl_ctx).read()
        return json.loads(data)

    def run(self):
        try:
            if self.query:
                params = {'q': self.query}
            else:
                params = {'artist': self.artist, 'release_title': self.album}
            params.update({'type': 'release', 'format': 'Vinyl', 'per_page': 5})
            url = f'{DISCOGS_API}/database/search?{urllib.parse.urlencode(params)}'
            results = self._get_json(url).get('results', [])
            if not results and not self.query:
                # Looser full-text fallback (also matches non-vinyl releases)
                params = {'q': f'{self.artist} {self.album}'.strip(),
                          'type': 'release', 'per_page': 5}
                url = f'{DISCOGS_API}/database/search?{urllib.parse.urlencode(params)}'
                results = self._get_json(url).get('results', [])

            images = []
            for r in results[:self.MAX_RELEASES]:
                rid = r.get('id')
                if not rid:
                    continue
                release = self._get_json(f'{DISCOGS_API}/releases/{rid}')
                title = r.get('title') or release.get('title', '')
                year = release.get('year') or ''
                fmt = ' '.join((r.get('format') or [])[:2])
                for img in release.get('images') or []:
                    if not img.get('uri'):
                        continue
                    kind = 'front' if img.get('type') == 'primary' else 'extra'
                    images.append({
                        'thumb': img.get('uri150', ''),
                        'url': img['uri'],
                        'title': title,
                        'detail': f"{kind} · {img.get('width', '?')}×"
                                  f"{img.get('height', '?')} · "
                                  f"{fmt} {year}".strip(),
                    })
                if len(images) >= self.MAX_IMAGES:
                    break
            self.finished.emit(images[:self.MAX_IMAGES])
        except Exception as e:
            print(f'Discogs search error: {e}')
            self.finished.emit([])


def finder_dialog_qss(t, fs=None):
    """One stylesheet for the artwork-search dialogs (album art, extra art,
    and radio's station art picker): themed result rows with an accent-tint
    hover, accent save buttons/checkboxes, and the app's minimal scrollbar.
    Rows opt in via object names (#result-row, #row-thumb, #row-title,
    #row-detail, #section-header, #status-label, #accent-btn).

    fs is the app's text-size setting so these dialogs scale with it like
    everything else (Ctrl+=/Ctrl+-, the Text Size dialog)."""
    accent = t['accent']
    fg_dim = t.get('fg_dim', t['fg'])
    fs = fs or theme.DEFAULT_SIZE
    return f"""
        QDialog {{ background-color: {t['bg']}; }}
        QScrollArea {{ border: none; background: {t['bg']}; }}
        QWidget#results-container {{ background: {t['bg']}; }}
        #result-row {{
            background: transparent;
            border-radius: 6px;
        }}
        #result-row:hover {{ background-color: {theme._alpha(accent, 22)}; }}
        #row-thumb {{
            background: {t['bg_alt']};
            border: 1px solid {t['border']};
            color: {fg_dim};
            font-size: {fs + 4}pt;
        }}
        #row-title {{
            color: {t['fg']}; background: transparent;
            font-family: {theme.FONT}; font-size: {fs + 1}pt;
        }}
        #row-detail {{
            color: {fg_dim}; background: transparent;
            font-family: {theme.FONT}; font-size: {max(fs - 1, 7)}pt;
        }}
        #section-header {{
            color: {fg_dim}; background: transparent;
            font-family: {theme.FONT}; font-size: {max(fs - 1, 7)}pt;
            font-weight: bold;
            padding: 10px 8px 2px 8px;
        }}
        #status-label {{
            color: {fg_dim};
            font-family: {theme.FONT}; font-size: {fs}pt;
        }}
        QCheckBox {{ background: transparent; }}
        QCheckBox::indicator {{
            width: 18px; height: 18px;
            border: 1px solid {t['border']};
            border-radius: 4px;
            background: {t['bg']};
        }}
        QCheckBox::indicator:hover {{ border-color: {accent}; }}
        QCheckBox::indicator:checked {{
            background-color: {accent};
            border-color: {accent};
        }}
        QLineEdit {{
            background-color: {t['bg_alt']};
            color: {t['fg']};
            border: 1px solid {t['border']};
            font-family: {theme.FONT};
            font-size: {fs + 1}pt;
            padding: 6px;
        }}
        QLineEdit:focus {{ border: 1px solid {accent}; }}
        #accent-btn {{
            background: {accent};
            color: {t['selection_text']};
            border: none;
            font-family: {theme.FONT};
            font-size: {fs + 1}pt;
            padding: 5px 14px;
        }}
        #accent-btn:hover {{ background: {theme._alpha(accent, 200)}; }}
        #accent-btn:disabled {{ background: {t['bg_alt']}; color: {fg_dim}; }}
        QProgressBar {{ border: none; background: {t['bg_alt']}; }}
        QProgressBar::chunk {{ background-color: {accent}; }}
        {theme.minimal_scrollbar_qss(t, 'QScrollArea')}
    """


def _build_result_row(row, title_html, detail_text, selectable, checked):
    """Shared layout for a result row: thumbnail | title/detail | control.

    All colors/fonts come from the dialog-level stylesheet via object names
    (#result-row, #row-thumb, #row-title, #row-detail, #accent-btn), so the
    rows stay visually consistent without per-widget style strings.
    """
    row.setObjectName('result-row')
    row.setAttribute(Qt.WA_StyledBackground, True)
    if selectable:
        row.setCursor(Qt.PointingHandCursor)

    layout = QHBoxLayout(row)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(12)

    row.thumb = QLabel('…')
    row.thumb.setObjectName('row-thumb')
    row.thumb.setFixedSize(120, 120)
    row.thumb.setAlignment(Qt.AlignCenter)
    layout.addWidget(row.thumb)

    info_layout = QVBoxLayout()
    info_layout.setSpacing(2)
    title_label = QLabel(title_html)
    title_label.setObjectName('row-title')
    title_label.setWordWrap(True)
    detail_label = QLabel(detail_text)
    detail_label.setObjectName('row-detail')
    info_layout.addWidget(title_label)
    info_layout.addWidget(detail_label)
    info_layout.addStretch()
    layout.addLayout(info_layout, stretch=1)

    if selectable:
        row.checkbox = QCheckBox()
        row.checkbox.setToolTip('Select for saving')
        row.checkbox.setCursor(Qt.PointingHandCursor)
        row.checkbox.setChecked(checked)
        layout.addWidget(row.checkbox)
        layout.addSpacing(4)
    else:
        row.save_btn = QPushButton('Save')
        row.save_btn.setObjectName('accent-btn')
        row.save_btn.setCursor(Qt.PointingHandCursor)
        row.save_btn.setMinimumSize(70, 35)
        layout.addWidget(row.save_btn)


class ArtworkResult(QWidget):
    """Single artwork result row with thumbnail and download/select control.

    selectable=True (multi-image 'find more art' mode) shows a checkbox
    instead of an immediate-download Save button, so several images across
    one or more searches can be queued and saved together.
    """
    download_requested = pyqtSignal(str, str)  # hi_res_url, album_name
    selection_changed = pyqtSignal(bool, str, str)  # checked, hi_res_url, name

    def __init__(self, result, index, theme_dict, selectable=False, checked=False):
        super().__init__()
        self.result = result
        self.index = index
        self._selectable = selectable

        # Build high-res URL (replace 100x100 with 3000x3000)
        art100 = result.get('artworkUrl100', '')
        self.hi_res_url = art100.replace('100x100bb', '3000x3000bb')
        self.preview_url = art100.replace('100x100bb', '300x300bb')

        name = result.get('collectionName', 'Unknown')
        artist = result.get('artistName', 'Unknown')
        year = result.get('releaseDate', '')[:4]
        tracks = result.get('trackCount', '?')

        _build_result_row(self, f'<b>{name}</b>',
                          f'{artist} ({year}) · {tracks} tracks',
                          selectable, checked)
        if selectable:
            self.checkbox.toggled.connect(
                lambda on: self.selection_changed.emit(on, self.hi_res_url, name))
        else:
            self.save_btn.clicked.connect(lambda: self.download_requested.emit(
                self.hi_res_url, name))

    def mousePressEvent(self, event):
        # The whole row is a click target in multi-select mode
        if self._selectable and event.button() == Qt.LeftButton:
            self.checkbox.toggle()
        super().mousePressEvent(event)

    def set_thumbnail(self, pixmap):
        if not pixmap.isNull():
            self.thumb.setText('')
            self.thumb.setPixmap(pixmap.scaled(
                120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))


class DiscogsImageRow(QWidget):
    """Single Discogs image result: thumbnail, pressing info, save/select control."""
    download_requested = pyqtSignal(str, str)  # full_url, name
    selection_changed = pyqtSignal(bool, str, str)  # checked, url, name

    def __init__(self, img, index, theme_dict, selectable=False, checked=False):
        super().__init__()
        self.index = index
        self._selectable = selectable

        _build_result_row(self, f'<b>{img["title"]}</b>', img['detail'],
                          selectable, checked)
        if selectable:
            self.checkbox.toggled.connect(
                lambda on: self.selection_changed.emit(on, img['url'], img['title']))
        else:
            self.save_btn.clicked.connect(lambda: self.download_requested.emit(
                img['url'], img['title']))

    def mousePressEvent(self, event):
        if self._selectable and event.button() == Qt.LeftButton:
            self.checkbox.toggle()
        super().mousePressEvent(event)

    def set_thumbnail(self, pixmap):
        if not pixmap.isNull():
            self.thumb.setText('')
            self.thumb.setPixmap(pixmap.scaled(
                120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))


class ArtworkFinderDialog(QDialog):
    """Dialog to search iTunes for album artwork and save to album folder."""
    artwork_saved = pyqtSignal(str)  # path to saved file

    def __init__(self, artist, album_title, album_path, theme_dict, parent=None,
                 extra=False, fs=None):
        super().__init__(parent)
        self.artist = artist or ''
        self.album_title = album_title or ''
        self.album_path = album_path
        self.theme_dict = theme_dict
        self.extra = extra  # save alongside the cover instead of replacing it
        self._loaders = []
        # url -> title, kept across searches so picks from an earlier
        # search aren't lost when a later search replaces the result rows
        self._selected = {}

        self.setWindowTitle('Find More Album Art' if extra
                            else 'Find Album Artwork')
        self.setMinimumSize(500, 400)
        self.resize(550, 500)

        self.setStyleSheet(finder_dialog_qss(theme_dict, fs))
        layout = QVBoxLayout()

        # Search bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Search for album artwork...')
        self.search_input.setText(
            f'{self._clean_query(self.artist)} {self._clean_query(self.album_title)}'.strip()
        )
        self.search_input.returnPressed.connect(self._on_search_submit)
        # Prevent Enter from closing the dialog (QDialog default behaviour)
        self.search_input.installEventFilter(self)
        search_layout.addWidget(self.search_input)

        search_btn = QPushButton('Search')
        search_btn.setObjectName('accent-btn')
        search_btn.setCursor(Qt.PointingHandCursor)
        search_btn.setFixedSize(80, 35)
        search_btn.clicked.connect(self._on_search_submit)
        search_layout.addWidget(search_btn)
        layout.addLayout(search_layout)

        # Multi-select footer: pick images across one or more searches,
        # then save them all in one go
        if self.extra:
            select_row = QHBoxLayout()
            self.selected_label = QLabel('0 selected')
            self.selected_label.setObjectName('status-label')
            select_row.addWidget(self.selected_label)
            select_row.addStretch()
            self.save_selected_btn = QPushButton('Save Selected')
            self.save_selected_btn.setObjectName('accent-btn')
            self.save_selected_btn.setCursor(Qt.PointingHandCursor)
            self.save_selected_btn.setEnabled(False)
            self.save_selected_btn.clicked.connect(self._save_selected)
            select_row.addWidget(self.save_selected_btn)
            layout.addLayout(select_row)

        # Status label
        self.status = QLabel()
        self.status.setObjectName('status-label')
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
        # Results grouped by source, so async arrivals never interleave
        self.itunes_section = QVBoxLayout()
        self.discogs_section = QVBoxLayout()
        self.results_layout.addLayout(self.itunes_section)
        self.results_layout.addLayout(self.discogs_section)
        self.scroll.setWidget(self.results_widget)
        layout.addWidget(self.scroll)

        self.setLayout(layout)

        # Start search
        self._search()

    def eventFilter(self, obj, event):
        # Block Enter/Return from propagating to QDialog (which would close it)
        if obj is self.search_input and event.type() == event.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._on_search_submit()
                return True
        return super().eventFilter(obj, event)

    def _on_search_submit(self):
        query = self.search_input.text().strip()
        if query:
            self._search(query)

    @staticmethod
    def _clean_query(text):
        """Strip years, edition tags, and brackets for a cleaner search."""
        text = re.sub(r'\(.*?\)|\[.*?\]', '', text)   # remove bracketed text
        text = re.sub(r'\b(19|20)\d{2}\b', '', text)  # remove years
        text = re.sub(r'[-_]+', ' ', text)             # dashes/underscores to spaces
        return ' '.join(text.split()).strip()

    def _search(self, query=None):
        typed = query is not None  # user-typed query vs. album metadata
        artist = self._clean_query(self.artist)
        album = self._clean_query(self.album_title)
        if query is None:
            query = f'{artist} {album}'.strip()
        if not query:
            self.status.setText('No artist/album info available.')
            return

        # Clear previous results
        for section in (self.itunes_section, self.discogs_section):
            while section.count():
                item = section.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        self._loaders.clear()

        self.status.setText(f'Searching for: {query}')
        self._found = {'iTunes': None}

        params = urllib.parse.urlencode({
            'term': query,
            'entity': 'album',
            'limit': 8,
        })
        url = f'{ITUNES_SEARCH_URL}?{params}'

        self._search_thread = SearchThread(url, query)
        self._search_thread.finished.connect(self._on_results)
        self._search_thread.start()

        # Extra-art mode also searches Discogs — pressings there carry
        # collector scans of backs, labels, gatefolds and inserts
        if self.extra:
            self._found['Discogs'] = None
            self._discogs_thread = DiscogsSearchThread(
                artist, album, query if typed else '')
            self._discogs_thread.finished.connect(self._on_discogs_results)
            self._discogs_thread.start()

    def _update_status(self):
        parts = [f'{name}: {n} result{"s" if n != 1 else ""}'
                 for name, n in self._found.items() if n is not None]
        self.status.setText('  ·  '.join(parts))

    def _section_header(self, text):
        label = QLabel(text.upper())
        label.setObjectName('section-header')
        return label

    def _on_results(self, results):
        self._found['iTunes'] = len(results)
        self._update_status()
        if not results:
            return

        if self.extra:
            self.itunes_section.addWidget(self._section_header('iTunes — covers'))

        for i, result in enumerate(results):
            art100 = result.get('artworkUrl100', '')
            hi_res_url = art100.replace('100x100bb', '3000x3000bb')
            row = ArtworkResult(result, i, self.theme_dict,
                                selectable=self.extra,
                                checked=hi_res_url in self._selected)
            if self.extra:
                row.selection_changed.connect(self._on_selection_changed)
            else:
                row.download_requested.connect(self._download_artwork)
            self.itunes_section.addWidget(row)

            # Load thumbnail in background
            preview_url = row.preview_url
            if preview_url:
                loader = ImageLoader(i, preview_url)
                loader.finished.connect(lambda idx, px: self._set_thumb(idx, px))
                self._loaders.append(loader)
                loader.start()

    def _on_discogs_results(self, images):
        self._found['Discogs'] = len(images)
        self._update_status()
        if not images:
            return

        self.discogs_section.addWidget(
            self._section_header('Discogs — backs, labels, inserts'))
        for i, img in enumerate(images):
            row = DiscogsImageRow(img, i, self.theme_dict,
                                  selectable=self.extra,
                                  checked=img['url'] in self._selected)
            if self.extra:
                row.selection_changed.connect(self._on_selection_changed)
            else:
                row.download_requested.connect(self._download_artwork)
            self.discogs_section.addWidget(row)
            if img['thumb']:
                loader = ImageLoader(i, img['thumb'])
                loader.finished.connect(self._set_discogs_thumb)
                self._loaders.append(loader)
                loader.start()

    def _set_thumb(self, index, pixmap):
        self._set_section_thumb(self.itunes_section, ArtworkResult,
                                index, pixmap)

    def _set_discogs_thumb(self, index, pixmap):
        self._set_section_thumb(self.discogs_section, DiscogsImageRow,
                                index, pixmap)

    @staticmethod
    def _set_section_thumb(section, row_cls, index, pixmap):
        for i in range(section.count()):
            widget = section.itemAt(i).widget()
            if isinstance(widget, row_cls) and widget.index == index:
                widget.set_thumbnail(pixmap)
                break

    def _on_selection_changed(self, checked, url, title):
        if checked:
            self._selected[url] = title
        else:
            self._selected.pop(url, None)
        self.selected_label.setText(
            f'{len(self._selected)} selected')
        self.save_selected_btn.setEnabled(bool(self._selected))

    def _save_selected(self):
        """Download every checked image, one at a time, then close."""
        if not self._selected:
            return
        self._save_queue = list(self._selected.items())  # [(url, title), ...]
        self._save_total = len(self._save_queue)
        self._save_done = 0
        self.save_selected_btn.setEnabled(False)
        self.search_input.setEnabled(False)
        self._dl_progress = QProgressBar()
        self._dl_progress.setRange(0, 100)
        self._dl_progress.setFixedHeight(14)
        self._dl_progress.setTextVisible(False)
        self.layout().addWidget(self._dl_progress)
        self._save_next()

    def _save_next(self):
        if not self._save_queue:
            self._dl_progress.deleteLater()
            self.status.setText(f'Saved {self._save_done} image(s).')
            self.accept()
            return
        url, title = self._save_queue.pop(0)
        self.status.setText(
            f'Saving {self._save_done + 1} of {self._save_total}: {title}')
        self._dl_progress.setValue(0)
        self._dl_thread = DownloadThread(url, self.album_path, extra=True)
        self._dl_thread.progress.connect(self._dl_progress.setValue)
        self._dl_thread.finished.connect(self._on_batch_item_downloaded)
        self._dl_thread.start()

    def _on_batch_item_downloaded(self, path):
        if path:
            self._save_done += 1
            self.artwork_saved.emit(path)
        self._save_next()

    def _download_artwork(self, url, album_name):
        self.status.setText('Downloading...')
        self._dl_progress = QProgressBar()
        self._dl_progress.setRange(0, 100)
        self._dl_progress.setFixedHeight(14)
        self._dl_progress.setTextVisible(False)
        self.layout().addWidget(self._dl_progress)
        self._dl_thread = DownloadThread(url, self.album_path, extra=self.extra)
        self._dl_thread.progress.connect(self._dl_progress.setValue)
        self._dl_thread.finished.connect(self._on_downloaded)
        self._dl_thread.start()

    def _on_downloaded(self, path):
        if hasattr(self, '_dl_progress') and self._dl_progress:
            self._dl_progress.deleteLater()
            self._dl_progress = None
        if path:
            self.status.setText(f'Saved to {path}')
            self.artwork_saved.emit(path)
            self.accept()
        else:
            self.status.setText('Download failed.')


class SearchThread(QThread):
    """Search iTunes: direct album search + artist lookup for better results."""
    finished = pyqtSignal(list)

    def __init__(self, url, query=''):
        super().__init__()
        self.url = url
        self.query = query

    def _fetch_json(self, url):
        req = urllib.request.Request(url, headers={'User-Agent': 'lp-music-player/1.0'})
        data = urllib.request.urlopen(req, timeout=10, context=_ssl_ctx).read()
        return json.loads(data).get('results', [])

    def run(self):
        try:
            # 1) Direct album search
            direct = self._fetch_json(self.url)

            # 2) Artist lookup — find artist, then get their albums
            artist_results = []
            if self.query:
                words = self.query.lower().split()
                params = urllib.parse.urlencode({
                    'term': self.query, 'entity': 'musicArtist', 'limit': 1
                })
                artists = self._fetch_json(f'{ITUNES_SEARCH_URL}?{params}')
                if artists:
                    artist_id = artists[0].get('artistId')
                    if artist_id:
                        lookup_url = f'https://itunes.apple.com/lookup?id={artist_id}&entity=album&limit=50'
                        albums = self._fetch_json(lookup_url)
                        artist_name = artists[0].get('artistName', '').lower()
                        for a in albums:
                            if a.get('wrapperType') != 'collection':
                                continue
                            # Only include albums by this artist (skip feat. compilations)
                            if a.get('artistName', '').lower() != artist_name:
                                continue
                            name = a.get('collectionName', '').lower()
                            # Keep albums where any query word matches the album name
                            if any(w in name for w in words):
                                artist_results.append(a)

            # Merge: artist lookup matches first (more precise), then direct
            seen_ids = set()
            merged = []
            for r in artist_results + direct:
                cid = r.get('collectionId')
                if cid and cid not in seen_ids:
                    seen_ids.add(cid)
                    merged.append(r)

            self.finished.emit(merged[:12])
        except Exception as e:
            print(f'Artwork search error: {e}')
            self.finished.emit([])


class DownloadThread(QThread):
    finished = pyqtSignal(str)
    progress = pyqtSignal(int)  # percentage 0-100

    def __init__(self, url, album_path, extra=False):
        super().__init__()
        self.url = url
        self.album_path = album_path
        self.extra = extra  # save as additional art, leave cover.jpg alone

    def run(self):
        try:
            if self.extra:
                n = 1
                while (Path(self.album_path) / f'art_{n}.jpg').exists():
                    n += 1
                dest = Path(self.album_path) / f'art_{n}.jpg'
            else:
                # Overwrite any existing cover in place
                dest = Path(self.album_path) / 'cover.jpg'
            req = urllib.request.Request(self.url, headers={
                'User-Agent': 'lp-music-player/1.0'
            })
            resp = urllib.request.urlopen(req, timeout=30, context=_ssl_ctx)
            total = int(resp.headers.get('Content-Length', 0))
            downloaded = 0
            with open(dest, 'wb') as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        self.progress.emit(int(downloaded / total * 100))
            self.finished.emit(str(dest))
        except Exception as e:
            print(f'Artwork download error: {e}')
            self.finished.emit('')
