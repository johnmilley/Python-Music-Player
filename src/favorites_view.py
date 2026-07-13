# FavoritesView — the left-pane view for favourites mode: the All
# Favourites collection plus the user's playlists, with a shuffle toggle.
#
# Selecting a collection loads it into the tracklist (App builds a Playlist
# object from the store's records). Favouriting itself happens in the
# tracklist's context menu (any mode); this view is for browsing/playing
# collections and managing playlists (create/rename/delete via context
# menu on a playlist entry).

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidgetItem, QMenu, QLabel, QInputDialog, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPainter

from vim_views import VimListWidget


class FavoritesView(QWidget):
    collection_selected = pyqtSignal(str)  # '' = all favourites
    shuffle_toggled = pyqtSignal(bool)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.heart_color = None  # accent color, set by App.apply_theme
        self.heart_sel_color = None  # accent_fg — rim color on selected rows

        layout = QVBoxLayout()

        btn_row = QHBoxLayout()
        self.new_btn = QPushButton('New Playlist')
        self.new_btn.clicked.connect(self._new_playlist)
        btn_row.addWidget(self.new_btn)
        self.shuffle_btn = QPushButton('Shuffle')
        self.shuffle_btn.setCheckable(True)
        self.shuffle_btn.setToolTip('Shuffle playback order (s)')
        self.shuffle_btn.toggled.connect(self.shuffle_toggled.emit)
        btn_row.addWidget(self.shuffle_btn)
        layout.addLayout(btn_row)

        self.coll_list = VimListWidget()
        self.coll_list.itemClicked.connect(self._on_item_clicked)
        self.coll_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.coll_list.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.coll_list)

        self.status_label = QLabel('')
        self.status_label.setObjectName('favorites-status')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.setLayout(layout)
        self.refresh()

    # ── Collection list ─────────────────────────────────────────────

    def current_key(self):
        item = self.coll_list.currentItem()
        return item.data(Qt.UserRole) if item else ''

    def set_heart_color(self, color, selected_color=None):
        """Accent changed — re-tint the All Favourites heart icon.
        selected_color (accent_fg) rims the heart on the selected row so it
        stays visible on the accent highlight."""
        if color == self.heart_color and selected_color == self.heart_sel_color:
            return
        self.heart_color = color
        self.heart_sel_color = selected_color
        self.refresh()

    def _heart_icon(self):
        """Accent-colored heart, with an accent_fg-rimmed QIcon.Selected
        variant (the accent fill vanishes into the accent selection
        highlight otherwise). Deferred import: player transitively imports
        this module's siblings, so avoid a top-level cycle."""
        from player import _render_svg
        color = self.heart_color or 'gray'
        icon = QIcon(_render_svg('heart', color, 14))
        if self.heart_sel_color:
            rimmed = _render_svg('heart', color, 14).copy()
            painter = QPainter(rimmed)
            painter.drawPixmap(0, 0,
                               _render_svg('heart_outline',
                                           self.heart_sel_color, 14))
            painter.end()
            icon.addPixmap(rimmed, QIcon.Selected)
        return icon

    def refresh(self):
        selected = self.current_key()
        self.coll_list.clear()
        item = QListWidgetItem(
            self._heart_icon(), f'All Favourites ({len(self.store.favorites)})')
        item.setData(Qt.UserRole, '')
        self.coll_list.addItem(item)
        for name in self.store.playlist_names():
            it = QListWidgetItem(f'{name} ({len(self.store.playlists[name])})')
            it.setData(Qt.UserRole, name)
            self.coll_list.addItem(it)
        # Keep the previous selection if it still exists
        row = 0
        for i in range(self.coll_list.count()):
            if self.coll_list.item(i).data(Qt.UserRole) == selected:
                row = i
                break
        self.coll_list.setCurrentRow(row)
        if not self.store.favorites:
            self.status_label.setText(
                'Right-click a track and choose "Add to Favourites".')
        else:
            self.status_label.setText('')

    def _on_item_clicked(self, item):
        self.collection_selected.emit(item.data(Qt.UserRole))

    # ── Playlist management ─────────────────────────────────────────

    def _new_playlist(self):
        name, ok = QInputDialog.getText(self, 'New Playlist', 'Playlist name:')
        if ok and name.strip():
            if self.store.create_playlist(name):
                self.refresh()
            else:
                QMessageBox.information(
                    self, 'New Playlist',
                    f'A playlist called "{name.strip()}" already exists.')

    def _context_menu(self, pos):
        item = self.coll_list.itemAt(pos)
        if not item:
            return
        name = item.data(Qt.UserRole)
        if not name:
            return  # All Favourites can't be renamed/deleted
        menu = QMenu(self.coll_list)
        rename_action = menu.addAction('Rename...')
        delete_action = menu.addAction('Delete')
        action = menu.exec_(self.coll_list.viewport().mapToGlobal(pos))
        if action == rename_action:
            new, ok = QInputDialog.getText(
                self, 'Rename Playlist', 'Playlist name:', text=name)
            if ok and self.store.rename_playlist(name, new):
                self.refresh()
        elif action == delete_action:
            confirm = QMessageBox.question(
                self, 'Delete Playlist',
                f'Delete the playlist "{name}"?\n'
                f'(The songs stay in your favourites.)')
            if confirm == QMessageBox.Yes:
                self.store.delete_playlist(name)
                self.refresh()
