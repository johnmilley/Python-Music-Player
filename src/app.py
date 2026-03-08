# App contains Player, Album View, and FolderView widgets

import sys

# local
from folder_view import FolderView
from player import Player
from album_view import AlbumView
import theme

from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout, QAction)


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
        self.layout_app = QHBoxLayout()

        self.layout_app.addWidget(self.folder_view, stretch=2)
        self.layout_app.addWidget(self.player, stretch=3)
        self.layout_app.addWidget(self.album_view, stretch=2)
        self.app_widget.setLayout(self.layout_app)

        self.setCentralWidget(self.app_widget)

        # Menu bar — Preferences
        self.prefs_menu = self.menuBar().addMenu('Preferences')

        self.dark_mode_action = QAction('Dark Mode', self)
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.triggered.connect(self.toggle_theme)
        self.prefs_menu.addAction(self.dark_mode_action)

        # Theme setup
        self.current_theme = theme.LIGHT
        self.apply_theme(self.current_theme)

        self.album_view.album_changed.connect(self.setWindowTitle)

    def apply_theme(self, t):
        self.current_theme = t
        self.setStyleSheet(theme.app_qss(t))
        self.player.setStyleSheet(theme.player_qss(t))
        self.folder_view.setStyleSheet(theme.folder_view_qss(t))
        self.album_view.setStyleSheet(theme.album_view_qss(t))

    def toggle_theme(self, checked):
        if checked:
            self.apply_theme(theme.DARK)
        else:
            self.apply_theme(theme.LIGHT)

def main():
    app = QApplication(sys.argv)
    app_ui = App()
    app_ui.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
