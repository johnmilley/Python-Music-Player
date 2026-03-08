# AlbumView widget displays the tracks of an album.

import sys
from pathlib import Path

# pyqt5
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QShortcut
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence

# local
from album import Album


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

        self.track_list_widget = QListWidget()
        self.track_list_widget.addItem("No album loaded")
        self.track_list_widget.setWordWrap(True)
        self.track_list_widget.setObjectName('track-list')
        self.track_list_widget.itemDoubleClicked.connect(self.set_current_track)

        layout_main.addWidget(self.track_list_widget)

        # Vim navigation: j = down, k = up
        QShortcut(QKeySequence('j'), self.track_list_widget,
                  lambda: self._move_selection(1))
        QShortcut(QKeySequence('k'), self.track_list_widget,
                  lambda: self._move_selection(-1))

        self.setLayout(layout_main)

    def _move_selection(self, direction):
        """Move the track list selection up or down by direction (+1 or -1)."""
        current = self.track_list_widget.currentRow()
        new_row = current + direction
        if 0 <= new_row < self.track_list_widget.count():
            self.track_list_widget.setCurrentRow(new_row)

    def load_album_listing(self, directory_path):
        """
            builds an Album object from any dir that contains music files (mp3, flac)
        """
        self.track_list_widget.clear()

        self.album = Album(Path(directory_path))
        
        if self.album.tracklist:
            for i, track in enumerate(self.album.tracklist):
                item = QListWidgetItem(str(track))
                item.setData(Qt.UserRole, i)
                self.track_list_widget.addItem(item)
            # self.track_list_widget.setFixedHeight(self.track_list_widget.sizeHint().height())
            if self.album.title and self.album.artist:
                # updates App with new ALBUM TITLE - ARTIST
                self.album_changed.emit(f"{self.album.title} - {self.album.artist}")
            # LOAD DATA into PLAYER
            if self.player:
                # BUG: overwrites track length if track is playing
                self.player.album = self.album
                self.player.load_album_art(self.player.album)
                self.player.track_pos = 0
        else:
            self.track_list_widget.addItem("No music files found.")
            self.setWindowTitle(f"Tracklist")

    def set_current_track(self, selected):
        track_pos = selected.data(Qt.UserRole)
        self.current_track = self.album.tracklist[track_pos]
        print(f"Current track: {self.current_track}")

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