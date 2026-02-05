# App contains Player, Album View, and FolderView widgets

import sys

# local
from folder_view import FolderView
from player import Player
from album_view import AlbumView

# pyqt
from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout,
QStyle)

class App(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.app_widget = QWidget()
        self.app_widget.setObjectName('main-window')
        self.app_widget.setStyleSheet("""
            #main-window {
                background-color: white;
            }
        """
        )
        
        self.player = Player()
        self.album_view = AlbumView()
        self.folder_view = FolderView(self.album_view)
        
        # Player and AlbumView coupling     
        self.player.album_view = self.album_view
        self.player.folder_view = self.folder_view
        self.album_view.player = self.player

        self.setWindowTitle("lp")
        self.layout_app = QHBoxLayout()

        self.layout_app.addWidget(self.folder_view)
        self.layout_app.addWidget(self.player)
        self.layout_app.addWidget(self.album_view)
        self.app_widget.setLayout(self.layout_app)

        self.setCentralWidget(self.app_widget)

        try:
            with open("/stylesheets/folder_view.qss", 'r') as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            print("stylesheet not found")

        self.album_view.album_changed.connect(self.setWindowTitle)

def main():
    app = QApplication(sys.argv)
    app_ui = App()
    app_ui.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()