# App contains Player, Album View, and FolderView widgets

import sys

# local
from folder_view import FolderView
from player import Player
from album_view import AlbumView
import theme

from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout,
    QAction, QActionGroup, QSplitter)
from PyQt5.QtCore import Qt, QSettings


class App(QMainWindow):
    def __init__(self):
        super().__init__()

        self.app_widget = QWidget()
        self.app_widget.setObjectName('main-window')

        self.player = Player()
        self.album_view = AlbumView()
        self.folder_view = FolderView(self.album_view)

        # Player and AlbumView coupling
        self.player.album_view = self.album_view
        self.player.folder_view = self.folder_view
        self.album_view.player = self.player

        self.setWindowTitle("lp")
        self.setMinimumSize(800, 600)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName('main-splitter')
        self.splitter.addWidget(self.folder_view)
        self.splitter.addWidget(self.player)
        self.splitter.addWidget(self.album_view)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 2)

        self.layout_app = QHBoxLayout()
        self.layout_app.setContentsMargins(0, 0, 0, 0)
        self.layout_app.addWidget(self.splitter)
        self.app_widget.setLayout(self.layout_app)

        self.setCentralWidget(self.app_widget)

        # Menu bar — Preferences
        self.prefs_menu = self.menuBar().addMenu('Preferences')

        self.dark_mode_action = QAction('Dark Mode', self)
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.triggered.connect(self.toggle_theme)
        self.prefs_menu.addAction(self.dark_mode_action)

        # Font size submenu
        self.font_size_menu = self.prefs_menu.addMenu('Font Size')
        self.font_size_group = QActionGroup(self)
        self.font_size = theme.DEFAULT_FONT_SIZE
        for size in theme.FONT_SIZES:
            action = QAction(f'{size}pt', self)
            action.setCheckable(True)
            action.setData(size)
            if size == theme.DEFAULT_FONT_SIZE:
                action.setChecked(True)
            action.triggered.connect(lambda checked, s=size: self.set_font_size(s))
            self.font_size_group.addAction(action)
            self.font_size_menu.addAction(action)

        # Theme setup
        self.current_theme = theme.LIGHT
        self.apply_theme(self.current_theme)

        self.album_view.album_changed.connect(self.setWindowTitle)

        # Restore saved state
        self.settings = QSettings('lp', 'music-player')
        self._restore_state()

    def apply_theme(self, t):
        self.current_theme = t
        fs = self.font_size
        self.setStyleSheet(theme.app_qss(t))
        self.player.setStyleSheet(theme.player_qss(t, fs))
        self.folder_view.setStyleSheet(theme.folder_view_qss(t, fs))
        self.album_view.setStyleSheet(theme.album_view_qss(t, fs))

    def toggle_theme(self, checked):
        if checked:
            self.apply_theme(theme.DARK)
        else:
            self.apply_theme(theme.LIGHT)

    def set_font_size(self, size):
        self.font_size = size
        self.apply_theme(self.current_theme)

    def _restore_state(self):
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
        splitter_state = self.settings.value('splitter')
        if splitter_state:
            self.splitter.restoreState(splitter_state)
        saved_fs = self.settings.value('font_size', type=int)
        if saved_fs and saved_fs in theme.FONT_SIZES:
            self.font_size = saved_fs
            for action in self.font_size_group.actions():
                if action.data() == saved_fs:
                    action.setChecked(True)
        if self.settings.value('dark_mode') == 'true':
            self.dark_mode_action.setChecked(True)
            self.apply_theme(theme.DARK)
        else:
            self.apply_theme(self.current_theme)
        last_album = self.settings.value('last_album')
        if last_album:
            self.album_view.load_album_listing(last_album)

    def closeEvent(self, event):
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('splitter', self.splitter.saveState())
        self.settings.setValue('dark_mode', 'true' if self.current_theme is theme.DARK else 'false')
        self.settings.setValue('font_size', self.font_size)
        if self.album_view.album and self.album_view.album.path:
            self.settings.setValue('last_album', self.album_view.album.path)
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app_ui = App()
    app_ui.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
