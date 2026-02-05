# Player displays playback controls, album art, and currently playing track

from pathlib import Path
import math
import sys
sys.path.append('./tracklist') # clean this up

from track import Track
from album import Album
from album_view import AlbumView
from progress_bar import ClickableProgressBar

from just_playback import Playback

# pyqt5
from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout, QPushButton, QLabel, QVBoxLayout)
from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt5.QtGui import QPixmap


class Player(QWidget):
    APP_UPDATE_TIME = 20 # ms

    track_finished = pyqtSignal()

    def __init__(self, album=None, folder_view=None, album_view=None):
        super().__init__()

        # Player plays Album, Tracks (queue) displayed in AlbumView
        self.album = album
        self.album_view = album_view # attached at the App level
        self.folder_view = folder_view

        self.build_gui()

        # just_playback: see notes/just_played_usage.png
        self.playback = Playback()
        self._time_elapsed = 0
        
        # Timer is used to track elapsed time and end of track
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_track_pos)
        
        # Tracklist: a list of Track objects
        self.current_track = None
        self.track_pos = 0

    def build_gui(self):
        """
            Builds the Player inferface

            General code steps:
                Create X Layout
                Create Widgets (style and attach events)
                Add Widgets to X Layout
                Add X Layout to PARENT layout (player)

        """
        self.setFixedSize(600, 800)

        self.layout_player = QVBoxLayout()
        self.layout_player.setContentsMargins(0,0,0,0)
        self.player = QWidget()
        self.player.setObjectName('player')

        # ALBUM ART
        self.layout_album_display = QVBoxLayout()
        self.album_widget = QLabel()
        self.album_widget.setFixedSize(580, 580)
        self.album_widget.setObjectName('album-art')
        self.album_widget.setAlignment(Qt.AlignCenter)
        self.album_widget.setScaledContents(True)
        self.layout_player.addWidget(self.album_widget, alignment=Qt.AlignCenter)

        # SONG TITLE - ARTIST   *improve text, center
        self.layout_track_information = QVBoxLayout()
        self.track_info = QLabel('')
        self.track_info.setWordWrap(True)
        self.track_info.setObjectName('track-info')
        
        self.track_info.setAlignment(Qt.AlignCenter)
        self.layout_track_information.addWidget(self.track_info, alignment=Qt.AlignCenter)
        self.layout_player.addLayout(self.layout_track_information)

        # PROGRESS BAR  *build progress bar, center
        self.progress_widget = QWidget()
        self.progress_widget.setObjectName('track-progress-widget')
        
        self.layout_track_progress = QHBoxLayout()
        self.layout_track_progress.setAlignment(Qt.AlignCenter)
        
        # TIME ELAPSED
        self.track_progress_label = QLabel('0:00')
        self.track_progress_label.setObjectName('track-progress')
       

        self.progress_bar = ClickableProgressBar(self)
        self.progress_bar.seek_requested.connect(self.seek_to)
        self.progress_bar.start_playback.connect(self.resume)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(18)

        self.track_length_label = QLabel('0:00')
        self.track_length_label.setObjectName('track-length')

        # Add track information to track layout
        self.layout_track_progress.addWidget(self.track_progress_label)
        self.layout_track_progress.addWidget(self.progress_bar)
        self.layout_track_progress.addWidget(self.track_length_label)

        self.progress_widget.setLayout(self.layout_track_progress)
        self.layout_player.addWidget(self.progress_widget)

        # Toggle Library/Tracklist buttons
        self.toggle_library_btn = QPushButton()
        self.toggle_library_btn.pressed.connect(self.toggle_library)
        self.toggle_library_btn.setObjectName('toggle-library-btn')


        self.toggle_folder_btn = QPushButton()
        self.toggle_folder_btn.pressed.connect(self.toggle_tracklist)
        self.toggle_folder_btn.setObjectName('toggle-folder-btn')

        # TRACK CONTROL BUTTONS (PREV PLAY/PAUSE NEXT)
        self.layout_player_buttons = QHBoxLayout()

        # PREV
        self.prev_track_button = QPushButton('< prev')
        self.prev_track_button.pressed.connect(self.prev_track)
        self.prev_track_button.setIconSize(QSize(50, 50))
        self.prev_track_button.setObjectName('prev-button')

        # PLAY / PAUSE
        self.play_button = QPushButton()
        self.play_button.setText('PLAY')
        self.play_button.pressed.connect(self.toggle_play_pause_button_text)
        self.play_button.setIconSize(QSize(50, 50))
        self.play_button.setObjectName('play-button')

        # NEXT
        self.next_track_button = QPushButton('next >')
        self.next_track_button.pressed.connect(self.next_track)
        self.next_track_button.setIconSize(QSize(50, 50))
        self.next_track_button.setObjectName('next-button')

        # Add buttons to button layout
        self.layout_player_buttons.addWidget(self.toggle_library_btn)
        self.layout_player_buttons.addWidget(self.prev_track_button)
        self.layout_player_buttons.addWidget(self.play_button)
        self.layout_player_buttons.addWidget(self.next_track_button)
        self.layout_player_buttons.addWidget(self.toggle_folder_btn)
        self.layout_player.addLayout(self.layout_player_buttons)

        # load stylesheet
        try:
            with open("stylesheets/player.qss", 'r') as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            print("stylesheet not found")

        self.setLayout(self.layout_player)

    def seek_to(self, pos):
        self.playback.pause()
        if self.current_track:
            # 1000 is the size of the progress bar
            seconds = (pos / 1000) * self.current_track.length
            self.track_progress_label.setText(
                self.current_track.length_to_string(seconds)
                )
            self.playback.seek(seconds)
    
    def check_track_pos(self):
        """
            runs every APP_UPDATE_TIME (milliseconds)
        """

        if not self.current_track or not self.playback.playing:
            return

        pos = self.playback.curr_pos
        total = self.current_track.length

        # Update progress bar
        if total > 0:
            progress = int((pos / total) * 1000)
            self.progress_bar.setValue(progress)
            self.progress_bar.repaint()

        # Update progress label
        if int(pos) != int(self._time_elapsed):
            self._time_elapsed = pos
            self.track_progress_label.setText(
                self.current_track.length_to_string(pos))

        # Check if Track fininshed playing
        if pos >= total - 0.1:
            self.track_progress_label.setText(
                self.current_track.length_to_string(self.current_track.length)
                )
            self.progress_bar.setValue(1000) # store size in var
            self.timer.stop()
            self.play_button.setText("PLAY")
            self.track_finished.emit()
            if self.current_track != self.album.tracklist[-1]:
                self.next_track()

    def next_track(self):
        # print(self.track_pos)
        if self.album:
            if self.track_pos != len(self.album.tracklist) - 1:
                self.track_pos += 1
                self.play(self.album, self.track_pos)
            else:
                self.track_pos = 0
                self.play(self.album, self.track_pos)
    
    def prev_track(self):
        # print(self.track_pos)
        if self.album:
            if self.track_pos != 0:
                self.track_pos -= 1
                self.play(self.album, self.track_pos)
            else: # go to end of tracklist
                self.track_pos = len(self.album.tracklist) - 1
                self.play(self.album, self.track_pos)

    def play(self, album, track_pos):
        self.timer.start(self.APP_UPDATE_TIME) # updates time elapsed

        # update instance variables (from AlbumView)
        self.album = album
        self.track_pos = track_pos
        self.current_track = self.album.tracklist[self.track_pos]

        # update UI
        self.update_gui_after_tracklist_load(self.album)

        # Play track
        try:
            self.playback.load_file(self.current_track.path)
            self.playback.play()
        except:
            # make a logger and add error handling - I need to teach it in Jan
            print(f"LOG: Unable to play.")

        # Updates AlbumViewer with track currently playing
        if self.album_view:
            self.album_view.track_list_widget.setCurrentRow(self.track_pos)
            
    def pause(self):
        self.playback.pause()

    def resume(self):
        self.playback.resume()
        self.play_button.setText("PAUSE")

    def update_gui_after_tracklist_load(self, album):
        """
            Updates GUI with track information when new track begins play

            art, title, artist, current time ellapsed in track mm:ss
        """
        self.album = album

        # Update TRACK TITLE - ARTIST
        if self.current_track.title:
            self.track_info.setText(f"{self.current_track.title} - {self.current_track.artist}")
        else:
            self.track_info.setText(f"{self.album.artist} - {self.album.title}")

        self.play_button.setText('PAUSE')

        # Update DURATION
        if self.current_track:
            track_length = self.current_track.length_to_string(
                self.current_track.length
                )
            self.track_length_label.setText(track_length)

    def load_album_art(self, album):
        """
            MOVE

            on album load, look for cover.jpg
            in the current folder.
        """

        # if file exists albumdir/cover.jpg':
        if self.album.art:
            pixmap = QPixmap(str(self.album.art))
            self.album_widget.setPixmap(pixmap)

        # Going to handle art download later in a proper way. This was fun though!
        # else:
        #     art_url = art_func.get_art_url(self.album.artist, self.album.title)
        #     if art_url:
        #         print('there IS an art url', art_url)
        #         art_path = art_func.download(self.album.path, art_url)
        #         if art_path:
        #             self.album.art = art_path
        #             pixmap = QPixmap(str(self.album.art))
        #             self.album_widget.setPixmap(pixmap)

    def toggle_library(self):
        if self.folder_view:
            if self.folder_view.isVisible():
                self.folder_view.setVisible(False)
            else:
                self.folder_view.setVisible(True)

    def toggle_tracklist(self):
        if self.album_view:
            if self.album_view.isVisible():
                self.album_view.setVisible(False)
            else:
                self.album_view.setVisible(True)
    
    def toggle_play_pause_button_text(self):
        if self.playback.active:
            if self.playback.playing:
                self.play_button.setText('PLAY')
                self.pause()
            else:
                self.play_button.setText('PAUSE')
                self.resume()

    def resizeEvent(self, event):
        w = self.album_widget.width()
        self.album_widget.resize(w, w)
        
def main():

    app = QApplication(sys.argv)
    player = Player()
    player.show()
    sys.exit(app.exec_())
    

if __name__ == '__main__':
    main()
