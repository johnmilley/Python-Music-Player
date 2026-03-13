# App contains Player, Album View, and FolderView widgets

import sys
from pathlib import Path

# local
from folder_view import FolderView
from player import Player
from album_view import AlbumView
from lyrics_widget import LyricsWidget
from lyrics_fetcher import LyricsFetchThread, lyrics_path_for_track
from color_extract import extract_palette, most_readable, text_color_for, ensure_contrast
import theme

from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout,
    QAction, QActionGroup, QSplitter, QColorDialog, QShortcut, QDialog,
    QVBoxLayout, QLabel, QLineEdit, QSizePolicy, QFileDialog, QGraphicsDropShadowEffect,
    QWidgetAction, QPushButton, QFontDialog)
from PyQt5.QtCore import Qt, QSettings, QTimer
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
        self.player.art_clicked.connect(self.toggle_maxplayer)

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

        # Font picker
        self.font_action = QAction('Font...', self)
        self.font_action.triggered.connect(self._pick_font)
        self.prefs_menu.addAction(self.font_action)

        # Menu bar — Theme
        self.colour_menu = self.menuBar().addMenu('Theme')
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

        # Max mode state
        self.is_maxplayer = False
        self._max_widget = None

        # Theme setup
        self.current_theme = theme.LIGHT
        self.apply_theme(self.current_theme)

        self.album_view.album_changed.connect(self.setWindowTitle)
        self.album_view.album_changed.connect(lambda _: self._update_accent_for_album())
        self.album_view.album_changed.connect(lambda _: QTimer.singleShot(0, self._fit_right_splitter))

        # Restore saved state
        self.settings = QSettings('lp', 'music-player')
        self._restore_state()

        # Set player buttons to NoFocus so Tab skips them
        for w in [self.player.prev_track_button, self.player.play_button,
                  self.player.next_track_button, self.player.toggle_library_btn,
                  self.player.toggle_folder_btn, self.player.progress_bar]:
            w.setFocusPolicy(Qt.NoFocus)
        self.lyrics_widget.setFocusPolicy(Qt.NoFocus)
        self.lyrics_widget.label.setFocusPolicy(Qt.NoFocus)
        self.lyrics_widget.scroll.setFocusPolicy(Qt.NoFocus)
        self.lyrics_widget.seek_requested.connect(self._on_lyrics_seek)

        # Focus change tracking for pane highlighting
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

        # Tab key cycles between folder view and album view
        self.folder_view.view.installEventFilter(self)
        self.album_view.track_list_widget.installEventFilter(self)

        # Keyboard shortcuts
        self._setup_shortcuts()

    def apply_theme(self, t):
        self.current_theme = t
        # Override accent/selection with user's chosen color
        t = dict(t)
        t['accent'] = self.accent_color
        t['selection'] = self.accent_color
        t['selection_text'] = text_color_for(self.accent_color)
        fs = self.font_size
        self.setStyleSheet(theme.app_qss(t, fs))
        self.player.setStyleSheet(theme.player_qss(t, fs))
        folder_focused = self.folder_view.view.hasFocus()
        album_focused = self.album_view.track_list_widget.hasFocus()
        self.folder_view.setStyleSheet(theme.folder_view_qss(t, fs, focused=folder_focused))
        self.album_view.setStyleSheet(theme.album_view_qss(t, fs, focused=album_focused))
        self.album_view.track_list_widget._selection_text_color = t['selection_text']
        self.lyrics_widget.setStyleSheet(theme.lyrics_qss(t, fs))
        self.lyrics_widget.set_theme(t, fs)
        self.right_splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: transparent; height: 6px; }}"
            f"QSplitter::handle:hover {{ background-color: {t['accent']}; }}"
        )

    def toggle_theme(self):
        new_theme = theme.DARK if self.current_theme is theme.LIGHT else theme.LIGHT
        # Ensure accent is readable against the new background
        self.accent_color = ensure_contrast(self.accent_color, new_theme['bg'])
        self.apply_theme(new_theme)
        # Refresh colour menu so Dark/Light label stays in sync
        album_colors = []
        if self.player.album and self.player.album.art:
            album_colors = extract_palette(str(self.player.album.art))
        self._populate_accent_menu(album_colors)

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

    def _pick_font(self):
        """Open system font dialog and apply the chosen font."""
        from PyQt5.QtGui import QFont
        current = QFont(theme.FONT.split("'")[1] if "'" in theme.FONT else 'Consolas')
        font, ok = QFontDialog.getFont(current, self, 'Pick Font')
        if ok:
            family = font.family()
            theme.FONT = f"'{family}'"
            self.apply_theme(self.current_theme)

    def pick_custom_accent(self):
        color = QColorDialog.getColor(QColor(self.accent_color), self, 'Pick Accent Color')
        if color.isValid():
            self.set_accent(color.name())

    _FUN_COLOURS = ['#ff6f61', '#e8557a', '#5ba4cf', '#2bbbad', '#f0c040']

    def _populate_accent_menu(self, album_colors):
        """Rebuild the colour menu with theme toggle, album swatches, and presets."""
        self.colour_menu.clear()
        # Light/Dark toggle
        current = getattr(self, 'current_theme', theme.LIGHT)
        theme_action = QAction('Dark Mode' if current is theme.LIGHT else 'Light Mode', self)
        theme_action.triggered.connect(self.toggle_theme)
        self.colour_menu.addAction(theme_action)
        self.colour_menu.addSeparator()
        # Album colours
        if album_colors:
            self._add_colour_section('Album', album_colors)
            self.colour_menu.addSeparator()
        # Preset colours
        self._add_colour_section('Presets', self._FUN_COLOURS)
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
        t['selection_text'] = text_color_for(self.accent_color)
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
        saved_font = self.settings.value('font_family')
        if saved_font:
            theme.FONT = f"'{saved_font}'"
        if self.settings.value('dark_mode') == 'true':
            self.apply_theme(theme.DARK)
        else:
            self.apply_theme(self.current_theme)
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
            ('1',       'Toggle library',      self._toggle_and_focus_library),
            ('2',       'Toggle tracklist',    self._toggle_and_focus_tracklist),
            ('3',       'Toggle lyrics',       self.toggle_lyrics),
            ('/',       'Search',              self._open_search),
            ('Shift+M', 'Toggle max mode',    self.toggle_maxplayer),
            ('Shift+D', 'Toggle dark/light',   self.toggle_theme),
            ('Ctrl++',  'Increase font size',  lambda: self._step_font_size(1)),
            ('Ctrl+-',  'Decrease font size',  lambda: self._step_font_size(-1)),
            ('Ctrl+=',  None,                  lambda: self._step_font_size(1)),
            ('q',       'Quit',                self.close),
            ('?',       'Show shortcuts',      self.show_help),
        ]
        # These keys are shown in help but handled by eventFilter/views, not QShortcut
        self._display_bindings = self.keybindings + [
            ('Tab',     'Switch pane',         None),
            ('j / k',   'Navigate down / up',  None),
            ('h / l',   'Folder: collapse / expand; Tracklist: go to library', None),
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

    def _on_lyrics_seek(self, seconds):
        """Seek to a timestamp when a lyrics line is clicked."""
        if self.player.current_track and self.player.playback.active:
            seconds = max(0, min(seconds, self.player.current_track.length))
            self.player.playback.seek(seconds)
            self.player.progress_bar.setValue(
                int((seconds / self.player.current_track.length) * 1000))
            self.player.track_progress_label.setText(
                self.player.current_track.length_to_string(seconds))
            self.player._update_time_label(seconds)

    def _adjust_volume(self, delta):
        if self.player.playback.active:
            vol = self.player.playback.volume + delta
            self.player.playback.set_volume(max(0, min(1, vol)))

    def eventFilter(self, obj, event):
        """Intercept Tab and vim keys for pane navigation."""
        if event.type() == event.KeyPress and not isinstance(self.focusWidget(), QLineEdit):
            key = event.key()
            if key == Qt.Key_Tab:
                self._cycle_pane_focus()
                return True
            # h/l on album tracklist → switch to folder view
            if obj is self.album_view.track_list_widget and key in (Qt.Key_H, Qt.Key_L):
                if not self.folder_view.isVisible():
                    self.player.toggle_library()
                self.folder_view.view.setFocus()
                return True
            if obj is self.folder_view.view:
                idx = self.folder_view.view.currentIndex()
                # l on a music directory → load album and switch to tracklist
                if key == Qt.Key_L and idx.isValid():
                    path = self.folder_view.model.filePath(idx)
                    if self.folder_view._has_music(path):
                        self.album_view.load_album_listing(path)
                        if not self.album_view.isVisible():
                            self.player.toggle_tracklist()
                        self.album_view.track_list_widget.setFocus()
                        return True
                # h at top level → switch to tracklist
                if key == Qt.Key_H:
                    root = self.folder_view.view.rootIndex()
                    at_top = not idx.isValid() or (not self.folder_view.view.isExpanded(idx)
                                                   and idx.parent() == root)
                    if at_top:
                        if not self.album_view.isVisible():
                            self.player.toggle_tracklist()
                        self.album_view.track_list_widget.setFocus()
                        return True
        return super().eventFilter(obj, event)

    def _toggle_and_focus_library(self):
        """Toggle library panel and focus it if shown."""
        if self.is_maxplayer:
            return
        self.player.toggle_library()
        if self.folder_view.isVisible():
            self.folder_view.view.setFocus()
        elif self.album_view.isVisible():
            self.album_view.track_list_widget.setFocus()

    def _toggle_and_focus_tracklist(self):
        """Toggle tracklist panel and focus it if shown."""
        if self.is_maxplayer:
            return
        self.player.toggle_tracklist()
        if self.album_view.isVisible():
            self.album_view.track_list_widget.setFocus()
        elif self.folder_view.isVisible():
            self.folder_view.view.setFocus()

    def _open_search(self):
        """Open the search bar of the focused pane (folder view by default)."""
        if self.album_view.track_list_widget.hasFocus():
            bar = self.album_view.search_bar
        else:
            bar = self.folder_view.search_bar
        bar.setVisible(True)
        bar.setFocus()
        bar.clear()

    def _cycle_pane_focus(self):
        """Toggle focus between folder view and album view."""
        if self.folder_view.view.hasFocus():
            self.album_view.track_list_widget.setFocus()
        else:
            self.folder_view.view.setFocus()

    def _on_focus_changed(self, old, new):
        """Update pane highlighting when focus changes."""
        self._apply_pane_styles()

    def _apply_pane_styles(self):
        """Re-apply view stylesheets based on which pane has focus."""
        t = dict(self.current_theme)
        t['accent'] = self.accent_color
        t['selection'] = self.accent_color
        t['selection_text'] = text_color_for(self.accent_color)
        fs = self.font_size
        folder_focused = self.folder_view.view.hasFocus()
        album_focused = self.album_view.track_list_widget.hasFocus()
        self.folder_view.setStyleSheet(theme.folder_view_qss(t, fs, focused=folder_focused))
        self.album_view.setStyleSheet(theme.album_view_qss(t, fs, focused=album_focused))
        # Store selection text color for the delegate
        self.album_view.track_list_widget._selection_text_color = t['selection_text']
        # Force re-polish so child widgets pick up the new stylesheet immediately
        for view in (self.folder_view.view, self.album_view.track_list_widget):
            view.style().unpolish(view)
            view.style().polish(view)
            view.viewport().update()

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
            for key, desc, _ in self._display_bindings if desc
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
        else:
            self.lyrics_widget.setVisible(not self.lyrics_widget.isVisible())

    def _toggle_max_lyrics(self):
        if not self._max_lyrics or not self._max_art:
            return
        self._max_lyrics.setVisible(not self._max_lyrics.isVisible())
        # Re-apply style so lyrics render at the correct max-mode font size
        if self._max_lyrics.isVisible():
            self._style_max_mode()
        # Re-scale art after layout settles
        from PyQt5.QtCore import QTimer as QT
        QT.singleShot(0, lambda: self._set_max_art(self._max_art_pixmap)
                       if self._max_art and hasattr(self, '_max_art_pixmap') else None)

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
        self._lyrics_track_key = track_key
        self._lyrics_thread = LyricsFetchThread(
            track.artist, track.title, track.album, track, self.player.album
        )
        self._lyrics_thread.finished.connect(self._on_lyrics_fetched)
        self._lyrics_thread.start()

    def _on_lyrics_fetched(self, file_path, text):
        # Verify this result is still for the current track (race condition guard)
        current = self.player.current_track
        if current:
            current_key = f'{current.artist}:{current.title}:{current.album}'
            if current_key != self._lyrics_track_key:
                return

        if text:
            self.lyrics_widget.set_lyrics(text)
            if self.is_maxplayer and self._max_lyrics:
                self._max_lyrics.set_lyrics(text)
        else:
            if current:
                self._failed_lyrics.add(self._lyrics_track_key)
            self.lyrics_widget.set_lyrics('')
            if self.is_maxplayer and self._max_lyrics:
                self._max_lyrics.set_lyrics('')

    def _update_lyrics_position(self):
        """Feed current playback position to lyrics widget for sync."""
        if self.player.playback.playing:
            if self.lyrics_widget.isVisible():
                self.lyrics_widget.update_position(self.player.playback.curr_pos)
            self._update_max_mode()

    def toggle_maxplayer(self):
        if self.is_maxplayer:
            self.exit_maxplayer()
        else:
            self.enter_maxplayer()

    def enter_maxplayer(self):
        if self.is_maxplayer:
            return
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
        self._max_info.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._update_max_info()
        max_layout.addWidget(self._max_info)

        # Content: art (2/3) + lyrics (1/3), lyrics height matches art
        content = QWidget()
        content.setObjectName('max-content')
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

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
        content_layout.addWidget(self._max_art, stretch=2)

        # Lyrics — constrained to art height, vertically centered
        self._max_lyrics = LyricsWidget()
        self._max_lyrics.setObjectName('max-lyrics')
        self._max_lyrics.seek_requested.connect(self._on_lyrics_seek)
        # Copy current lyrics content
        if self.lyrics_widget._synced_lines:
            lrc_text = '\n'.join(
                f'[{int(ts//60):02d}:{ts%60:05.2f}] {line}'
                for ts, line in self.lyrics_widget._synced_lines
            )
            self._max_lyrics.set_lyrics(lrc_text)
        else:
            self._max_lyrics.set_lyrics(self.lyrics_widget.label.text())
        self._max_lyrics.setVisible(True)
        content_layout.addWidget(self._max_lyrics, stretch=1)

        content.setLayout(content_layout)
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
        t['selection_text'] = text_color_for(self.accent_color)
        fs = self.font_size
        self._max_widget.setStyleSheet(f"""
            #max-mode {{
                background-color: {t['bg']};
            }}
            #max-content {{
                background-color: {t['bg']};
            }}
            #max-info {{
                background-color: {t['bg']};
                color: {t['fg']};
                font-family: {theme.FONT};
                font-size: {fs + 6}pt;
                font-weight: bold;
                padding: 15px;
                border-bottom: 2px solid {t['accent']};
            }}
        """)
        self._max_lyrics.setStyleSheet(f"""
            #lyrics-widget, #max-lyrics {{
                background-color: {t['bg']};
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
                padding: 0px 60px 0px 20px;
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
            self._max_info.setText('      '.join(parts))
        elif self.player.album:
            self._max_info.setText(
                f'{self.player.album.artist}      {self.player.album.title}')
        else:
            self._max_info.setText('lp')

    def _fit_right_splitter(self):
        """Size the right splitter so lyrics sit just below the tracklist."""
        if self.is_maxplayer or not self.lyrics_widget.isVisible():
            return
        tw = self.album_view.track_list_widget
        # Calculate total height needed for all items
        track_h = 0
        for row in range(tw.count()):
            track_h += tw.sizeHintForRow(row)
        # Add search bar height if visible, plus layout margins
        margins = self.album_view.layout().contentsMargins()
        track_h += margins.top() + margins.bottom()
        if self.album_view.search_bar.isVisible():
            track_h += self.album_view.search_bar.height()

        total = self.right_splitter.height()
        track_h = min(track_h, int(total * 0.50))  # cap at 50% — lyrics get at least half
        lyrics_h = total - track_h
        if lyrics_h > 0:
            self.right_splitter.setSizes([track_h, lyrics_h])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.is_maxplayer:
            self._fit_right_splitter()
        if self.is_maxplayer and self._max_art:
            if hasattr(self, '_max_art_pixmap'):
                size = self._max_art.size()
                scaled = self._max_art_pixmap.scaled(
                    size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._max_art.setPixmap(scaled)
                # Align lyrics top/bottom with the actual displayed pixmap
                if self._max_lyrics and self._max_lyrics.isVisible():
                    art_container_h = self._max_art.height()
                    cm = self._max_art.contentsMargins()
                    inner_h = art_container_h - cm.top() - cm.bottom()
                    pix_h = scaled.height()
                    top_pad = cm.top() + max(0, (inner_h - pix_h) // 2)
                    bottom_pad = art_container_h - top_pad - pix_h
                    self._max_lyrics.scroll.setContentsMargins(0, max(0, top_pad), 0, max(0, bottom_pad))

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
        # Save font family (extract from CSS format)
        font_family = theme.FONT.strip("'\"")
        self.settings.setValue('font_family', font_family)
        self.settings.setValue('album_accents', self._album_accents)
        self.settings.setValue('lyrics_visible', 'true' if self.lyrics_widget.isVisible() else 'false')
        if self.album_view.album and self.album_view.album.path:
            self.settings.setValue('last_album', self.album_view.album.path)
        if self.player.current_track:
            self.settings.setValue('last_track_pos', self.player.track_pos)
            self.settings.setValue('last_seek_pos', self.player.playback.curr_pos)
        super().closeEvent(event)

def main():
    # HiDPI scaling — must be set before QApplication is created
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # Force Fusion style for consistent rendering across platforms.
    # Without this, Qt picks up the system GTK theme on Linux desktops
    # (e.g. Pop!_OS, GNOME), which overrides QSS colours and font sizes.
    app.setStyle('Fusion')
    theme.resolve_font()

    app.setDesktopFileName('lp')
    app_ui = App()
    app_ui.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
