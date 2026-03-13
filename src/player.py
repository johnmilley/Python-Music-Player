# Player displays playback controls, album art, and currently playing track

from pathlib import Path
import math
import sys
sys.path.append('./tracklist') # clean this up

# local
from track import Track
from album import Album
from album_view import AlbumView
from progress_bar import ClickableProgressBar
from artwork_finder import ArtworkFinderDialog

# media playback - find one that uses crossplat mediakeys out of the box
from just_playback import Playback

# pyqt5
from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout, QPushButton, QLabel, QVBoxLayout, QSizePolicy, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt5.QtGui import QPixmap, QColor


class Player(QWidget):
    APP_UPDATE_TIME = 20 # ms

    track_finished = pyqtSignal()
    track_changed = pyqtSignal(object)
    art_clicked = pyqtSignal()

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
        self.setMinimumSize(350, 300)

        self.layout_player = QVBoxLayout()
        self.layout_player.setContentsMargins(0, 0, 0, 12)
        self.player = QWidget()
        self.player.setObjectName('player')

        # ALBUM ART
        self.layout_album_display = QVBoxLayout()
        self.album_widget = QLabel()
        self.album_widget.setMinimumSize(200, 150)
        self.album_widget.setObjectName('album-art')
        self.album_widget.setAlignment(Qt.AlignCenter)
        self.album_widget.setScaledContents(True)
        self.album_widget.setCursor(Qt.PointingHandCursor)
        self.album_widget.mousePressEvent = lambda e: self.art_clicked.emit() if e.button() == Qt.LeftButton else None
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setOffset(4, 4)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.album_widget.setGraphicsEffect(shadow)
        self.layout_player.addWidget(self.album_widget, stretch=1, alignment=Qt.AlignCenter)

        # Controls container — matches album art width
        self.controls_container = QWidget()
        controls_layout = QVBoxLayout()
        controls_layout.setContentsMargins(0, 4, 0, 0)
        controls_layout.setSpacing(6)

        # SONG TITLE - ARTIST
        self.track_info = QLabel('')
        self.track_info.setWordWrap(True)
        self.track_info.setObjectName('track-info')
        self.track_info.setAlignment(Qt.AlignCenter)
        self.track_info.setContentsMargins(0, 2, 0, 2)
        controls_layout.addWidget(self.track_info)

        # PROGRESS BAR
        self.layout_track_progress = QHBoxLayout()
        self.layout_track_progress.setContentsMargins(0, 0, 0, 0)

        self.track_progress_label = QLabel('0:00')
        self.track_progress_label.setObjectName('track-progress')
        self.track_progress_label.setFixedWidth(self.track_progress_label.fontMetrics().horizontalAdvance('-00:00') + 4)
        self.track_progress_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.progress_bar = ClickableProgressBar(self)
        self.progress_bar.seek_requested.connect(self.seek_to)
        self.progress_bar.start_playback.connect(self.resume)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(14)

        self.track_length_label = QLabel('0:00')
        self.track_length_label.setObjectName('track-length')
        self.track_length_label.setFixedWidth(self.track_length_label.fontMetrics().horizontalAdvance('-00:00') + 4)
        self.track_length_label.setCursor(Qt.PointingHandCursor)
        self.track_length_label.mousePressEvent = lambda e: self._toggle_time_display()
        self._show_remaining = True

        self.layout_track_progress.addWidget(self.track_progress_label)
        self.layout_track_progress.addWidget(self.progress_bar)
        self.layout_track_progress.addWidget(self.track_length_label)
        controls_layout.addLayout(self.layout_track_progress)

        # Toggle Library/Tracklist buttons
        self.toggle_library_btn = QPushButton('\u2630')
        self.toggle_library_btn.setToolTip('Toggle Library')
        self.toggle_library_btn.pressed.connect(self.toggle_library)
        self.toggle_library_btn.setObjectName('toggle-library-btn')
        self.toggle_library_btn.setCheckable(True)
        self.toggle_library_btn.setChecked(True)

        self.toggle_folder_btn = QPushButton('\u2261')
        self.toggle_folder_btn.setToolTip('Toggle Tracklist')
        self.toggle_folder_btn.pressed.connect(self.toggle_tracklist)
        self.toggle_folder_btn.setObjectName('toggle-folder-btn')
        self.toggle_folder_btn.setCheckable(True)
        self.toggle_folder_btn.setChecked(True)

        # TRACK CONTROL BUTTONS
        self.layout_player_buttons = QHBoxLayout()
        self.layout_player_buttons.setSpacing(4)
        self.layout_player_buttons.setContentsMargins(0, 0, 0, 0)

        self.prev_track_button = QPushButton('\u23ee')
        self.prev_track_button.pressed.connect(self.prev_track)
        self.prev_track_button.setObjectName('prev-button')

        self.play_button = QPushButton('\u25b6')
        self.play_button.pressed.connect(self.toggle_play_pause_button_text)
        self.play_button.setObjectName('play-button')

        self.next_track_button = QPushButton('\u23ed')
        self.next_track_button.pressed.connect(self.next_track)
        self.next_track_button.setObjectName('next-button')

        self.layout_player_buttons.addWidget(self.toggle_library_btn)
        self.layout_player_buttons.addWidget(self.prev_track_button)
        self.layout_player_buttons.addWidget(self.play_button)
        self.layout_player_buttons.addWidget(self.next_track_button)
        self.layout_player_buttons.addWidget(self.toggle_folder_btn)
        controls_layout.addLayout(self.layout_player_buttons)

        self.controls_container.setLayout(controls_layout)

        # Center controls horizontally using stretch spacers instead of
        # alignment flags — alignment flags constrain the widget to its
        # sizeHint, which breaks word-wrapped QLabel height calculation.
        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.addStretch()
        controls_row.addWidget(self.controls_container)
        controls_row.addStretch()
        self.layout_player.addLayout(controls_row)

        self.setLayout(self.layout_player)

    def _toggle_time_display(self):
        self._show_remaining = not self._show_remaining
        self._update_time_label()

    def _update_time_label(self, pos=None):
        if not self.current_track:
            return
        total = self.current_track.length
        if pos is None:
            pos = self.playback.curr_pos if self.playback.playing else 0
        if self._show_remaining:
            remaining = max(0, total - pos)
            self.track_length_label.setText(
                f"-{self.current_track.length_to_string(remaining)}")
        else:
            self.track_length_label.setText(
                self.current_track.length_to_string(total))

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
            self._update_time_label(pos)

        # Check if Track finished playing
        if pos >= total - 0.1:
            self.track_progress_label.setText(
                self.current_track.length_to_string(self.current_track.length)
                )
            self.progress_bar.setValue(1000)
            self.timer.stop()
            self.play_button.setText('\u25b6')
            self.track_finished.emit()
            if self.album and self.current_track != self.album.tracklist[-1]:
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
        self.track_changed.emit(self.current_track)

        # update UI
        self.update_gui_after_tracklist_load(self.album)

        # Play track
        try:
            self.playback.load_file(self.current_track.path)
            self.playback.play()
        except Exception as e:
            print(f"LOG: Unable to play: {e}")
            self.play_button.setText('\u25b6')
            self.track_info.setText(f"Error: could not play file")

        # Updates AlbumViewer with track currently playing
        if self.album_view:
            self.album_view.track_list_widget.setCurrentRow(self.track_pos)
            
    def load_track(self, album, track_pos, seek_to=0):
        """Load a track and update UI without playing. Optionally seek to position."""
        self.album = album
        self.track_pos = track_pos
        self.current_track = self.album.tracklist[self.track_pos]
        self.track_changed.emit(self.current_track)

        self.update_gui_after_tracklist_load(self.album)
        self.play_button.setText('\u25b6')

        if self.album_view:
            self.album_view.track_list_widget.setCurrentRow(self.track_pos)

        try:
            self.playback.load_file(self.current_track.path)
            self.playback.play()
            self.playback.pause()
            if seek_to > 0:
                self.playback.seek(seek_to)
                progress = int((seek_to / self.current_track.length) * 1000)
                self.progress_bar.setValue(progress)
                self.track_progress_label.setText(
                    self.current_track.length_to_string(seek_to))
        except Exception as e:
            print(f"LOG: Unable to load track: {e}")

    def pause(self):
        self.playback.pause()

    def resume(self):
        self.playback.resume()
        self.timer.start(self.APP_UPDATE_TIME)
        self.play_button.setText('\u23f8')

    def update_gui_after_tracklist_load(self, album):
        """
            Updates GUI with track information when new track begins play

            art, title, artist, current time ellapsed in track mm:ss
        """
        self.album = album

        # Update TRACK TITLE - ARTIST
        title = str(self.current_track.title or '')
        artist = str(self.current_track.artist or '')
        if title and artist:
            self.track_info.setText(f"{title} - {artist}")
        elif title:
            self.track_info.setText(title)
        elif self.album.artist and self.album.title:
            self.track_info.setText(f"{self.album.artist} - {self.album.title}")
        else:
            self.track_info.setText(self.current_track.filename)

        self.play_button.setText('\u23f8')

        # Update DURATION
        if self.current_track:
            self._update_time_label(0)

    def load_album_art(self, album):
        """Load cover.jpg from album folder, or offer to search iTunes."""
        if self.album.art:
            pixmap = QPixmap(str(self.album.art))
            self.album_widget.setPixmap(pixmap)
        else:
            self.album_widget.clear()
            self._offer_artwork_search()

    def _offer_artwork_search(self):
        """Open the artwork finder dialog to search iTunes for cover art."""
        if not self.album or not self.album.path:
            return
        import theme as theme_mod
        app = self.window()
        t = getattr(app, 'current_theme', theme_mod.LIGHT)
        # Override accent like apply_theme does
        t = dict(t)
        t['accent'] = getattr(app, 'accent_color', theme_mod.DEFAULT_ACCENT)
        t['selection'] = t['accent']

        dialog = ArtworkFinderDialog(
            self.album.artist, self.album.title,
            self.album.path, t, parent=self
        )
        dialog.artwork_saved.connect(self._on_artwork_saved)
        dialog.exec_()

    def _on_artwork_saved(self, path):
        """Called when artwork is downloaded and saved."""
        from pathlib import Path as P
        self.album.art = P(path)
        pixmap = QPixmap(path)
        self.album_widget.setPixmap(pixmap)
        # Notify app to update accent palette
        app = self.window()
        if hasattr(app, '_update_accent_for_album'):
            app._update_accent_for_album(force=True)

    def _toggle_panel(self, panel, button):
        """Hides or shows a side panel within the existing window size."""
        if not panel:
            return
        panel.setVisible(not panel.isVisible())
        button.setChecked(panel.isVisible())

    def toggle_library(self):
        self._toggle_panel(self.folder_view, self.toggle_library_btn)

    def toggle_tracklist(self):
        self._toggle_panel(self.album_view, self.toggle_folder_btn)
    
    # mix of UI and logic
    def toggle_play_pause_button_text(self):
        if self.playback.active:
            if self.playback.playing:
                self.play_button.setText('\u25b6')
                self.pause()
            else:
                self.play_button.setText('\u23f8')
                self.resume()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep album art square, fitting within available width
        available = self.width() - 10
        controls_height = 100 if self.height() < 450 else 180
        size = min(available, self.height() - controls_height)
        size = max(size, 100)
        self.album_widget.setFixedSize(size, size)
        self.controls_container.setFixedWidth(size)
        
def main():

    app = QApplication(sys.argv)
    player = Player()
    player.show()
    sys.exit(app.exec_())
    

if __name__ == '__main__':
    main()
