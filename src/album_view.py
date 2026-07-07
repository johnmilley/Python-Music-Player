# AlbumView widget displays the tracks of an album.

import sys
import urllib.parse
import webbrowser
from pathlib import Path

# pyqt5
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QListWidgetItem, QMenu
)
from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QThread
from PyQt5.QtGui import QDesktopServices

# local
from album import Album
from vim_views import VimListWidget, SearchBar


class AlbumLoadThread(QThread):
    """Load album metadata in a background thread."""
    finished = pyqtSignal(object)  # Album

    def __init__(self, directory_path):
        super().__init__()
        self.directory_path = directory_path

    def run(self):
        album = Album(Path(self.directory_path))
        self.finished.emit(album)


class AlbumView(QWidget):
    album_changed = pyqtSignal(str)

    def __init__(self, player=None):
        super().__init__()
        self.setWindowTitle("Tracklist")
        self.setMinimumWidth(150)
        self.current_track = None
        self.album = None
        self.init_gui()
        self.player = player

    def init_gui(self):
        """
            builds the GUI and connects events
        """
        layout_main = QVBoxLayout()

        self.track_list_widget = VimListWidget()
        self.track_list_widget.addItem("No album loaded")
        self.track_list_widget.setObjectName('track-list')
        # Wrap long titles onto extra lines so as much text fits as reasonable;
        # a single unbreakable run still elides. Full text is in the tooltip.
        self.track_list_widget.setWordWrap(True)
        self.track_list_widget.setTextElideMode(Qt.ElideRight)
        self.track_list_widget.itemClicked.connect(self.set_current_track)
        self.track_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.track_list_widget.customContextMenuRequested.connect(self._open_context_menu)

        # Search bar
        self.search_bar = SearchBar(self.track_list_widget)
        self.track_list_widget.set_search_bar(self.search_bar)
        self.search_bar.textChanged.connect(self._on_search)

        layout_main.addWidget(self.search_bar)
        layout_main.addWidget(self.track_list_widget)

        self.setLayout(layout_main)

    def _on_search(self, text):
        """Jump to first track where any word starts with the search text."""
        if not text:
            return
        query = text.lower()
        for row in range(self.track_list_widget.count()):
            item = self.track_list_widget.item(row)
            label = item.text().lower()
            words = label.replace('-', ' ').replace('_', ' ').split()
            if any(w.startswith(query) for w in words) or label.startswith(query):
                self.track_list_widget.setCurrentRow(row)
                self.track_list_widget.scrollToItem(item)
                break

    def load_album_listing(self, directory_path):
        """Load album metadata in background, then populate the track list."""
        self.track_list_widget.clear()
        self.track_list_widget.addItem("Loading...")
        self._load_thread = AlbumLoadThread(directory_path)
        self._load_thread.finished.connect(self._on_album_loaded)
        self._load_thread.start()

    def _on_album_loaded(self, album):
        """Populate track list after background loading completes."""
        self.track_list_widget.clear()
        self.album = album

        if self.album.tracklist:
            for i, track in enumerate(self.album.tracklist):
                item = QListWidgetItem(str(track))
                item.setData(Qt.UserRole, i)
                item.setToolTip(str(track))
                self.track_list_widget.addItem(item)
            if self.player:
                self.player.album = self.album
                self.player.load_album_art(self.player.album)
            if self.album.title and self.album.artist:
                self.album_changed.emit(f"{self.album.title} - {self.album.artist}")
        else:
            self.track_list_widget.addItem("No music files found.")

    def _open_context_menu(self, pos):
        item = self.track_list_widget.itemAt(pos)
        if item is None or not self.album or not self.album.tracklist:
            return
        track_pos = item.data(Qt.UserRole)
        if track_pos is None:
            return
        track = self.album.tracklist[track_pos]
        menu = QMenu(self.track_list_widget)
        chords_action = menu.addAction("Look Up Chords / Tab")
        # pos is in viewport coordinates for item views
        action = menu.exec_(self.track_list_widget.viewport().mapToGlobal(pos))
        if action == chords_action:
            self._lookup_chords(track)

    def _lookup_chords(self, track):
        """Open a new browser window with a chords/tab search for this track."""
        query = ' '.join(part for part in (track.artist, track.title, 'chords') if part)
        url = 'https://www.google.com/search?q=' + urllib.parse.quote(query)
        # webbrowser.open_new() asks for a fresh window (not a reused tab);
        # fall back to the desktop's URL handler if no browser controller
        # is registered for it.
        try:
            opened = webbrowser.open_new(url)
        except webbrowser.Error:
            opened = False
        if not opened:
            QDesktopServices.openUrl(QUrl(url))

    def set_current_track(self, selected):
        track_pos = selected.data(Qt.UserRole)
        if track_pos is None or not self.album or not self.album.tracklist:
            return
        self.current_track = self.album.tracklist[track_pos]

        # Send Album to Player
        if self.player:
            self.player.play(self.album, track_pos)

    def get_current_track(self):
        if self.current_track:
            return self.current_track

def main():
    app = QApplication(sys.argv)
    album_view = AlbumView()

    album_view.base_directory = '/Users/jlm/Downloads/music/Carly Rae Jepsen - Emotion (10th Anniversary Edition) - (2025)'
    album_view.load_album_listing(album_view.base_directory)

    album_view.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
