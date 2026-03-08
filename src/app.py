# App contains Player, Album View, and FolderView widgets

import sys
from pathlib import Path

# local
from folder_view import FolderView
from player import Player
from album_view import AlbumView
from lyrics_widget import LyricsWidget
from lyrics_fetcher import LyricsFetchThread, lyrics_path_for_track
import theme

from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout,
    QAction, QActionGroup, QSplitter, QColorDialog, QShortcut, QDialog,
    QVBoxLayout, QLabel, QLineEdit)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QColor, QPixmap, QIcon, QKeySequence


class App(QMainWindow):
    def __init__(self):
        super().__init__()

        self.app_widget = QWidget()
        self.app_widget.setObjectName('main-window')

        self.player = Player()
        self.album_view = AlbumView()
        self.lyrics_widget = LyricsWidget()
        self.folder_view = FolderView(self.album_view)

        # Player and AlbumView coupling
        self.player.album_view = self.album_view
        self.player.folder_view = self.folder_view
        self.album_view.player = self.player

        # Lyrics fetching and sync
        self._lyrics_thread = None
        self._failed_lyrics = set()  # track paths with no results
        self.player.track_changed.connect(self._on_track_changed)
        self.player.timer.timeout.connect(self._update_lyrics_position)

        self.setWindowTitle("lp")
        icon_path = Path(__file__).parent.parent / 'icon.png'
        self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(800, 600)

        # Right column: album view + lyrics in a vertical splitter
        self.right_splitter = QSplitter(Qt.Vertical)
        self.right_splitter.addWidget(self.album_view)
        self.right_splitter.addWidget(self.lyrics_widget)
        self.right_splitter.setStretchFactor(0, 3)
        self.right_splitter.setStretchFactor(1, 2)
        self.right_splitter.setCollapsible(0, False)
        self.right_splitter.setCollapsible(1, False)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName('main-splitter')
        self.splitter.addWidget(self.folder_view)
        self.splitter.addWidget(self.player)
        self.splitter.addWidget(self.right_splitter)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 2)
        self.splitter.setCollapsible(0, False)  # folder view
        self.splitter.setCollapsible(1, False)  # player
        self.splitter.setCollapsible(2, False)  # right column

        self.layout_app = QHBoxLayout()
        self.layout_app.setContentsMargins(0, 0, 0, 0)
        self.layout_app.addWidget(self.splitter)
        self.app_widget.setLayout(self.layout_app)

        self.setCentralWidget(self.app_widget)

        # Menu bar — Preferences
        self.prefs_menu = self.menuBar().addMenu('Preferences')

        self.dark_mode_action = QAction('Dark Mode', self)
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

        # Accent color submenu
        self.accent_menu = self.prefs_menu.addMenu('Accent Color')
        self.accent_group = QActionGroup(self)
        self.accent_color = theme.DEFAULT_ACCENT
        for name, color in theme.ACCENT_PRESETS.items():
            action = QAction(name, self)
            action.setCheckable(True)
            action.setData(color)
            action.setIcon(self._color_icon(color))
            if name == 'Orange':
                action.setChecked(True)
            action.triggered.connect(lambda checked, c=color: self.set_accent(c))
            self.accent_group.addAction(action)
            self.accent_menu.addAction(action)
        self.accent_menu.addSeparator()
        custom_action = QAction('Custom...', self)
        custom_action.triggered.connect(self.pick_custom_accent)
        self.accent_menu.addAction(custom_action)

        # Change album art action
        self.prefs_menu.addSeparator()
        self.change_art_action = QAction('Change Album Art...', self)
        self.change_art_action.triggered.connect(self._change_album_art)
        self.prefs_menu.addAction(self.change_art_action)

        # Miniplayer state
        self.is_miniplayer = False
        self._pre_mini_geometry = None
        self._pre_mini_splitter = None

        # Theme setup
        self.current_theme = theme.LIGHT
        self.apply_theme(self.current_theme)

        self.album_view.album_changed.connect(self.setWindowTitle)

        # Restore saved state
        self.settings = QSettings('lp', 'music-player')
        self._restore_state()

        # Keyboard shortcuts
        self._setup_shortcuts()

    def apply_theme(self, t):
        self.current_theme = t
        # Update menu text to show available action
        if t is theme.DARK:
            self.dark_mode_action.setText('Light Mode')
        else:
            self.dark_mode_action.setText('Dark Mode')
        # Override accent/selection with user's chosen color
        t = dict(t)
        t['accent'] = self.accent_color
        t['selection'] = self.accent_color
        fs = self.font_size
        compact = self.is_miniplayer
        self.setStyleSheet(theme.app_qss(t))
        self.player.setStyleSheet(theme.player_qss(t, fs, compact))
        self.folder_view.setStyleSheet(theme.folder_view_qss(t, fs))
        self.album_view.setStyleSheet(theme.album_view_qss(t, fs))
        self.lyrics_widget.setStyleSheet(theme.lyrics_qss(t, fs))
        self.lyrics_widget.set_theme(t)
        self.right_splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {t['accent']}; height: 3px; }}"
        )

    def toggle_theme(self):
        if self.current_theme is theme.LIGHT:
            self.apply_theme(theme.DARK)
        else:
            self.apply_theme(theme.LIGHT)

    def set_font_size(self, size):
        self.font_size = size
        self.apply_theme(self.current_theme)

    def set_accent(self, color):
        self.accent_color = color
        self.apply_theme(self.current_theme)

    def pick_custom_accent(self):
        color = QColorDialog.getColor(QColor(self.accent_color), self, 'Pick Accent Color')
        if color.isValid():
            # Uncheck any preset
            checked = self.accent_group.checkedAction()
            if checked:
                checked.setChecked(False)
            self.set_accent(color.name())

    def _change_album_art(self):
        """Open artwork finder to search for new album cover."""
        if not self.player.album or not self.player.album.path:
            return
        from artwork_finder import ArtworkFinderDialog
        t = dict(self.current_theme)
        t['accent'] = self.accent_color
        t['selection'] = self.accent_color
        dialog = ArtworkFinderDialog(
            self.player.album.artist, self.player.album.title,
            self.player.album.path, t, parent=self
        )
        dialog.artwork_saved.connect(self.player._on_artwork_saved)
        dialog.exec_()

    def _color_icon(self, color, width=64, height=16):
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(color))
        return QIcon(pixmap)

    def _restore_state(self):
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
        splitter_state = self.settings.value('splitter')
        if splitter_state:
            self.splitter.restoreState(splitter_state)
        right_splitter_state = self.settings.value('right_splitter')
        if right_splitter_state:
            self.right_splitter.restoreState(right_splitter_state)
        if self.settings.value('lyrics_visible') == 'false':
            self.lyrics_widget.setVisible(False)
        saved_fs = self.settings.value('font_size', type=int)
        if saved_fs and saved_fs in theme.FONT_SIZES:
            self.font_size = saved_fs
            for action in self.font_size_group.actions():
                if action.data() == saved_fs:
                    action.setChecked(True)
        saved_accent = self.settings.value('accent_color')
        if saved_accent:
            self.accent_color = saved_accent
            # Check matching preset, if any
            for action in self.accent_group.actions():
                action.setChecked(action.data() == saved_accent)
        if self.settings.value('dark_mode') == 'true':
            self.apply_theme(theme.DARK)
        else:
            self.apply_theme(self.current_theme)
        if self.settings.value('miniplayer') == 'true':
            self.enter_miniplayer()
        last_album = self.settings.value('last_album')
        if last_album:
            self.album_view.load_album_listing(last_album)
            track_pos = self.settings.value('last_track_pos', 0, type=int)
            seek_pos = self.settings.value('last_seek_pos', 0.0, type=float)
            if self.album_view.album and track_pos < len(self.album_view.album.tracklist):
                self.player.load_track(self.album_view.album, track_pos, seek_pos)

    def _setup_shortcuts(self):
        self.keybindings = [
            ('p',       'Play / Pause',       self.player.toggle_play_pause_button_text),
            ('>',       'Next track',          self.player.next_track),
            ('<',       'Previous track',      self.player.prev_track),
            ('f',       'Seek forward 5s',     lambda: self._seek_relative(5)),
            ('b',       'Seek back 5s',        lambda: self._seek_relative(-5)),
            ('.',       'Volume up',           lambda: self._adjust_volume(0.05)),
            (',',       'Volume down',         lambda: self._adjust_volume(-0.05)),
            ('1',       'Toggle library',      lambda: self.exit_miniplayer() if self.is_miniplayer else self.player.toggle_library()),
            ('2',       'Toggle tracklist',    lambda: self.exit_miniplayer() if self.is_miniplayer else self.player.toggle_tracklist()),
            ('l',       'Toggle lyrics',       self.toggle_lyrics),
            ('m',       'Toggle miniplayer',   self.toggle_miniplayer),
            ('q',       'Quit',                self.close),
            ('?',       'Show shortcuts',      self.show_help),
        ]
        for key, _, callback in self.keybindings:
            shortcut = QShortcut(QKeySequence(key), self)
            # Only suppress in search bar
            shortcut.activated.connect(
                lambda cb=callback: cb() if not isinstance(
                    self.focusWidget(), QLineEdit) else None)

    def _seek_relative(self, seconds):
        if self.player.current_track and self.player.playback.active:
            pos = self.player.playback.curr_pos + seconds
            pos = max(0, min(pos, self.player.current_track.length))
            self.player.playback.seek(pos)
            self.player.progress_bar.setValue(
                int((pos / self.player.current_track.length) * 1000))
            self.player.track_progress_label.setText(
                self.player.current_track.length_to_string(pos))

    def _adjust_volume(self, delta):
        if self.player.playback.active:
            vol = self.player.playback.volume + delta
            self.player.playback.set_volume(max(0, min(1, vol)))

    def show_help(self):
        t = self.current_theme
        dialog = QDialog(self)
        dialog.setWindowTitle('Keyboard Shortcuts')
        dialog.setStyleSheet(f"""
            QDialog {{ background-color: {t['bg']}; }}
            QLabel {{ color: {t['fg']}; font-family: {theme.FONT}; font-size: 12pt; }}
        """)
        layout = QVBoxLayout()
        rows = ''.join(
            f'<tr><td style="padding: 4px 20px 4px 0;"><b>{key}</b></td>'
            f'<td style="padding: 4px 0;">{desc}</td></tr>'
            for key, desc, _ in self.keybindings
        )
        label = QLabel(f'<table>{rows}</table>')
        label.setTextFormat(Qt.RichText)
        layout.addWidget(label)
        dialog.setLayout(layout)
        dialog.exec_()

    def toggle_lyrics(self):
        if self.is_miniplayer:
            self._toggle_mini_lyrics()
        else:
            self.lyrics_widget.setVisible(not self.lyrics_widget.isVisible())

    def _on_track_changed(self, track):
        """Fetch lyrics when the track changes."""
        if not self.player.album:
            return
        path = lyrics_path_for_track(track, self.player.album)

        # Already cached on disk
        if path.exists():
            self.lyrics_widget.set_lyrics(path.read_text(encoding='utf-8'))
            return

        # Already tried and failed for this track
        track_key = f'{track.artist}:{track.title}:{track.album}'
        if track_key in self._failed_lyrics:
            self.lyrics_widget.set_lyrics('')
            return

        self.lyrics_widget.set_lyrics('Fetching lyrics...')
        self._lyrics_thread = LyricsFetchThread(
            track.artist, track.title, track.album, track, self.player.album
        )
        self._lyrics_thread.finished.connect(self._on_lyrics_fetched)
        self._lyrics_thread.start()

    def _on_lyrics_fetched(self, file_path, text):
        if text:
            self.lyrics_widget.set_lyrics(text)
        else:
            track = self.player.current_track
            if track:
                self._failed_lyrics.add(f'{track.artist}:{track.title}:{track.album}')
            self.lyrics_widget.set_lyrics('')

    def _update_lyrics_position(self):
        """Feed current playback position to lyrics widget for sync."""
        if self.player.playback.playing and self.lyrics_widget.isVisible():
            self.lyrics_widget.update_position(self.player.playback.curr_pos)

    def toggle_miniplayer(self):
        if self.is_miniplayer:
            self.exit_miniplayer()
        else:
            self.enter_miniplayer()

    def _toggle_mini_lyrics(self):
        vis = not self.lyrics_widget.isVisible()
        self.lyrics_widget.setVisible(vis)
        self._mini_lyrics_btn.setChecked(vis)
        # Resize window to accommodate lyrics
        if vis:
            self.lyrics_widget.setMinimumHeight(350)
            self.resize(self.width(), self.height() + 450)
        else:
            self.lyrics_widget.setMinimumHeight(0)
            self.resize(self.width(), 400)

    def enter_miniplayer(self):
        if self.is_miniplayer:
            return
        self.is_miniplayer = True

        # Save current state for restoration
        self._pre_mini_geometry = self.saveGeometry()
        self._pre_mini_splitter = self.splitter.saveState()
        self._pre_mini_right_splitter = self.right_splitter.saveState()
        self._pre_mini_library = self.folder_view.isVisible()
        self._pre_mini_tracklist = self.album_view.isVisible()
        self._pre_mini_lyrics = self.lyrics_widget.isVisible()

        # Hide side panels and menu bar
        self.folder_view.setVisible(False)
        self.album_view.setVisible(False)
        self.right_splitter.setVisible(False)
        self.menuBar().setVisible(False)

        # Move lyrics widget into player layout for miniplayer
        self.lyrics_widget.setVisible(False)
        self.player.layout_player.addWidget(self.lyrics_widget)

        # Add lyrics toggle button to player button row
        from PyQt5.QtWidgets import QPushButton
        self._mini_lyrics_btn = QPushButton('\u266A')  # musical note
        self._mini_lyrics_btn.setObjectName('lyrics-toggle-btn')
        self._mini_lyrics_btn.setCheckable(True)
        self._mini_lyrics_btn.setChecked(False)
        self._mini_lyrics_btn.pressed.connect(self._toggle_mini_lyrics)
        self.player.layout_player_buttons.addWidget(self._mini_lyrics_btn)

        # Hide non-essential player widgets
        self.player.toggle_library_btn.setVisible(False)
        self.player.toggle_folder_btn.setVisible(False)
        self.player.track_progress_label.setVisible(False)
        self.player.track_length_label.setVisible(False)
        self.player.progress_widget.setVisible(False)

        # Reduce minimum sizes
        self.player.setMinimumSize(200, 250)
        self.setMinimumSize(280, 320)

        # Restyle for compact mode
        self.apply_theme(self.current_theme)

        # Resize to compact
        self.resize(320, 400)

        # Stay on top
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.show()

    def exit_miniplayer(self):
        if not self.is_miniplayer:
            return
        self.is_miniplayer = False

        # Remove stay on top
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()

        # Remove mini lyrics button
        if hasattr(self, '_mini_lyrics_btn'):
            self.player.layout_player_buttons.removeWidget(self._mini_lyrics_btn)
            self._mini_lyrics_btn.deleteLater()
            del self._mini_lyrics_btn

        # Move lyrics widget back to right splitter
        self.right_splitter.addWidget(self.lyrics_widget)

        # Restore minimum sizes
        self.setMinimumSize(800, 600)
        self.player.setMinimumSize(350, 500)

        # Show everything
        self.menuBar().setVisible(True)
        self.player.toggle_library_btn.setVisible(True)
        self.player.toggle_folder_btn.setVisible(True)
        self.player.track_progress_label.setVisible(True)
        self.player.track_length_label.setVisible(True)
        self.player.progress_widget.setVisible(True)

        # Restore side panels
        self.right_splitter.setVisible(True)
        self.folder_view.setVisible(self._pre_mini_library)
        self.album_view.setVisible(self._pre_mini_tracklist)
        self.lyrics_widget.setVisible(self._pre_mini_lyrics)
        self.player.toggle_library_btn.setChecked(self._pre_mini_library)
        self.player.toggle_folder_btn.setChecked(self._pre_mini_tracklist)

        # Restyle for normal mode
        self.apply_theme(self.current_theme)

        # Restore geometry
        if self._pre_mini_geometry:
            self.restoreGeometry(self._pre_mini_geometry)
            self.splitter.restoreState(self._pre_mini_splitter)
            self.right_splitter.restoreState(self._pre_mini_right_splitter)

    def closeEvent(self, event):
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('splitter', self.splitter.saveState())
        self.settings.setValue('right_splitter', self.right_splitter.saveState())
        self.settings.setValue('dark_mode', 'true' if self.current_theme is theme.DARK else 'false')
        self.settings.setValue('font_size', self.font_size)
        self.settings.setValue('accent_color', self.accent_color)
        self.settings.setValue('lyrics_visible', 'true' if self.lyrics_widget.isVisible() else 'false')
        self.settings.setValue('miniplayer', 'true' if self.is_miniplayer else 'false')
        if self.album_view.album and self.album_view.album.path:
            self.settings.setValue('last_album', self.album_view.album.path)
        if self.player.current_track:
            self.settings.setValue('last_track_pos', self.player.track_pos)
            self.settings.setValue('last_seek_pos', self.player.playback.curr_pos)
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app_ui = App()
    app_ui.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
