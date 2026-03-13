# App contains Player, Album View, and FolderView widgets

import sys
from pathlib import Path

# local
from folder_view import FolderView
from player import Player
from album_view import AlbumView
from lyrics_widget import LyricsWidget
from lyrics_fetcher import LyricsFetchThread, lyrics_path_for_track
from color_extract import extract_palette, most_readable
import theme

from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout,
    QAction, QActionGroup, QSplitter, QColorDialog, QShortcut, QDialog,
    QVBoxLayout, QLabel, QLineEdit, QSizePolicy, QFileDialog, QGraphicsDropShadowEffect,
    QWidgetAction, QPushButton)
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
        self.player.art_clicked.connect(lambda: self.toggle_maxplayer() if not self.is_miniplayer else None)

        self.setWindowTitle("lp")
        # Support both normal and PyInstaller-bundled paths
        if getattr(sys, '_MEIPASS', None):
            icon_path = Path(sys._MEIPASS) / 'icon.png'
        else:
            icon_path = Path(__file__).parent.parent / 'icon.png'
        self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(800, 400)

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

        # Menu bar — File
        self.file_menu = self.menuBar().addMenu('File')

        self.library_action = QAction('Music Library...', self)
        self.library_action.triggered.connect(self._pick_library)
        self.file_menu.addAction(self.library_action)

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

        # Menu bar — Colour
        self.colour_menu = self.menuBar().addMenu('Colour')
        self.accent_color = theme.DEFAULT_ACCENT
        self._album_accents = {}  # album_path -> accent color
        self._populate_accent_menu([])

        # Change album art action
        self.prefs_menu.addSeparator()
        self.change_art_action = QAction('Change Album Art...', self)
        self.change_art_action.triggered.connect(self._change_album_art)
        self.prefs_menu.addAction(self.change_art_action)

        # Menu bar — Help
        self.help_menu = self.menuBar().addMenu('Help')

        self.shortcuts_action = QAction('Display Shortcuts', self)
        self.shortcuts_action.setShortcut(QKeySequence('Shift+?'))
        self.shortcuts_action.triggered.connect(self.show_help)
        self.help_menu.addAction(self.shortcuts_action)

        self.about_action = QAction('About', self)
        self.about_action.triggered.connect(self.show_about)
        self.help_menu.addAction(self.about_action)

        # Miniplayer state
        self.is_miniplayer = False
        self._pre_mini_geometry = None
        self._pre_mini_splitter = None

        # Max mode state
        self.is_maxplayer = False
        self._max_widget = None

        # Theme setup
        self.current_theme = theme.LIGHT
        self.apply_theme(self.current_theme)

        self.album_view.album_changed.connect(self.setWindowTitle)
        self.album_view.album_changed.connect(lambda _: self._update_accent_for_album())

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
        self.lyrics_widget.set_theme(t, fs)
        self.right_splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: transparent; height: 6px; }}"
            f"QSplitter::handle:hover {{ background-color: {t['accent']}; }}"
        )

    def toggle_theme(self):
        if self.current_theme is theme.LIGHT:
            self.apply_theme(theme.DARK)
        else:
            self.apply_theme(theme.LIGHT)

    def set_font_size(self, size):
        self.font_size = size
        self.apply_theme(self.current_theme)
        # Keep menu checkmark in sync
        for action in self.font_size_group.actions():
            if action.data() == size:
                action.setChecked(True)
                break

    def _step_font_size(self, delta):
        sizes = theme.FONT_SIZES
        try:
            idx = sizes.index(self.font_size)
        except ValueError:
            idx = sizes.index(theme.DEFAULT_FONT_SIZE)
        idx = max(0, min(len(sizes) - 1, idx + delta))
        self.set_font_size(sizes[idx])

    def set_accent(self, color):
        self.accent_color = color
        # Save per-album preference
        if self.player.album and self.player.album.path:
            self._album_accents[self.player.album.path] = color
        self.apply_theme(self.current_theme)

    def pick_custom_accent(self):
        color = QColorDialog.getColor(QColor(self.accent_color), self, 'Pick Accent Color')
        if color.isValid():
            self.set_accent(color.name())

    _FUN_COLOURS = ['#ff6f61', '#e8557a', '#5ba4cf', '#2bbbad', '#f0c040']

    def _populate_accent_menu(self, album_colors):
        """Rebuild the colour menu with album swatches and fun colours."""
        self.colour_menu.clear()
        if album_colors:
            self._add_colour_section('Album', album_colors)
            self.colour_menu.addSeparator()
        self._add_colour_section(None, self._FUN_COLOURS)
        self.colour_menu.addSeparator()
        custom_action = QAction('Custom...', self)
        custom_action.triggered.connect(self.pick_custom_accent)
        self.colour_menu.addAction(custom_action)

    def _add_colour_section(self, label, colors):
        if label:
            header = QAction(label, self)
            header.setEnabled(False)
            self.colour_menu.addAction(header)
        for c in colors:
            wa = QWidgetAction(self)
            btn = QPushButton()
            btn.setFixedSize(140, 28)
            border = '2px solid white' if c == self.accent_color else 'none'
            btn.setStyleSheet(
                f'QPushButton {{ background: {c}; border: {border}; }}'
                f'QPushButton:hover {{ border: 2px solid white; }}'
            )
            btn.clicked.connect(lambda checked, color=c: (self.set_accent(color), self.colour_menu.close()))
            wa.setDefaultWidget(btn)
            self.colour_menu.addAction(wa)

    def _update_accent_for_album(self, force=False):
        """Extract palette from album art and update accent menu."""
        if not self.player.album or not self.player.album.art:
            return
        album_path = self.player.album.path
        # Skip if we already extracted for this album
        if not force and getattr(self, '_last_palette_album', None) == album_path:
            return
        self._last_palette_album = album_path
        colors = extract_palette(str(self.player.album.art))
        if not colors:
            return
        # Restore saved accent for this album, or pick most readable
        if album_path in self._album_accents:
            self.accent_color = self._album_accents[album_path]
        else:
            default = most_readable(colors) or colors[0]
            self.accent_color = default
            self._album_accents[album_path] = default
        self._populate_accent_menu(colors)
        self.apply_theme(self.current_theme)

    def _pick_library(self):
        """Let user pick the root music library folder."""
        current = self.settings.value('library_root', '')
        path = QFileDialog.getExistingDirectory(
            self, 'Select Music Library Folder', current)
        if path:
            self.folder_view.set_root(path)
            self.settings.setValue('library_root', path)

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
        dialog.artwork_saved.connect(lambda _: self._update_accent_for_album(force=True))
        dialog.exec_()

    def _color_icon(self, color, width=120, height=24):
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(color))
        return QIcon(pixmap)

    def _restore_state(self):
        library_root = self.settings.value('library_root')
        if library_root:
            self.folder_view.set_root(library_root)
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
        saved_album_accents = self.settings.value('album_accents')
        if saved_album_accents and isinstance(saved_album_accents, dict):
            self._album_accents = saved_album_accents
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
        # Update accent palette from restored album art
        if self.player.album and self.player.album.art:
            self._update_accent_for_album()

    def _setup_shortcuts(self):
        self.keybindings = [
            ('p',       'Play / Pause',       self.player.toggle_play_pause_button_text),
            ('>',       'Next track',          self.player.next_track),
            ('<',       'Previous track',      self.player.prev_track),
            ('f',       'Seek forward 5s',     lambda: self._seek_relative(5)),
            ('b',       'Seek back 5s',        lambda: self._seek_relative(-5)),
            ('.',       'Volume up',           lambda: self._adjust_volume(0.05)),
            (',',       'Volume down',         lambda: self._adjust_volume(-0.05)),
            ('1',       'Toggle library',      lambda: None if self.is_maxplayer else (self.exit_miniplayer() if self.is_miniplayer else self.player.toggle_library())),
            ('2',       'Toggle tracklist',    lambda: None if self.is_maxplayer else (self.exit_miniplayer() if self.is_miniplayer else self.player.toggle_tracklist())),
            ('3',       'Toggle lyrics',       self.toggle_lyrics),
            ('l',       None,                  self.toggle_lyrics),
            ('m',       'Toggle miniplayer',   lambda: None if self.is_maxplayer else self.toggle_miniplayer()),
            ('Shift+M', 'Toggle max mode',    lambda: None if self.is_miniplayer else self.toggle_maxplayer()),
            ('Ctrl++',  'Increase font size',  lambda: self._step_font_size(1)),
            ('Ctrl+-',  'Decrease font size',  lambda: self._step_font_size(-1)),
            ('Ctrl+=',  None,                  lambda: self._step_font_size(1)),
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
        def esc(s):
            return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        rows = ''.join(
            f'<tr><td style="padding: 4px 20px 4px 0;"><b>{esc(key)}</b></td>'
            f'<td style="padding: 4px 0;">{esc(desc)}</td></tr>'
            for key, desc, _ in self.keybindings if desc
        )
        label = QLabel(f'<table>{rows}</table>')
        label.setTextFormat(Qt.RichText)
        layout.addWidget(label)
        dialog.setLayout(layout)
        dialog.exec_()

    def show_about(self):
        t = self.current_theme
        dialog = QDialog(self)
        dialog.setWindowTitle('About lp')
        dialog.setStyleSheet(f"""
            QDialog {{ background-color: {t['bg']}; }}
            QLabel {{ color: {t['fg']}; font-family: {theme.FONT}; font-size: 12pt; }}
        """)
        layout = QVBoxLayout()
        label = QLabel(
            '<div style="text-align: center;">'
            '<h2>lp</h2>'
            '<p>Version 0.5</p>'
            '<p>By Johnathan Milley</p>'
            '<p>Licensed under the MIT License</p>'
            '</div>'
        )
        label.setTextFormat(Qt.RichText)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        dialog.setLayout(layout)
        dialog.exec_()

    def toggle_lyrics(self):
        if self.is_maxplayer:
            self._toggle_max_lyrics()
        elif self.is_miniplayer:
            self._toggle_mini_lyrics()
        else:
            self.lyrics_widget.setVisible(not self.lyrics_widget.isVisible())

    def _toggle_max_lyrics(self):
        if not self._max_lyrics or not self._max_art:
            return
        self._max_lyrics.setVisible(not self._max_lyrics.isVisible())
        # Re-scale art to fit new available space
        if hasattr(self, '_max_art_pixmap'):
            from PyQt5.QtCore import QTimer as QT
            QT.singleShot(0, lambda: self._set_max_art(self._max_art_pixmap) if self._max_art else None)

    def _on_track_changed(self, track):
        """Fetch lyrics when the track changes."""
        # Update max mode if active
        if self.is_maxplayer:
            self._update_max_info()
            if self._max_art and self.player.album and self.player.album.art:
                self._set_max_art(QPixmap(str(self.player.album.art)))

        if not self.player.album:
            return
        path = lyrics_path_for_track(track, self.player.album)

        # Already cached on disk
        if path.exists():
            text = path.read_text(encoding='utf-8')
            self.lyrics_widget.set_lyrics(text)
            if self.is_maxplayer and self._max_lyrics:
                self._max_lyrics.set_lyrics(text)
            return

        # Already tried and failed for this track
        track_key = f'{track.artist}:{track.title}:{track.album}'
        if track_key in self._failed_lyrics:
            self.lyrics_widget.set_lyrics('')
            if self.is_maxplayer and self._max_lyrics:
                self._max_lyrics.set_lyrics('')
            return

        self.lyrics_widget.set_lyrics('Fetching lyrics...')
        if self.is_maxplayer and self._max_lyrics:
            self._max_lyrics.set_lyrics('Fetching lyrics...')
        # Stop any in-progress fetch before starting a new one
        if self._lyrics_thread and self._lyrics_thread.isRunning():
            self._lyrics_thread.finished.disconnect(self._on_lyrics_fetched)
            self._lyrics_thread.quit()
            self._lyrics_thread.wait(2000)
        self._lyrics_thread = LyricsFetchThread(
            track.artist, track.title, track.album, track, self.player.album
        )
        self._lyrics_thread.finished.connect(self._on_lyrics_fetched)
        self._lyrics_thread.start()

    def _on_lyrics_fetched(self, file_path, text):
        if text:
            self.lyrics_widget.set_lyrics(text)
            if self.is_maxplayer and self._max_lyrics:
                self._max_lyrics.set_lyrics(text)
        else:
            track = self.player.current_track
            if track:
                self._failed_lyrics.add(f'{track.artist}:{track.title}:{track.album}')
            self.lyrics_widget.set_lyrics('')
            if self.is_maxplayer and self._max_lyrics:
                self._max_lyrics.set_lyrics('')

    def _update_lyrics_position(self):
        """Feed current playback position to lyrics widget for sync."""
        if self.player.playback.playing:
            if self.lyrics_widget.isVisible():
                self.lyrics_widget.update_position(self.player.playback.curr_pos)
            self._update_max_mode()

    def toggle_miniplayer(self):
        if self.is_miniplayer:
            self.exit_miniplayer()
        else:
            self.enter_miniplayer()

    def _toggle_mini_lyrics(self):
        vis = not self.lyrics_widget.isVisible()
        self._mini_lyrics_btn.setChecked(vis)
        # Resize window to accommodate lyrics
        if vis:
            self.lyrics_widget.setMinimumHeight(350)
            self.lyrics_widget.setVisible(True)
            self.resize(self.width(), self.height() + 450)
        else:
            lyrics_h = self.lyrics_widget.height()
            self.lyrics_widget.setMinimumHeight(0)
            self.lyrics_widget.setVisible(False)
            self.resize(self.width(), self.height() - lyrics_h)

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
        self.lyrics_widget.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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
        self.lyrics_widget.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.right_splitter.addWidget(self.lyrics_widget)

        # Restore minimum sizes
        self.setMinimumSize(800, 400)
        self.player.setMinimumSize(350, 300)

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

    def toggle_maxplayer(self):
        if self.is_maxplayer:
            self.exit_maxplayer()
        else:
            self.enter_maxplayer()

    def enter_maxplayer(self):
        if self.is_maxplayer:
            return
        # Exit miniplayer first if active
        if self.is_miniplayer:
            self.exit_miniplayer()
        self.is_maxplayer = True

        # Save state
        self._pre_max_geometry = self.saveGeometry()
        self._pre_max_splitter = self.splitter.saveState()
        self._pre_max_right_splitter = self.right_splitter.saveState()
        self._pre_max_library = self.folder_view.isVisible()
        self._pre_max_tracklist = self.album_view.isVisible()
        self._pre_max_lyrics = self.lyrics_widget.isVisible()

        # Hide normal UI
        self.splitter.setVisible(False)
        self.menuBar().setVisible(False)

        # Build max mode widget
        self._max_widget = QWidget()
        self._max_widget.setObjectName('max-mode')
        max_layout = QVBoxLayout()
        max_layout.setContentsMargins(0, 0, 0, 0)
        max_layout.setSpacing(0)

        # Top bar: Artist - Album - Track
        self._max_info = QLabel()
        self._max_info.setObjectName('max-info')
        self._max_info.setAlignment(Qt.AlignCenter)
        self._max_info.setWordWrap(True)
        self._update_max_info()
        max_layout.addWidget(self._max_info)

        # Content: large art (left) + large lyrics (right)
        content = QSplitter(Qt.Horizontal)
        content.setObjectName('max-splitter')

        # Album art — large, scaled
        self._max_art = QLabel()
        self._max_art.setAlignment(Qt.AlignCenter)
        self._max_art.setContentsMargins(20, 20, 20, 20)
        self._max_art.setMinimumSize(300, 300)
        self._max_art.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._max_art.setCursor(Qt.PointingHandCursor)
        self._max_art.mousePressEvent = lambda e: self.toggle_maxplayer() if e.button() == Qt.LeftButton else None
        max_shadow = QGraphicsDropShadowEffect(self)
        max_shadow.setBlurRadius(40)
        max_shadow.setOffset(6, 6)
        max_shadow.setColor(QColor(0, 0, 0, 180))
        self._max_art.setGraphicsEffect(max_shadow)
        if self.player.album and self.player.album.art:
            self._set_max_art(QPixmap(str(self.player.album.art)))
        content.addWidget(self._max_art)

        # Lyrics — large font
        self._max_lyrics = LyricsWidget()
        self._max_lyrics.setObjectName('max-lyrics')
        # Copy current lyrics content
        if self.lyrics_widget._synced_lines:
            # Re-render synced lyrics
            lrc_text = '\n'.join(
                f'[{int(ts//60):02d}:{ts%60:05.2f}] {line}'
                for ts, line in self.lyrics_widget._synced_lines
            )
            self._max_lyrics.set_lyrics(lrc_text)
        else:
            self._max_lyrics.set_lyrics(self.lyrics_widget.label.text())
        content.addWidget(self._max_lyrics)

        content.setStretchFactor(0, 3)
        content.setStretchFactor(1, 2)
        self._max_content = content

        max_layout.addWidget(content, stretch=1)
        self._max_widget.setLayout(max_layout)

        self.layout_app.addWidget(self._max_widget)

        # Apply theme to max mode
        self._style_max_mode()

        # Go fullscreen
        self.showFullScreen()

    def _style_max_mode(self):
        t = dict(self.current_theme)
        t['accent'] = self.accent_color
        t['selection'] = self.accent_color
        fs = self.font_size
        self._max_widget.setStyleSheet(f"""
            #max-mode {{
                background-color: {t['bg']};
            }}
            #max-info {{
                background-color: {t['bg']};
                color: {t['fg']};
                font-family: {theme.FONT};
                font-size: {fs + 6}pt;
                padding: 15px;
                border-bottom: 2px solid {t['accent']};
            }}
            QSplitter::handle {{
                background-color: transparent;
                width: 6px;
            }}
            QSplitter::handle:hover {{
                background-color: {t['accent']};
            }}
        """)
        self._max_lyrics.setStyleSheet(f"""
            #lyrics-widget, #max-lyrics {{
                background-color: {t['bg']};
                padding: 20px;
            }}
            #lyrics-scroll {{
                background-color: {t['bg']};
                border: none;
            }}
            #lyrics-text {{
                background-color: {t['bg']};
                color: {t['fg']};
                font-family: {theme.FONT};
                font-size: {fs + 8}pt;
            }}
        """)
        self._max_lyrics.set_theme(t, fs + 8)

    def _set_max_art(self, pixmap):
        """Set max mode art scaled to fit without stretching."""
        if pixmap.isNull():
            return
        size = self._max_art.size()
        scaled = pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._max_art.setPixmap(scaled)
        self._max_art_pixmap = pixmap  # keep original for resize

    def _update_max_info(self):
        if not hasattr(self, '_max_info'):
            return
        track = self.player.current_track
        if track:
            parts = [p for p in [track.artist, track.album, track.title] if p]
            self._max_info.setText('  \u2014  '.join(parts))
        elif self.player.album:
            self._max_info.setText(
                f'{self.player.album.artist}  \u2014  {self.player.album.title}')
        else:
            self._max_info.setText('lp')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.is_maxplayer and self._max_art and hasattr(self, '_max_art_pixmap'):
            size = self._max_art.size()
            scaled = self._max_art_pixmap.scaled(
                size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._max_art.setPixmap(scaled)

    def _update_max_mode(self):
        """Update max mode lyrics and info on timer tick."""
        if not self.is_maxplayer:
            return
        if self.player.playback.playing:
            self._max_lyrics.update_position(self.player.playback.curr_pos)

    def exit_maxplayer(self):
        if not self.is_maxplayer:
            return
        self.is_maxplayer = False

        # Remove max widget
        if self._max_widget:
            self.layout_app.removeWidget(self._max_widget)
            self._max_widget.deleteLater()
            self._max_widget = None
            self._max_lyrics = None
            self._max_art = None
            self._max_info = None

        # Restore normal UI
        self.splitter.setVisible(True)
        self.menuBar().setVisible(True)

        # Restore side panels
        self.folder_view.setVisible(self._pre_max_library)
        self.album_view.setVisible(self._pre_max_tracklist)
        self.lyrics_widget.setVisible(self._pre_max_lyrics)
        self.player.toggle_library_btn.setChecked(self._pre_max_library)
        self.player.toggle_folder_btn.setChecked(self._pre_max_tracklist)

        # Restyle
        self.apply_theme(self.current_theme)

        # Exit fullscreen and restore geometry
        self.showNormal()
        if self._pre_max_geometry:
            self.restoreGeometry(self._pre_max_geometry)
            self.splitter.restoreState(self._pre_max_splitter)
            self.right_splitter.restoreState(self._pre_max_right_splitter)

    def closeEvent(self, event):
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('splitter', self.splitter.saveState())
        self.settings.setValue('right_splitter', self.right_splitter.saveState())
        self.settings.setValue('dark_mode', 'true' if self.current_theme is theme.DARK else 'false')
        self.settings.setValue('font_size', self.font_size)
        self.settings.setValue('accent_color', self.accent_color)
        self.settings.setValue('album_accents', self._album_accents)
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
    app.setDesktopFileName('lp')
    app_ui = App()
    app_ui.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
