# Player displays playback controls, album art, and currently playing track

from pathlib import Path
import math
import sys
sys.path.append('./tracklist') # clean this up

# local
from track import Track
from album import Album
from album_view import AlbumView
from art_label import AlbumArtLabel
from progress_bar import ClickableProgressBar
from artwork_finder import ArtworkFinderDialog
from color_extract import text_color_for
from marquee_label import MarqueeLabel

# media playback - find one that uses crossplat mediakeys out of the box
from just_playback import Playback

# pyqt5
from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout,
    QPushButton, QLabel, QVBoxLayout, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, QSize, QEvent, QThread, pyqtSignal, QByteArray
from PyQt5.QtGui import QPixmap, QColor, QIcon, QImage, QPainter, QFontMetrics
from PyQt5.QtSvg import QSvgRenderer

import bg_threads


if getattr(sys, '_MEIPASS', None):
    ICONS_DIR = Path(sys._MEIPASS) / 'icons'
else:
    ICONS_DIR = Path(__file__).parent / 'icons'

_ICON_CACHE = {}  # (name, color, size) -> QPixmap

def _render_svg(name, color, size):
    """Render an SVG icon with the given fill color and return a QPixmap.

    Rendered pixmaps are memoized — theme/accent changes and mode-control
    swaps request the same handful of (name, color, size) combinations over
    and over, so this avoids repeated disk reads and rasterization.
    """
    key = (name, color, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
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
    _ICON_CACHE[key] = pixmap
    return pixmap


class _ImageLoadThread(QThread):
    """Decode an image file off the UI thread — QImage is thread-safe to
    construct (unlike QPixmap). Album covers live on a possibly slow NAS,
    so a synchronous QPixmap(path) on album/track switches froze the UI
    for as long as the read+decode took."""
    image_ready = pyqtSignal(int, QImage)

    def __init__(self, path, token):
        super().__init__()
        self.path = str(path)
        self.token = token

    def run(self):
        self.image_ready.emit(self.token, QImage(self.path))


def _svg_icon(name, color='black', size=32, hover_color=None):
    """Load an SVG icon with normal and optional hover/active color variants."""
    icon = QIcon(_render_svg(name, color, size))
    if hover_color:
        hover_pixmap = _render_svg(name, hover_color, size)
        icon.addPixmap(hover_pixmap, QIcon.Active)
    return icon


class Player(QWidget):
    # Progress/lyrics tick interval. 200ms is plenty: the progress bar has
    # 1000 steps, time labels change once per second, and LRC lyrics lines
    # are second-granularity.
    APP_UPDATE_TIME = 200 # ms

    track_finished = pyqtSignal()
    track_changed = pyqtSignal(object)
    art_clicked = pyqtSignal()
    art_changed = pyqtSignal(QPixmap)
    play_state_changed = pyqtSignal(bool)
    # (track, seconds actually listened) — emitted by flush_listen() when a
    # track is about to be replaced (or the app closes). Player stays
    # log-agnostic: thresholds and persistence live in play_log/App.
    listen_ended = pyqtSignal(object, float)

    def __init__(self, album=None, folder_view=None, album_view=None):
        super().__init__()

        # Player plays Album, Tracks (queue) displayed in AlbumView
        self.album = album
        self.album_view = album_view # attached at the App level
        self.folder_view = folder_view

        # Compactness: 1.0 = roomy chrome, 0.0 = tightest. Recomputed from
        # available height in resizeEvent so the controls block shrinks
        # before it ever eats into the album art's space.
        self._compact_t = 1.0
        self._last_font_size = None

        # Artwork gallery: cover.jpg first, then any other images from the
        # album folder (back covers, inserts...). Registered AlbumArtLabels
        # (player column, max mode, mini mode) get hover arrows to scroll it.
        self._art_paths = []
        self._art_index = 0
        self._art_labels = []
        # Async art decode: token guards against a stale decode landing
        # after a newer request (rapid album switches / gallery stepping)
        self._art_token = 0
        self._art_thread = None

        # Extra progress bar/time-label sets (max mode, mini mode overlay
        # panels) that mirror the player column's own — same pattern as
        # _art_labels, single source of truth stays check_track_pos/etc.
        self._extra_progress_bars = []

        self.build_gui()

        # just_playback: see notes/just_played_usage.png
        self.playback = Playback()
        self._time_elapsed = 0
        # Seconds of *actual* playback for the current track: ticked in
        # check_track_pos only while playing, untouched by seeks, reset by
        # flush_listen(). This is what decides whether a play counts.
        self._listened = 0.0
        
        # Timer is used to track elapsed time and end of track
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_track_pos)
        
        # Tracklist: a list of Track objects
        self.current_track = None
        self.track_pos = 0
        # Playlist: the album/feed that is actually playing (not just displayed)
        self.playlist = None
        self.playlist_pos = 0
        # Shuffle: next_track draws from a shuffled bag of the remaining
        # indices (so every track plays once per cycle); prev_track walks
        # back through the actual play order.
        self.shuffle = False
        self._shuffle_bag = []
        self._shuffle_history = []
        self._shuffle_for = None  # the playlist the bag was drawn for

    def build_gui(self):
        """Build the player column: art on top, controls block below.

        Sizing is left entirely to Qt layouts — the art expands into the
        remaining space (AlbumArtLabel letterboxes and caches its own
        scaling) and the controls block keeps a fixed height, capped width,
        and stays horizontally centered.
        """
        self.setMinimumSize(180, 220)
        self.setObjectName('player')
        # Custom QWidget subclasses only paint QSS backgrounds with this set —
        # the player column sits on the elevated background tone
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.layout_player = QVBoxLayout()
        self.layout_player.setContentsMargins(12, 12, 12, 12)
        self.layout_player.setSpacing(10)

        # ALBUM ART — square footprint, cached scaling. Centered as a tight
        # unit with the controls (stretches above/below share the slack).
        self.layout_player.addStretch(1)
        self.album_widget = AlbumArtLabel(square=True)
        self.album_widget.clicked.connect(self.art_clicked.emit)
        self.register_art_label(self.album_widget)
        self.layout_player.addWidget(self.album_widget)

        # Big favourite heart over the art, shown only on hover (normal
        # mode only; max/mini mode have their own separate art + full
        # ControlPanel). Deferred import: overlay_controls imports
        # _render_svg from this module.
        import overlay_controls
        self.heart_overlay = overlay_controls.HeartOverlay(self.album_widget)
        self.album_widget.installEventFilter(self)

        # Controls container — fixed height, capped width, centered
        self.controls_container = QWidget()
        self.controls_container.setObjectName('player-controls')
        self.controls_container.setMaximumWidth(420)
        self.controls_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        controls_layout = QVBoxLayout()
        controls_layout.setContentsMargins(0, 6, 0, 0)
        controls_layout.setSpacing(6)
        self.controls_layout = controls_layout

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
        self.progress_bar.setFixedHeight(8)

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
        self._icon_size = QSize(40, 40)
        self.layout_player_buttons = QHBoxLayout()
        self.layout_player_buttons.setSpacing(0)
        self.layout_player_buttons.setContentsMargins(0, 2, 0, 0)

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
            btn.setCursor(Qt.PointingHandCursor)

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

        # Center the controls block; it caps at 420px wide
        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.addStretch(1)
        controls_row.addWidget(self.controls_container, stretch=8)
        controls_row.addStretch(1)
        self.layout_player.addLayout(controls_row)
        self.layout_player.addStretch(1)

        self.setLayout(self.layout_player)
        self.set_control_scale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_compactness()

    def eventFilter(self, obj, event):
        """Show/hide/position the hover heart — Enter/Leave on the art
        widget itself, since its child (the heart button) would otherwise
        swallow those events before they reach it."""
        if obj is self.album_widget:
            t = event.type()
            if t == QEvent.Enter:
                self._position_heart_overlay()
                self.heart_overlay.show()
                self.heart_overlay.raise_()
            elif t == QEvent.Leave:
                self.heart_overlay.hide()
            elif t == QEvent.Resize and self.heart_overlay.isVisible():
                self._position_heart_overlay()
        return super().eventFilter(obj, event)

    def _position_heart_overlay(self):
        hint = self.heart_overlay.sizeHint()
        x = (self.album_widget.width() - hint.width()) // 2
        y = (self.album_widget.height() - hint.height()) // 2
        self.heart_overlay.setGeometry(x, y, hint.width(), hint.height())

    def _update_compactness(self):
        """Shrink the controls block's chrome (margins, spacing, icon size,
        progress bar thickness) as the column gets short — the album art
        keeps first claim on vertical space instead of being squeezed."""
        lo, hi = 240, 480
        t = max(0.0, min(1.0, (self.height() - lo) / (hi - lo)))
        if abs(t - self._compact_t) < 0.02:
            return
        self._compact_t = t
        margin = round(4 + 8 * t)
        self.layout_player.setContentsMargins(margin, margin, margin, margin)
        self.layout_player.setSpacing(round(4 + 6 * t))
        self.controls_layout.setSpacing(round(2 + 4 * t))
        self.progress_bar.setFixedHeight(round(5 + 3 * t))
        self.set_control_scale(self._last_font_size)

    def _toggle_time_display(self):
        self._show_remaining = not self._show_remaining
        self._update_time_label()

    def update_button_icons(self, color=None, hover_color=None):
        """Refresh all button icons with the given color (for theme changes)."""
        if color is None:
            color = getattr(self, '_icon_color', 'black')
        self._icon_color = color
        self._icon_hover_color = hover_color
        if hover_color:
            self._accent_color = hover_color
        self._set_btn_hover_icons(self.prev_track_button, 'skip_previous', color, hover_color)
        self._set_btn_hover_icons(self.next_track_button, 'skip_next', color, hover_color)
        self._set_play_icon()
        if hasattr(self, 'heart_overlay'):
            accent = getattr(self, '_accent_color', None) or color
            self.heart_overlay.set_theme({'accent': accent})

    def _set_btn_hover_icons(self, btn, icon_name, color, hover_color):
        """Set normal icon and install enter/leave handlers for accent-contrast hover."""
        accent = getattr(self, '_accent_color', None)
        contrast = text_color_for(accent) if accent else color
        btn.setIcon(_svg_icon(icon_name, color))
        btn._normal_icon = _svg_icon(icon_name, color)
        btn._hover_icon = _svg_icon(icon_name, contrast)
        btn.enterEvent = lambda e, b=btn: b.setIcon(b._hover_icon)
        btn.leaveEvent = lambda e, b=btn: b.setIcon(b._normal_icon)

    def _set_play_icon(self, playing=None):
        """Update play button icon to play or pause."""
        if playing is not None:
            changed = playing != self._is_playing
            self._is_playing = playing
            if changed:
                self.play_state_changed.emit(playing)
        name = 'pause' if self._is_playing else 'play_arrow'
        color = getattr(self, '_icon_color', 'black')
        hover_color = getattr(self, '_icon_hover_color', None)
        self._set_btn_hover_icons(self.play_button, name, color, hover_color)

    def _update_time_label(self, pos=None):
        if not self.current_track:
            return
        total = self.current_track.length
        if pos is None:
            pos = self.playback.curr_pos if self.playback.playing else 0
        if self._show_remaining:
            remaining = max(0, total - pos)
            self._set_progress_text(
                len_text=f"-{self.current_track.length_to_string(remaining)}")
        else:
            self._set_progress_text(
                len_text=self.current_track.length_to_string(total))

    def seek_to(self, pos):
        self.playback.pause()
        if self.current_track:
            # 1000 is the size of the progress bar
            seconds = (pos / 1000) * self.current_track.length
            self._set_progress_text(
                pos_text=self.current_track.length_to_string(seconds))
            self._update_time_label(seconds)
            self.playback.seek(seconds)

    def check_track_pos(self):
        """
            runs every APP_UPDATE_TIME (milliseconds)
        """

        if not self.current_track or not self.playback.playing:
            return

        self._listened += self.APP_UPDATE_TIME / 1000.0

        pos = self.playback.curr_pos
        total = self.current_track.length

        # Update progress bar
        if total > 0:
            progress = int((pos / total) * 1000)
            self._set_progress_value(progress)

        # Update progress label
        if int(pos) != int(self._time_elapsed):
            self._time_elapsed = pos
            self._set_progress_text(
                pos_text=self.current_track.length_to_string(pos))
            self._update_time_label(pos)

        # Check if Track finished playing (margin covers one timer tick)
        if pos >= total - 0.3:
            self._set_progress_text(
                pos_text=self.current_track.length_to_string(self.current_track.length))
            self._set_progress_value(1000)
            self.timer.stop()
            self._set_play_icon(False)
            self.track_finished.emit()
            if self.playlist:
                if self.shuffle:
                    # Advance until the shuffled cycle has played every
                    # track once (the bag refills on manual next)
                    if self._shuffle_for is not self.playlist or self._shuffle_bag:
                        self.next_track()
                elif self.current_track != self.playlist.tracklist[-1]:
                    self.next_track()

    def next_track(self):
        if not self.playlist:
            return
        if self.shuffle and len(self.playlist.tracklist) > 1:
            if self._shuffle_for is not self.playlist:
                self._shuffle_bag = []
                self._shuffle_history = []
                self._shuffle_for = self.playlist
            if not self._shuffle_bag:
                import random
                self._shuffle_bag = [
                    i for i in range(len(self.playlist.tracklist))
                    if i != self.playlist_pos]
                random.shuffle(self._shuffle_bag)
            self._shuffle_history.append(self.playlist_pos)
            self.playlist_pos = self._shuffle_bag.pop(0)
        elif self.playlist_pos != len(self.playlist.tracklist) - 1:
            self.playlist_pos += 1
        else:
            self.playlist_pos = 0
        self.play(self.playlist, self.playlist_pos)

    def prev_track(self):
        if not self.playlist:
            return
        if self.shuffle and self._shuffle_history \
                and self._shuffle_for is self.playlist:
            self.playlist_pos = self._shuffle_history.pop()
        elif self.playlist_pos != 0:
            self.playlist_pos -= 1
        else:
            self.playlist_pos = len(self.playlist.tracklist) - 1
        self.play(self.playlist, self.playlist_pos)

    def flush_listen(self):
        """Report the outgoing track's accumulated listen time and reset.
        Must run before current_track is reassigned — first statement of
        play()/load_track() — and once more from App on close."""
        if self.current_track is not None and self._listened > 0:
            self.listen_ended.emit(self.current_track, self._listened)
        self._listened = 0.0

    def play(self, album, track_pos):
        self.flush_listen()
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
        self.flush_listen()
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
                self._set_progress_value(progress)
                self._set_progress_text(
                    pos_text=self.current_track.length_to_string(seek_to))
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

        # Update TRACK TITLE
        title = str(self.current_track.title or '')
        if title:
            self.track_info.setText(title)
        else:
            self.track_info.setText(self.current_track.filename)

        self._set_play_icon(True)

        # Update DURATION
        if self.current_track:
            self._update_time_label(0)

    def set_art(self, pixmap):
        """Route single artwork through here so listeners (max/mini mode)
        stay in sync. Clears any multi-image gallery."""
        self._art_paths = []
        self._art_index = 0
        self._art_token += 1  # invalidate any in-flight async decode
        self._set_nav_enabled(False)
        self._display_art(pixmap)

    def set_art_path(self, path):
        """Single-image variant of set_art that decodes off the UI thread.
        path=None clears the art."""
        self._art_paths = []
        self._art_index = 0
        self._set_nav_enabled(False)
        self._load_art_async(path)

    def _load_art_async(self, path):
        """Decode an image in a background thread and display it when done.
        Superseded decodes are token-invalidated and their threads retired
        (never dropped while running, never waited on)."""
        self._art_token += 1
        if not path:
            self._display_art(None)
            return
        old = self._art_thread
        if old is not None:
            bg_threads.retire(old)
        t = _ImageLoadThread(path, self._art_token)
        t.image_ready.connect(self._on_art_image_ready)
        self._art_thread = t
        t.start()

    def _on_art_image_ready(self, token, image):
        if token != self._art_token:
            return  # a newer request superseded this decode
        self._display_art(
            QPixmap.fromImage(image) if not image.isNull() else None)

    def _display_art(self, pixmap):
        if pixmap is None or pixmap.isNull():
            self.album_widget.clear()
            self.art_changed.emit(QPixmap())
        else:
            self.album_widget.set_source(pixmap)
            # Emit the display copy (already downscaled) for reuse elsewhere
            self.art_changed.emit(self.album_widget.pixmap())

    # ── Artwork gallery (multiple images per album) ────────────────

    def register_art_label(self, label):
        """Wire an AlbumArtLabel's hover arrows to the shared art gallery.
        The player column, max mode and mini mode all register here."""
        self._art_labels.append(label)
        label.prev_requested.connect(lambda: self.step_art(-1))
        label.next_requested.connect(lambda: self.step_art(1))
        label.set_nav_enabled(len(self._art_paths) > 1)

    def _set_nav_enabled(self, enabled):
        for label in self._art_labels:
            label.set_nav_enabled(enabled)

    # ── Progress bar / time labels (mirrored onto max/mini overlays) ──

    def register_progress_display(self, progress_bar, pos_label, len_label):
        """Wire a ClickableProgressBar + time labels (max/mini mode's
        overlay panel) to seek/resume, and mirror the player column's own
        progress bar/labels onto them from here on — same registration
        pattern as register_art_label."""
        progress_bar.seek_requested.connect(self.seek_to)
        progress_bar.start_playback.connect(self.resume)
        progress_bar.setRange(0, 1000)
        progress_bar.setTextVisible(False)
        self._extra_progress_bars.append((progress_bar, pos_label, len_label))
        progress_bar.setValue(self.progress_bar.value())
        pos_label.setText(self.track_progress_label.text())
        len_label.setText(self.track_length_label.text())

    def _set_progress_value(self, value):
        self.progress_bar.setValue(value)
        for bar, _, _ in self._extra_progress_bars:
            bar.setValue(value)

    def _set_progress_text(self, pos_text=None, len_text=None):
        if pos_text is not None:
            self.track_progress_label.setText(pos_text)
            for _, pos_label, _ in self._extra_progress_bars:
                pos_label.setText(pos_text)
        if len_text is not None:
            self.track_length_label.setText(len_text)
            for _, _, len_label in self._extra_progress_bars:
                len_label.setText(len_text)

    def set_art_gallery(self, paths):
        """Show a scrollable set of artwork images (cover first)."""
        self._art_paths = [str(p) for p in paths]
        self._art_index = 0
        self._set_nav_enabled(len(self._art_paths) > 1)
        self._load_art_async(self._art_paths[0] if self._art_paths else None)

    def step_art(self, delta):
        """Scroll the gallery forward/back (wraps around)."""
        if len(self._art_paths) < 2:
            return
        self._art_index = (self._art_index + delta) % len(self._art_paths)
        self._load_art_async(self._art_paths[self._art_index])

    def refresh_art_gallery(self):
        """Re-scan the album folder after artwork was added or replaced."""
        if self.album and hasattr(self.album, 'refresh_art'):
            self.album.refresh_art()
            if self.album.art_list:
                self.set_art_gallery(self.album.art_list)

    def load_album_art(self, album):
        """Load artwork from the album folder, or offer to search iTunes."""
        art_list = getattr(self.album, 'art_list', None)
        if art_list:
            self.set_art_gallery(art_list)
        elif self.album.art:
            self.set_art_path(str(self.album.art))
        else:
            self.set_art(None)
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
            self.album.path, t, parent=self,
            fs=getattr(app, 'font_size', None)
        )
        dialog.artwork_saved.connect(self._on_artwork_saved)
        dialog.exec_()

    def _on_artwork_saved(self, path):
        """Called when artwork is downloaded and saved."""
        from pathlib import Path as P
        self.album.art = P(path)
        if hasattr(self.album, 'refresh_art'):
            self.refresh_art_gallery()
        else:
            self.set_art(QPixmap(path))
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

    def set_control_scale(self, font_size=None):
        """Size icons and time labels from the controls font size, scaled
        down further by the current compactness (see _update_compactness).

        Called at build time, whenever the theme/font changes, and whenever
        the column gets short enough to need tighter chrome.
        """
        if font_size is None:
            import theme as theme_mod
            font_size = theme_mod.DEFAULT_SIZE
        self._last_font_size = font_size
        compact_scale = 0.7 + 0.3 * self._compact_t  # 0.7 tight .. 1.0 roomy
        icon_dim = max(22, min(56, int(font_size * 3.2 * compact_scale)))
        icon_size = QSize(icon_dim, icon_dim)
        for btn in (self.prev_track_button, self.play_button, self.next_track_button):
            btn.setIconSize(icon_size)
            btn.setFixedHeight(icon_dim + 8)
            btn.setMinimumWidth(icon_dim + 20)
        if hasattr(self, '_icon_color'):
            self.update_button_icons()
        # Time labels get a stable width so the progress bar doesn't jitter
        fm = QFontMetrics(self.track_length_label.font())
        time_w = fm.horizontalAdvance('-88:88') + 6
        self.track_progress_label.setFixedWidth(time_w)
        self.track_length_label.setFixedWidth(time_w)

def main():

    app = QApplication(sys.argv)
    player = Player()
    player.show()
    sys.exit(app.exec_())
    

if __name__ == '__main__':
    main()
