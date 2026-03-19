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
from marquee_label import MarqueeLabel

# media playback - find one that uses crossplat mediakeys out of the box
from just_playback import Playback

# pyqt5
from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout, QPushButton, QLabel, QVBoxLayout, QSizePolicy, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal, QByteArray
from PyQt5.QtGui import QPixmap, QColor, QIcon, QPainter
from PyQt5.QtSvg import QSvgRenderer


if getattr(sys, '_MEIPASS', None):
    ICONS_DIR = Path(sys._MEIPASS) / 'icons'
else:
    ICONS_DIR = Path(__file__).parent / 'icons'

def _render_svg(name, color, size):
    """Render an SVG icon with the given fill color and return a QPixmap."""
    svg_path = ICONS_DIR / f'{name}.svg'
    svg_data = svg_path.read_text()
    svg_data = svg_data.replace('<path d=', f'<path fill="{color}" d=')
    svg_data = svg_data.replace('stroke="black"', f'stroke="{color}"')
    renderer = QSvgRenderer(QByteArray(svg_data.encode()))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def _svg_icon(name, color='black', size=32, hover_color=None):
    """Load an SVG icon with normal and optional hover/active color variants."""
    icon = QIcon(_render_svg(name, color, size))
    if hover_color:
        hover_pixmap = _render_svg(name, hover_color, size)
        icon.addPixmap(hover_pixmap, QIcon.Active)
    return icon


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
        # Playlist: the album/feed that is actually playing (not just displayed)
        self.playlist = None
        self.playlist_pos = 0

    def build_gui(self):
        """
            Builds the Player inferface

            General code steps:
                Create X Layout
                Create Widgets (style and attach events)
                Add Widgets to X Layout
                Add X Layout to PARENT layout (player)

        """
        self.setMinimumSize(200, 250)

        self.layout_player = QVBoxLayout()
        self.layout_player.setContentsMargins(0, 0, 0, 2)
        self.player = QWidget()
        self.player.setObjectName('player')

        # ALBUM ART
        self.layout_album_display = QVBoxLayout()
        self.album_widget = QLabel()
        self.album_widget.setMinimumSize(80, 80)
        self.album_widget.setObjectName('album-art')
        self.album_widget.setAlignment(Qt.AlignCenter)
        self.album_widget.setScaledContents(True)
        self.album_widget.setCursor(Qt.PointingHandCursor)
        self.album_widget.mousePressEvent = lambda e: self.art_clicked.emit() if e.button() == Qt.LeftButton else None
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(6)
        shadow.setOffset(2, 2)
        shadow.setColor(QColor(0, 0, 0, 200))
        self.album_widget.setGraphicsEffect(shadow)
        self.layout_player.addWidget(self.album_widget, stretch=1, alignment=Qt.AlignCenter)

        # Controls container — matches album art width
        self.controls_container = QWidget()
        controls_layout = QVBoxLayout()
        controls_layout.setContentsMargins(0, 2, 0, 0)
        controls_layout.setSpacing(4)

        # SONG TITLE - ARTIST
        self.track_info = MarqueeLabel('')
        self.track_info.setObjectName('track-info')
        self.track_info.setAlignment(Qt.AlignCenter)
        self.track_info.setContentsMargins(0, 0, 0, 0)
        self.track_info.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        controls_layout.addWidget(self.track_info)

        # PROGRESS BAR
        self.layout_track_progress = QHBoxLayout()
        self.layout_track_progress.setContentsMargins(0, 0, 0, 0)

        self.track_progress_label = QLabel('0:00')
        self.track_progress_label.setObjectName('track-progress')
        self.track_progress_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.progress_bar = ClickableProgressBar(self)
        self.progress_bar.seek_requested.connect(self.seek_to)
        self.progress_bar.start_playback.connect(self.resume)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)

        self.track_length_label = QLabel('0:00')
        self.track_length_label.setObjectName('track-length')
        self.track_length_label.setCursor(Qt.PointingHandCursor)
        self.track_length_label.mousePressEvent = lambda e: self._toggle_time_display()
        self._show_remaining = True

        self.layout_track_progress.addWidget(self.track_progress_label)
        self.layout_track_progress.addWidget(self.progress_bar)
        self.layout_track_progress.addWidget(self.track_length_label)
        controls_layout.addLayout(self.layout_track_progress)

        # TRACK CONTROL BUTTONS
        self._icon_size = QSize(24, 24)
        self.layout_player_buttons = QHBoxLayout()
        self.layout_player_buttons.setSpacing(4)
        self.layout_player_buttons.setContentsMargins(0, 0, 0, 0)

        self.prev_track_button = QPushButton()
        self.prev_track_button.pressed.connect(self.prev_track)
        self.prev_track_button.setObjectName('prev-button')
        self.prev_track_button.setIconSize(self._icon_size)
        self.prev_track_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self.play_button = QPushButton()
        self.play_button.pressed.connect(self.toggle_play_pause_button_text)
        self.play_button.setObjectName('play-button')
        self.play_button.setIconSize(self._icon_size)
        self.play_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self.next_track_button = QPushButton()
        self.next_track_button.pressed.connect(self.next_track)
        self.next_track_button.setObjectName('next-button')
        self.next_track_button.setIconSize(self._icon_size)
        self.next_track_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._is_playing = False
        self.update_button_icons()

        for btn in (self.prev_track_button, self.play_button, self.next_track_button):
            btn.setMinimumWidth(20)
            shadow = QGraphicsDropShadowEffect(btn)
            shadow.setBlurRadius(6)
            shadow.setOffset(0, 2)
            shadow.setColor(QColor(0, 0, 0, 50))
            btn.setGraphicsEffect(shadow)

        self._btn_container = QWidget()
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addWidget(self.prev_track_button)
        btn_layout.addWidget(self.play_button)
        btn_layout.addWidget(self.next_track_button)
        self._btn_container.setLayout(btn_layout)
        self.layout_player_buttons.addStretch()
        self.layout_player_buttons.addWidget(self._btn_container)
        self.layout_player_buttons.addStretch()
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

    def update_button_icons(self, color=None, hover_color=None):
        """Refresh all button icons with the given color (for theme changes)."""
        if color is None:
            color = getattr(self, '_icon_color', 'black')
        self._icon_color = color
        self._icon_hover_color = hover_color
        self.prev_track_button.setIcon(_svg_icon('skip_previous', color, hover_color=hover_color))
        self.next_track_button.setIcon(_svg_icon('skip_next', color, hover_color=hover_color))
        self._set_play_icon()

    def _set_play_icon(self, playing=None):
        """Update play button icon to play or pause."""
        if playing is not None:
            self._is_playing = playing
        name = 'pause' if self._is_playing else 'play_arrow'
        color = getattr(self, '_icon_color', 'black')
        hover_color = getattr(self, '_icon_hover_color', None)
        self.play_button.setIcon(_svg_icon(name, color, hover_color=hover_color))

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
            self._update_time_label(seconds)
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
            self._set_play_icon(False)
            self.track_finished.emit()
            if self.playlist and self.current_track != self.playlist.tracklist[-1]:
                self.next_track()

    def next_track(self):
        if self.playlist:
            if self.playlist_pos != len(self.playlist.tracklist) - 1:
                self.playlist_pos += 1
            else:
                self.playlist_pos = 0
            self.play(self.playlist, self.playlist_pos)

    def prev_track(self):
        if self.playlist:
            if self.playlist_pos != 0:
                self.playlist_pos -= 1
            else:
                self.playlist_pos = len(self.playlist.tracklist) - 1
            self.play(self.playlist, self.playlist_pos)

    def play(self, album, track_pos):
        self.timer.start(self.APP_UPDATE_TIME) # updates time elapsed

        # update instance variables (from AlbumView)
        self.album = album
        self.track_pos = track_pos
        self.playlist = album
        self.playlist_pos = track_pos
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
            self._set_play_icon(False)
            self.track_info.setText(f"Error: could not play file")

        # Updates AlbumViewer with track currently playing
        if self.album_view:
            self.album_view.track_list_widget.setCurrentRow(self.track_pos)
            
    def load_track(self, album, track_pos, seek_to=0):
        """Load a track and update UI without playing. Optionally seek to position."""
        self.album = album
        self.track_pos = track_pos
        self.playlist = album
        self.playlist_pos = track_pos
        self.current_track = self.album.tracklist[self.track_pos]
        self.track_changed.emit(self.current_track)

        self.update_gui_after_tracklist_load(self.album)
        self._set_play_icon(False)

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
        self._set_play_icon(True)

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

        self._set_play_icon(True)

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
        self.update_layout()

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

    
    # mix of UI and logic
    def toggle_play_pause_button_text(self):
        if self.playback.active:
            if self.playback.playing:
                self._set_play_icon(False)
                self.pause()
            else:
                self._set_play_icon(True)
                self.resume()

    def update_layout(self):
        """Recalculate control sizing after mode/visibility changes."""
        self.resizeEvent(None)

    def resizeEvent(self, event):
        if event:
            super().resizeEvent(event)
        # Calculate controls height from actual child sizes
        line_h = self.track_info.fontMetrics().lineSpacing()
        bar_h = self.progress_bar.height()
        btn_h = self.play_button.sizeHint().height()
        margins = self.layout_player.contentsMargins()
        controls_height = line_h + bar_h + btn_h + margins.top() + margins.bottom() + 20

        # Keep album art square, filling available width with minimal margin
        margin = min(10, int(self.width() * 0.02))
        available = self.width() - margin * 2
        size = min(available, self.height() - controls_height)
        size = max(size, 80)
        self.album_widget.setFixedSize(size, size)
        self.controls_container.setFixedWidth(size)

        # Scale controls to fit available width
        compact = size < 250
        icon_dim = max(16, min(24, size // 12))
        icon_size = QSize(icon_dim, icon_dim)
        btn_spacing = self._btn_container.layout().spacing()
        visible = [b for b in (self.prev_track_button, self.play_button, self.next_track_button) if b.isVisible()]
        btn_w = max(24, (size - btn_spacing * (len(visible) + 1)) // max(len(visible), 1))
        for btn in (self.prev_track_button, self.play_button, self.next_track_button):
            btn.setIconSize(icon_size)
            btn.setFixedWidth(btn_w)

        # Constrain button container so buttons shrink together
        self._btn_container.setMaximumWidth(size)

        # Adapt time label widths — use fraction of controls width
        time_w = max(30, size // 5)
        self.track_progress_label.setFixedWidth(time_w)
        self.track_length_label.setFixedWidth(time_w)

        # Tighten spacing when compact
        sp = 2 if compact else 4
        self.controls_container.layout().setSpacing(sp)
        self.controls_container.layout().setContentsMargins(0, sp, 0, 0)
        self._btn_container.layout().setSpacing(2 if compact else 4)
        
def main():

    app = QApplication(sys.argv)
    player = Player()
    player.show()
    sys.exit(app.exec_())
    

if __name__ == '__main__':
    main()
