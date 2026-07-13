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
from PyQt5.QtGui import QDesktopServices, QIcon, QPainter

# local
import bg_threads
from album import Album
from vim_views import VimListWidget, SearchBar


class AlbumLoadThread(QThread):
    """Load album metadata in a background thread."""
    # Named album_ready (not 'finished') so QThread's own finished signal
    # stays usable for lifecycle handling — see bg_threads.retire()
    album_ready = pyqtSignal(object)  # Album

    def __init__(self, directory_path):
        super().__init__()
        self.directory_path = directory_path

    def run(self):
        album = Album(Path(self.directory_path))
        self.album_ready.emit(album)


class AlbumView(QWidget):
    album_changed = pyqtSignal(str)
    favorites_changed = pyqtSignal()  # a favourite/playlist mutation happened

    def __init__(self, player=None):
        super().__init__()
        self.setWindowTitle("Tracklist")
        self.setMinimumWidth(150)
        self.current_track = None
        self.album = None
        self.fav_store = None  # FavoritesStore, attached at the App level
        self.heart_color = None  # accent color, set by App.apply_theme
        self.heart_sel_color = None  # accent_fg — rim color on selected rows
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
        """Load album metadata in background, then populate the track list.

        Rapid album switching starts a new load while the previous one is
        still reading its (possibly slow NAS) folder. The superseded thread
        is disconnected — its result must not clobber the newer album — and
        retired, never waited on and never dropped while running."""
        self.track_list_widget.clear()
        self.track_list_widget.addItem("Loading...")
        old = getattr(self, '_load_thread', None)
        if old is not None:
            try:
                old.album_ready.disconnect(self._on_album_loaded)
            except TypeError:
                pass
            bg_threads.retire(old)
        self._load_thread = AlbumLoadThread(directory_path)
        self._load_thread.album_ready.connect(self._on_album_loaded)
        self._load_thread.start()

    def _music_item_text(self, track):
        """Track label for album listings (favourite state is shown by an
        accent heart icon, not a text glyph — see _apply_heart)."""
        return str(track)

    def _heart_icon(self, filled=True, size=14):
        """Accent-colored heart icon. Deferred import: player imports this
        module, so a top-level import would be circular.

        Filled hearts get a QIcon.Selected variant with an accent_fg rim:
        on the accent selection highlight the accent fill vanishes into the
        background, so the rim is what keeps the heart visible there (and on
        the softer unfocused-selection grey the accent fill still shows)."""
        from player import _render_svg
        color = self.heart_color or 'gray'
        icon = QIcon(_render_svg('heart' if filled else 'heart_outline',
                                 color, size))
        if filled and self.heart_sel_color:
            rimmed = _render_svg('heart', color, size).copy()
            painter = QPainter(rimmed)
            painter.drawPixmap(0, 0,
                               _render_svg('heart_outline',
                                           self.heart_sel_color, size))
            painter.end()
            icon.addPixmap(rimmed, QIcon.Selected)
        return icon

    def _apply_heart(self, item, track):
        """Set or clear the accent heart icon on a tracklist row."""
        if (self.fav_store and track.path
                and self.fav_store.is_favorite(track.path)):
            item.setIcon(self._heart_icon())
        else:
            item.setIcon(QIcon())

    def set_heart_color(self, color, selected_color=None):
        """Accent changed — re-tint the heart icons on favourited rows.
        selected_color (accent_fg) rims the heart on selected rows so it
        stays visible on the accent highlight."""
        if color == self.heart_color and selected_color == self.heart_sel_color:
            return
        self.heart_color = color
        self.heart_sel_color = selected_color
        self.refresh_hearts()

    def refresh_hearts(self):
        """Re-apply heart icons across the current album listing (skipped
        for playlist views, which don't show hearts — every playlist track
        is a favourite by construction)."""
        if (not self.album or getattr(self.album, 'is_playlist', False)
                or not self.album.tracklist):
            return
        for i in range(self.track_list_widget.count()):
            item = self.track_list_widget.item(i)
            pos = item.data(Qt.UserRole)
            if pos is not None and pos < len(self.album.tracklist):
                self._apply_heart(item, self.album.tracklist[pos])

    def _on_album_loaded(self, album):
        """Populate track list after background loading completes."""
        self.track_list_widget.clear()
        self.album = album

        if self.album.tracklist:
            for i, track in enumerate(self.album.tracklist):
                label = self._music_item_text(track)
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, i)
                item.setToolTip(label)
                self._apply_heart(item, track)
                self.track_list_widget.addItem(item)
            # Start with the first track highlighted so keyboard focus has
            # a visible "you are here" (playing-track highlight, if this
            # album is the one playing, is set by Player right after)
            self.track_list_widget.setCurrentRow(0)
            if self.player:
                self.player.album = self.album
                self.player.load_album_art(self.player.album)
            if self.album.title and self.album.artist:
                self.album_changed.emit(f"{self.album.title} - {self.album.artist}")
        else:
            self.track_list_widget.addItem("No music files found.")

    def load_playlist(self, playlist):
        """Show a favourites/playlist collection (a Playlist object) —
        same list, but labels carry the artist since tracks span albums."""
        self.track_list_widget.clear()
        self.album = playlist
        if not playlist.tracklist:
            self.track_list_widget.addItem('No songs here yet.')
            return
        for i, track in enumerate(playlist.tracklist):
            label = self._playlist_item_text(track)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, i)
            item.setToolTip(label)
            self.track_list_widget.addItem(item)
        self.track_list_widget.setCurrentRow(0)

    @staticmethod
    def _playlist_item_text(track):
        dur = track.length_to_string(track.length)
        if track.artist:
            return f'{track.title or track.filename} — {track.artist} ({dur})'
        return f'{track.title or track.filename} ({dur})'

    def _open_context_menu(self, pos):
        item = self.track_list_widget.itemAt(pos)
        if item is None or not self.album or not self.album.tracklist:
            return
        track_pos = item.data(Qt.UserRole)
        if track_pos is None:
            return
        track = self.album.tracklist[track_pos]
        menu = QMenu(self.track_list_widget)

        # Favourites section (music tracks only — the store is attached by
        # App and the menu is swapped out entirely in podcast mode)
        store = self.fav_store
        fav_action = unfav_action = remove_here_action = new_pl_action = None
        playlist_adds = {}
        if store is not None and track.path:
            if store.is_favorite(track.path):
                unfav_action = menu.addAction(
                    self._heart_icon(filled=True), 'Remove from Favourites')
            else:
                fav_action = menu.addAction(
                    self._heart_icon(filled=False), 'Add to Favourites')
            # A track doesn't need to already be a favourite to join a
            # playlist — adding it favourites it automatically (see
            # FavoritesStore.add_to_playlist).
            add_menu = menu.addMenu('Add to Playlist')
            for name in store.playlist_names():
                act = add_menu.addAction(name)
                if store.in_playlist(name, track.path):
                    act.setEnabled(False)  # already in it
                else:
                    playlist_adds[act] = name
            new_pl_action = add_menu.addAction('New Playlist...')
            # Viewing a named playlist — allow removing from just it
            pl_name = getattr(self.album, 'playlist_name', '')
            if pl_name:
                remove_here_action = menu.addAction(
                    f'Remove from "{pl_name}"')
            menu.addSeparator()

        chords_action = menu.addAction("Look Up Chords / Tab")
        # pos is in viewport coordinates for item views
        action = menu.exec_(self.track_list_widget.viewport().mapToGlobal(pos))
        if action is None:
            return
        if action == chords_action:
            self._lookup_chords(track)
            return
        if store is None:
            return
        if action == fav_action:
            store.add(track)
        elif action == unfav_action:
            store.remove(track.path)
        elif action == remove_here_action:
            store.remove_from_playlist(self.album.playlist_name, track.path)
        elif action == new_pl_action:
            from PyQt5.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(
                self, 'New Playlist', 'Playlist name:')
            if not (ok and name.strip()):
                return
            name = name.strip()
            store.create_playlist(name)
            store.add_to_playlist(name, track)
        elif action in playlist_adds:
            store.add_to_playlist(playlist_adds[action], track)
        else:
            return
        # Reflect the change: accent heart icon on album listings; playlist
        # views are reloaded by App via favorites_changed
        if not getattr(self.album, 'is_playlist', False):
            self._apply_heart(item, track)
        self.favorites_changed.emit()

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
