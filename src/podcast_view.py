# PodcastView — left panel for podcast mode
# Shows subscribed feeds; selecting one loads episodes into AlbumView

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QLabel, QMenu, QApplication
)
from PyQt5.QtCore import Qt, QSettings, pyqtSignal

from podcast_feed import PodcastFeed, FeedFetchThread


class PodcastView(QWidget):
    """Left panel showing subscribed podcast feeds."""

    feed_selected = pyqtSignal(object)  # emits PodcastFeed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(150)
        self._feeds = {}          # url -> PodcastFeed
        self._fetch_thread = None
        self._auto_select_url = None

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)

        # Add feed input
        input_row = QHBoxLayout()
        input_row.setSpacing(4)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText('Paste Apple Podcasts link...')
        self.url_input.setFocusPolicy(Qt.ClickFocus)
        self.url_input.returnPressed.connect(self._add_feed)
        self.add_btn = QPushButton('+')
        self.add_btn.setFixedWidth(30)
        self.add_btn.pressed.connect(self._add_feed)
        input_row.addWidget(self.url_input)
        input_row.addWidget(self.add_btn)
        layout.addLayout(input_row)

        # Feed list
        self.feed_list = QListWidget()
        self.feed_list.setObjectName('podcast-feed-list')
        self.feed_list.itemClicked.connect(self._on_feed_clicked)
        self.feed_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.feed_list.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.feed_list)

        # Status
        self.status_label = QLabel('')
        self.status_label.setObjectName('podcast-status')
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def load_saved_feeds(self):
        """Load subscribed feed URLs from QSettings and fetch them (once)."""
        if self._feeds:
            return
        settings = QSettings('lp', 'music-player')
        urls = settings.value('podcast/feeds', [])
        if isinstance(urls, str):
            urls = [urls] if urls else []
        for url in urls:
            self._fetch_feed(url)

    def _save_feeds(self):
        """Persist feed URLs to QSettings."""
        settings = QSettings('lp', 'music-player')
        settings.setValue('podcast/feeds', list(self._feeds.keys()))

    def _add_feed(self):
        url = self.url_input.text().strip()
        if not url:
            return
        if url in self._feeds:
            self.status_label.setText('Already subscribed')
            return
        self.url_input.clear()
        self._fetch_feed(url)

    def _fetch_feed(self, url):
        self.status_label.setText('Loading...')
        thread = FeedFetchThread(url, parent=self)
        thread.finished.connect(self._on_feed_loaded)
        thread.error.connect(self._on_feed_error)
        thread.start()
        # Keep reference so it doesn't get GC'd
        self._fetch_thread = thread

    def _on_feed_loaded(self, feed):
        self.status_label.setText('')
        if feed and feed.title:
            self._feeds[feed.url] = feed
            item = QListWidgetItem(feed.title)
            item.setData(Qt.UserRole, feed.url)
            self.feed_list.addItem(item)
            self._save_feeds()
            if self._auto_select_url and feed.url == self._auto_select_url:
                self._auto_select_url = None
                self.feed_list.setCurrentItem(item)
                self.feed_selected.emit(feed)

    def _on_feed_error(self, msg):
        self.status_label.setText(f'Error: {msg[:50]}')

    def _on_feed_clicked(self, item):
        url = item.data(Qt.UserRole)
        feed = self._feeds.get(url)
        if feed:
            self.feed_selected.emit(feed)

    def _context_menu(self, pos):
        item = self.feed_list.itemAt(pos)
        if not item:
            return
        menu = QMenu()
        remove = menu.addAction('Remove')
        refresh = menu.addAction('Refresh')
        action = menu.exec_(self.feed_list.mapToGlobal(pos))
        if action == remove:
            url = item.data(Qt.UserRole)
            self._feeds.pop(url, None)
            self.feed_list.takeItem(self.feed_list.row(item))
            self._save_feeds()
        elif action == refresh:
            url = item.data(Qt.UserRole)
            self._feeds.pop(url, None)
            self.feed_list.takeItem(self.feed_list.row(item))
            self._fetch_feed(url)

    def get_feed(self, url):
        return self._feeds.get(url)
