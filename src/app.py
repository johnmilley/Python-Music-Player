# App — main window orchestrator
# Creates all widgets, wires signals between them, and manages:
#   - Three display modes: music, podcast, radio (see _set_mode)
#   - Two view modes: normal (splitter layout) and max (fullscreen art + lyrics)
#   - Theming: light/dark with per-album accent colors
#   - Keyboard shortcuts and media key handling
#   - Session persistence (window state, playback position, settings)

import sys
from pathlib import Path

# local
from folder_view import FolderView
from player import Player
from album_view import AlbumView
from lyrics_widget import LyricsWidget
from lyrics_fetcher import LyricsFetchThread, lyrics_path_for_track
from color_extract import extract_palette, most_readable, text_color_for, ensure_contrast, PaletteExtractThread
from podcast_view import PodcastView
from podcast_feed import PodcastFeed, EpisodeDownloadThread, ImageDownloadThread
from radio_view import RadioView
from radio_player import _make_radio_player, StationArtDialog, station_art_path
from radio_station import RadioStation
from media_keys import MediaKeyHandler, start_native_backend
import theme

from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout,
    QAction, QSplitter, QColorDialog, QShortcut, QDialog, QMenu,
    QVBoxLayout, QLabel, QLineEdit, QListWidgetItem, QSizePolicy, QFileDialog,
    QGraphicsDropShadowEffect, QPushButton, QFontDialog, QToolButton)
from PyQt5.QtCore import Qt, QEvent, QSettings, QTimer, QSize
from PyQt5.QtGui import QColor, QPixmap, QIcon, QKeySequence


class _HoverRevealBar(QWidget):
    """Widget that hides child text until hovered — solid accent when idle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered = False
        self._bg_color = None
        self._fg_color = None
        self._accent_color = None

    def set_colors(self, accent, bg, fg):
        self._accent_color = accent
        self._bg_color = bg
        self._fg_color = fg
        self._apply_colors()

    def _apply_colors(self):
        if self._hovered:
            # Reveal: normal bg, accent text
            self.setStyleSheet(f'#menu-bar {{ background-color: {self._bg_color}; }}')
            for child in self.findChildren(QToolButton):
                child.setStyleSheet(f'color: {self._accent_color};')
        else:
            # Hidden: accent bg, accent text (invisible)
            self.setStyleSheet(f'#menu-bar {{ background-color: {self._accent_color}; }}')
            for child in self.findChildren(QToolButton):
                child.setStyleSheet(f'color: {self._accent_color};')

    def enterEvent(self, event):
        self._hovered = True
        self._apply_colors()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._apply_colors()
        super().leaveEvent(event)


class ToolBar(QWidget):
    """Two-row toolbar: menu bar on top, accent separator, toggle bar below."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('toolbar')

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setLayout(outer)

        # Top row: menu buttons — solid accent, text revealed on hover
        self._menu_bar = _HoverRevealBar()
        self._menu_bar.setObjectName('menu-bar')
        self._menu_layout = QHBoxLayout()
        self._menu_layout.setContentsMargins(4, 0, 4, 0)
        self._menu_layout.setSpacing(0)
        self._menu_bar.setLayout(self._menu_layout)
        outer.addWidget(self._menu_bar)

        # Accent separator
        self._accent_bar = QWidget()
        self._accent_bar.setObjectName('accent-bar')
        self._accent_bar.setFixedHeight(2)
        outer.addWidget(self._accent_bar)

        # Bottom row: mode toggles + panel toggles
        self._toggle_bar = QWidget()
        self._toggle_bar.setObjectName('toggle-bar')
        self._toggle_layout = QHBoxLayout()
        self._toggle_layout.setContentsMargins(4, 0, 4, 0)
        self._toggle_layout.setSpacing(0)
        self._toggle_bar.setLayout(self._toggle_layout)
        outer.addWidget(self._toggle_bar)

        self.update_heights(theme.DEFAULT_FONT_SIZE)

    def update_heights(self, fs):
        """Resize bars to fit the given font size."""
        menu_h = 15  # fixed small height, independent of font size
        toggle_h = fs + 14
        self._menu_bar.setFixedHeight(menu_h)
        self._toggle_bar.setFixedHeight(toggle_h)
        self.setFixedHeight(menu_h + 2 + toggle_h)

    def addWidget(self, widget):
        self._toggle_layout.addWidget(widget)

    def addStretch(self):
        self._toggle_layout.addStretch()

    def addMenuWidget(self, widget):
        self._menu_layout.addWidget(widget)

    def addMenuStretch(self):
        self._menu_layout.addStretch()

    def add_menu_button(self, text, menu):
        """Create a QToolButton that opens the given QMenu on click."""
        btn = QToolButton()
        btn.setText(text)
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setObjectName('menu-button')
        return btn


class App(QMainWindow):
    """Main application window — owns all widgets and wires them together.

    Layout (normal mode):
        ToolBar
        QSplitter: [left_panel | player | album_view | lyrics_widget]

    Left panel swaps by mode: folder_view (music), podcast_view, radio_view.
    Max mode replaces everything with fullscreen art + lyrics.
    """

    def __init__(self, media_signals=None, media_backend=None):
        super().__init__()
        self._media_signals = media_signals
        self._media_backend = media_backend
        self._was_inactive = True  # suppress click-through on first focus

        self.app_widget = QWidget()
        self.app_widget.setObjectName('main-window')

        self.player = Player()
        self.album_view = AlbumView()
        self.lyrics_widget = LyricsWidget()
        self.folder_view = FolderView(self.album_view)
        self.podcast_view = PodcastView()
        self.radio_view = RadioView()
        self.radio_player = _make_radio_player()

        # Mode: 'music', 'podcast', or 'radio'
        self._mode = 'music'
        self._playing_mode = None  # mode of last actual playback
        self._controls_mode = 'music'  # current button/controls layout
        self._playing_album_path = None  # album path of last actual music playback
        self._playing_track_pos = 0
        self._playing_seek_pos = 0
        self._download_threads = {}  # episode guid -> EpisodeDownloadThread
        self._download_play_guid = None  # guid of episode to auto-play when done
        self._image_thread = None
        self._current_podcast_feed = None
        self._current_radio_station = None
        self._episode_positions = {}  # guid -> seek position, loaded after settings init

        # Player and AlbumView coupling
        self.player.album_view = self.album_view
        self.player.folder_view = self.folder_view
        self.album_view.player = self.player

        # Podcast signals
        self.podcast_view.feed_selected.connect(self._on_podcast_feed_selected)

        # Radio signals
        self.radio_view.station_selected.connect(self._on_station_selected)
        self.radio_view.art_requested.connect(
            lambda s: self._pick_station_art_for(s))
        self.radio_player.metadata_changed.connect(self._on_radio_metadata)
        self._radio_now_playing = ''

        # Lyrics fetching and sync
        self._lyrics_thread = None
        self._failed_lyrics = set()  # track paths with no results
        self.player.track_changed.connect(self._on_track_changed)
        self.player.timer.timeout.connect(self._update_lyrics_position)
        self.player.art_clicked.connect(self._on_art_clicked)

        self.setWindowTitle("lp")
        # Support both normal and PyInstaller-bundled paths
        if getattr(sys, '_MEIPASS', None):
            icon_path = Path(sys._MEIPASS) / 'icon.png'
        else:
            icon_path = Path(__file__).parent.parent / 'icon.png'
        self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(600, 350)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName('main-splitter')
        self.splitter.addWidget(self.folder_view)
        self.splitter.addWidget(self.podcast_view)
        self.podcast_view.setVisible(False)
        self.splitter.addWidget(self.radio_view)
        self.radio_view.setVisible(False)
        self.splitter.addWidget(self.player)
        self.splitter.addWidget(self.album_view)
        self.splitter.addWidget(self.lyrics_widget)
        self.splitter.setStretchFactor(0, 2)  # folder view
        self.splitter.setStretchFactor(1, 2)  # podcast view
        self.splitter.setStretchFactor(2, 2)  # radio view
        self.splitter.setStretchFactor(3, 3)  # player
        self.splitter.setStretchFactor(4, 2)  # album/tracklist
        self.splitter.setStretchFactor(5, 2)  # lyrics
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setCollapsible(2, False)
        self.splitter.setCollapsible(3, False)
        self.splitter.setCollapsible(4, False)
        self.splitter.setCollapsible(5, False)

        self.layout_app = QVBoxLayout()
        self.layout_app.setContentsMargins(0, 0, 0, 0)
        self.layout_app.setSpacing(0)
        self.layout_app.addWidget(self.splitter)
        self.app_widget.setLayout(self.layout_app)

        self.setCentralWidget(self.app_widget)

        self.settings = QSettings('lp', 'music-player')
        self._episode_positions = self.settings.value('podcast/episode_positions', {}) or {}

        # Hide the native menu bar — we use a custom hover menu bar instead
        self.menuBar().setVisible(False)

        # Hover menu bar — accent strip + toolbar shown on hover
        self.toolbar_widget = ToolBar(self)
        hm = self.toolbar_widget

        # Left: mode toggle buttons
        self.mode_music_btn = QToolButton()
        self.mode_music_btn.setText('MUSIC')
        self.mode_music_btn.setToolTip('Music mode (1)')
        self.mode_music_btn.setCheckable(True)
        self.mode_music_btn.setChecked(True)
        self.mode_music_btn.setObjectName('mode-toggle')
        self.mode_music_btn.clicked.connect(lambda: self._set_mode('music'))

        self.mode_podcast_btn = QToolButton()
        self.mode_podcast_btn.setText('PODCASTS')
        self.mode_podcast_btn.setToolTip('Podcast mode (2)')
        self.mode_podcast_btn.setCheckable(True)
        self.mode_podcast_btn.setObjectName('mode-toggle')
        self.mode_podcast_btn.clicked.connect(lambda: self._set_mode('podcast'))

        self.mode_radio_btn = QToolButton()
        self.mode_radio_btn.setToolTip('Radio mode (3)')
        self.mode_radio_btn.setCheckable(True)
        self.mode_radio_btn.setObjectName('mode-toggle')
        self.mode_radio_btn.clicked.connect(lambda: self._set_mode('radio'))

        # Menu bar: Preferences, Theme, Help (top row)
        self.font_size = theme.DEFAULT_FONT_SIZE

        self.prefs_menu = QMenu('Preferences', self)
        self.font_action = QAction('Font...', self)
        self.font_action.triggered.connect(self._pick_font)
        self.prefs_menu.addAction(self.font_action)
        self.change_art_action = QAction('Change Album Art...', self)
        self.change_art_action.triggered.connect(self._change_album_art)
        self.prefs_menu.addAction(self.change_art_action)
        self.prefs_menu.addSeparator()
        self.library_action = QAction('Music Library...', self)
        self.library_action.triggered.connect(self._pick_library)
        self.prefs_menu.addAction(self.library_action)
        hm.addMenuWidget(hm.add_menu_button('Preferences', self.prefs_menu))

        self.colour_menu = QMenu('Theme', self)
        self.accent_color = theme.DEFAULT_ACCENT
        self._album_accents = {}
        self._accent_match = self.settings.value('accent_match', 'true') == 'true'
        self._populate_accent_menu([])
        hm.addMenuWidget(hm.add_menu_button('Theme', self.colour_menu))

        self.help_menu = QMenu('Help', self)
        self.shortcuts_action = QAction('Display Shortcuts', self)
        self.shortcuts_action.setShortcut(QKeySequence('Shift+?'))
        self.shortcuts_action.triggered.connect(self.show_help)
        self.help_menu.addAction(self.shortcuts_action)
        self.about_action = QAction('About', self)
        self.about_action.triggered.connect(self.show_about)
        self.help_menu.addAction(self.about_action)
        hm.addMenuWidget(hm.add_menu_button('Help', self.help_menu))
        hm.addMenuStretch()

        # Toggle bar: mode buttons (left) + panel toggles (right)
        hm.addWidget(self.mode_music_btn)
        hm.addWidget(self.mode_podcast_btn)
        hm.addWidget(self.mode_radio_btn)
        hm.addStretch()

        # Right: panel toggle buttons
        self.toggle_tracklist_btn = QToolButton()
        self.toggle_tracklist_btn.setText('TRACKLIST')
        self.toggle_tracklist_btn.setToolTip('Toggle Tracklist (4)')
        self.toggle_tracklist_btn.setCheckable(True)
        self.toggle_tracklist_btn.setChecked(True)
        self.toggle_tracklist_btn.setObjectName('panel-toggle')
        self.toggle_tracklist_btn.clicked.connect(self._on_toggle_tracklist)

        self.toggle_lyrics_btn = QToolButton()
        self.toggle_lyrics_btn.setText('LYRICS')
        self.toggle_lyrics_btn.setToolTip('Toggle Lyrics (5)')
        self.toggle_lyrics_btn.setCheckable(True)
        self.toggle_lyrics_btn.setChecked(True)
        self.toggle_lyrics_btn.setObjectName('panel-toggle')
        self.toggle_lyrics_btn.clicked.connect(self._on_toggle_lyrics)

        hm.addWidget(self.toggle_tracklist_btn)
        hm.addWidget(self.toggle_lyrics_btn)

        # Insert hover menu bar at top of layout
        self.layout_app.insertWidget(0, self.toolbar_widget)

        # Max mode state
        self.is_maxplayer = False
        self._max_widget = None

        # Theme setup
        self.current_theme = theme.LIGHT
        self.apply_theme(self.current_theme)

        self.album_view.album_changed.connect(self._on_album_changed)

        # Restore saved state
        self._restore_state()

        # Set player buttons and toggle buttons to NoFocus so Tab skips them
        for w in [self.player.prev_track_button, self.player.play_button,
                  self.player.next_track_button, self.player.progress_bar,
                  self.toggle_tracklist_btn, self.toggle_lyrics_btn,
                  self.mode_music_btn, self.mode_podcast_btn, self.mode_radio_btn]:
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

        # Media keys (play/pause, next, prev — global when possible)
        self._media_keys = MediaKeyHandler(self, self._media_signals, self._media_backend)
        self._media_keys.signals.play_pause.connect(self._shortcut_play_pause)
        self._media_keys.signals.next_track.connect(self._shortcut_next)
        self._media_keys.signals.prev_track.connect(self._shortcut_prev)
        self._media_keys.signals.stop.connect(
            lambda: self.player.playback.stop() if self.player.playback.active else None)

    # ── Theme & Styling ────────────────────────────────────────────

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
        self.player.update_button_icons(t['fg'], hover_color=t['accent'])
        folder_focused = self.folder_view.view.hasFocus()
        album_focused = self.album_view.track_list_widget.hasFocus()
        self.folder_view.setStyleSheet(theme.folder_view_qss(t, fs, focused=folder_focused))
        self.album_view.setStyleSheet(theme.album_view_qss(t, fs, focused=album_focused))
        self.album_view.track_list_widget._selection_text_color = t['selection_text']
        self.toolbar_widget.setStyleSheet(theme.hover_menu_qss(t, fs))
        self.toolbar_widget.update_heights(fs)
        self.toolbar_widget._menu_bar.set_colors(t['accent'], t['bg'], t['fg'])
        self.mode_radio_btn.setText('RADIO')
        self.lyrics_widget.setStyleSheet(theme.lyrics_qss(t, fs))
        self.lyrics_widget.set_theme(t, fs)
        self.podcast_view.setStyleSheet(theme.podcast_view_qss(t, fs))
        self.radio_view.setStyleSheet(theme.radio_view_qss(t, fs))

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
        """Open system font dialog and apply the chosen font and size."""
        from PyQt5.QtGui import QFont
        current = QFont(theme.FONT.split("'")[1] if "'" in theme.FONT else 'Consolas')
        current.setPointSize(self.font_size)
        font, ok = QFontDialog.getFont(current, self, 'Pick Font')
        if ok:
            theme.FONT = f"'{font.family()}'"
            min_fs, max_fs = theme.FONT_SIZES[0], theme.FONT_SIZES[-1]
            self.font_size = max(min_fs, min(max_fs, font.pointSize()))
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
        accent_match_action = QAction('Accent Match', self)
        accent_match_action.setCheckable(True)
        accent_match_action.setChecked(self._accent_match)
        accent_match_action.triggered.connect(self._toggle_accent_match)
        self.colour_menu.addAction(accent_match_action)
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
            action = QAction(self._color_icon(c), c, self)
            if c == self.accent_color:
                action.setCheckable(True)
                action.setChecked(True)
            action.triggered.connect(lambda checked, color=c: self.set_accent(color))
            self.colour_menu.addAction(action)

    def _toggle_accent_match(self, checked):
        self._accent_match = checked
        self.settings.setValue('accent_match', 'true' if checked else 'false')
        if checked:
            self._update_accent_for_album(force=True)

    def _update_accent_for_album(self, force=False):
        """Extract palette from album art and update accent menu."""
        if not self._accent_match:
            return
        if not self.player.album or not self.player.album.art:
            return
        album_path = self.player.album.path
        # Skip if we already extracted for this album
        if not force and getattr(self, '_last_palette_album', None) == album_path:
            return
        self._last_palette_album = album_path
        # If we have a saved accent, apply it immediately (no extraction needed)
        if album_path in self._album_accents:
            self.accent_color = self._album_accents[album_path]
            self.apply_theme(self.current_theme)
        # Extract palette in background thread
        self._palette_thread = PaletteExtractThread(str(self.player.album.art))
        self._palette_thread.finished.connect(
            lambda colors, p=album_path: self._on_palette_extracted(colors, p))
        self._palette_thread.start()

    def _on_palette_extracted(self, colors, album_path):
        """Handle palette extraction results from background thread."""
        if not colors:
            return
        if album_path not in self._album_accents:
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

    # ── Session Persistence ─────────────────────────────────────────

    def _restore_state(self):
        library_root = self.settings.value('library_root')
        if library_root:
            self.folder_view.set_root(library_root)
            self.folder_view.model.directoryLoaded.connect(
                lambda: QTimer.singleShot(100, self._auto_fit_folder_width))
            self.folder_view.view.expanded.connect(
                lambda: QTimer.singleShot(100, self._auto_fit_folder_width))
            self.folder_view.view.collapsed.connect(
                lambda: QTimer.singleShot(100, self._auto_fit_folder_width))
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
        splitter_state = self.settings.value('splitter')
        if splitter_state:
            self.splitter.restoreState(splitter_state)
        if self.settings.value('library_visible') == 'false':
            self.folder_view.setVisible(False)
            self.podcast_view.setVisible(False)
            self.radio_view.setVisible(False)
        if self.settings.value('tracklist_visible') == 'false':
            self.album_view.setVisible(False)
            self.toggle_tracklist_btn.setChecked(False)
        if self.settings.value('lyrics_visible') == 'false':
            self.lyrics_widget.setVisible(False)
            self.toggle_lyrics_btn.setChecked(False)
        saved_fs = self.settings.value('font_size', type=int)
        if saved_fs:
            min_fs, max_fs = theme.FONT_SIZES[0], theme.FONT_SIZES[-1]
            self.font_size = max(min_fs, min(max_fs, saved_fs))
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
        # Restore app mode
        saved_mode = self.settings.value('app_mode', 'music')
        if saved_mode == 'podcast':
            self._set_mode('podcast')
            self._restore_podcast_state()
        elif saved_mode == 'radio':
            self._set_mode('radio')
            self._restore_radio_state()
        else:
            # Ensure other views are hidden when restoring music mode
            self.podcast_view.setVisible(False)
            self.radio_view.setVisible(False)
            self.folder_view.setVisible(self.settings.value('library_visible') != 'false')
            # Restore last music album
            last_album = self.settings.value('last_album')
            if last_album and Path(last_album).is_dir():
                track_pos = self.settings.value('last_track_pos', 0, type=int)
                seek_pos = self.settings.value('last_seek_pos', 0.0, type=float)
                self._pending_music_restore = {'track_pos': track_pos, 'seek_pos': seek_pos}
                self.album_view.load_album_listing(last_album)

    # ── Keyboard Shortcuts & Input ───────────────────────────────────

    def _shortcut_play_pause(self):
        if self._playing_mode == 'radio':
            self._radio_toggle_play_pause()
        else:
            self.player.toggle_play_pause_button_text()

    def _shortcut_next(self):
        if self._playing_mode == 'radio':
            return
        if self._playing_mode == 'podcast':
            self._seek_relative(30)
        else:
            self.player.next_track()

    def _shortcut_prev(self):
        if self._playing_mode == 'radio':
            return
        if self._playing_mode == 'podcast':
            self._seek_relative(-30)
        else:
            self.player.prev_track()

    def _shortcut_seek_forward(self):
        if self._playing_mode == 'radio':
            return
        self._seek_relative(5)

    def _shortcut_seek_back(self):
        if self._playing_mode == 'radio':
            return
        self._seek_relative(-5)

    def _setup_shortcuts(self):
        self.keybindings = [
            ('p',       'Play / Pause',       self._shortcut_play_pause),
            ('>',       'Next / +30s',         self._shortcut_next),
            ('<',       'Previous / -30s',     self._shortcut_prev),
            ('f',       'Seek forward 5s',     self._shortcut_seek_forward),
            ('b',       'Seek back 5s',        self._shortcut_seek_back),
            ('.',       'Volume up',           lambda: self._adjust_volume(0.05)),
            (',',       'Volume down',         lambda: self._adjust_volume(-0.05)),
            ('1',       'Music mode',           lambda: self._set_mode('music')),
            ('2',       'Podcast mode',        lambda: self._set_mode('podcast')),
            ('3',       'Radio mode',          lambda: self._set_mode('radio')),
            ('4',       'Toggle tracklist',    self._toggle_and_focus_tracklist),
            ('5',       'Toggle lyrics',       self.toggle_lyrics),
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

    def changeEvent(self, event):
        """Track when window loses focus for click-through prevention."""
        if event.type() == QEvent.ActivationChange:
            if not self.isActiveWindow():
                self._was_inactive = True
        super().changeEvent(event)

    def keyPressEvent(self, event):
        """Handle key presses — dispatch shortcuts in max mode."""
        if self.is_maxplayer:
            key = event.key()
            mods = event.modifiers()
            if key == Qt.Key_Escape:
                self.toggle_maxplayer()
                return
            if key == Qt.Key_M and mods & Qt.ShiftModifier:
                self.toggle_maxplayer()
                return
            if key == Qt.Key_D and mods & Qt.ShiftModifier:
                self.toggle_theme()
                return
            # Map single keys to shortcuts
            _max_keys = {
                Qt.Key_P: self._shortcut_play_pause,
                Qt.Key_Greater: self._shortcut_next,
                Qt.Key_Less: self._shortcut_prev,
                Qt.Key_F: self._shortcut_seek_forward,
                Qt.Key_B: self._shortcut_seek_back,
                Qt.Key_Period: lambda: self._adjust_volume(0.05),
                Qt.Key_Comma: lambda: self._adjust_volume(-0.05),
                Qt.Key_3: self.toggle_lyrics,
                Qt.Key_Q: self.close,
                Qt.Key_Question: self.show_help,
            }
            handler = _max_keys.get(key)
            if handler:
                handler()
                return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        """Intercept Tab/vim keys and suppress click-through on refocus."""
        t = event.type()
        # Click-through prevention: swallow first click that refocuses the window
        if self._was_inactive and t in (QEvent.MouseButtonPress,
                                         QEvent.MouseButtonDblClick):
            self._was_inactive = False
            self.activateWindow()
            return True
        if t == event.KeyPress and not isinstance(self.focusWidget(), QLineEdit):
            key = event.key()
            if key == Qt.Key_Tab:
                self._cycle_pane_focus()
                return True
            # h/l on album tracklist → switch to folder view
            if obj is self.album_view.track_list_widget and key in (Qt.Key_H, Qt.Key_L):
                if not self.folder_view.isVisible():
                    self.toggle_library()
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
                            self.toggle_tracklist()
                        self.album_view.track_list_widget.setFocus()
                        return True
                # h at top level → switch to tracklist
                if key == Qt.Key_H:
                    root = self.folder_view.view.rootIndex()
                    at_top = not idx.isValid() or (not self.folder_view.view.isExpanded(idx)
                                                   and idx.parent() == root)
                    if at_top:
                        if not self.album_view.isVisible():
                            self.toggle_tracklist()
                        self.album_view.track_list_widget.setFocus()
                        return True
        return super().eventFilter(obj, event)

    def _toggle_and_focus_library(self):
        """Toggle library panel and focus it if shown."""
        if self.is_maxplayer:
            return
        self.toggle_library()
        if self._mode == 'podcast' and self.podcast_view.isVisible():
            self.podcast_view.feed_list.setFocus()
        elif self._mode == 'radio' and self.radio_view.isVisible():
            self.radio_view.station_list.setFocus()
        elif self.folder_view.isVisible():
            self.folder_view.view.setFocus()
        elif self.album_view.isVisible():
            self.album_view.track_list_widget.setFocus()

    def _toggle_and_focus_tracklist(self):
        """Toggle tracklist panel and focus it if shown."""
        if self.is_maxplayer:
            return
        self.toggle_tracklist()
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
        items = [(key, desc) for key, desc, _ in self._display_bindings if desc]
        mid = (len(items) + 1) // 2
        col1 = items[:mid]
        col2 = items[mid:]
        rows = ''
        for i in range(max(len(col1), len(col2))):
            k1, d1 = col1[i] if i < len(col1) else ('', '')
            k2, d2 = col2[i] if i < len(col2) else ('', '')
            rows += (
                f'<tr>'
                f'<td style="padding: 4px 16px 4px 0;"><b>{esc(k1)}</b></td>'
                f'<td style="padding: 4px 0;">{esc(d1)}</td>'
                f'<td style="padding: 4px 16px 4px 40px;"><b>{esc(k2)}</b></td>'
                f'<td style="padding: 4px 0;">{esc(d2)}</td>'
                f'</tr>'
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

    # ── Panel Visibility & Layout ────────────────────────────────────

    def _on_toggle_library(self, checked):
        if self._mode == 'podcast':
            lib = self.podcast_view
        elif self._mode == 'radio':
            lib = self.radio_view
        else:
            lib = self.folder_view
        self._toggle_library_panel(lib, checked)

    def _toggle_library_panel(self, lib_widget, show):
        """Toggle library panel, taking/giving space from right panels."""
        sizes = self.splitter.sizes()
        lib_idx = self.splitter.indexOf(lib_widget)
        # Collect visible right panels to steal from / give to
        right_indices = []
        for w in (self.album_view, self.lyrics_widget):
            if w.isVisible():
                right_indices.append(self.splitter.indexOf(w))
        if show:
            if right_indices:
                # Take space proportionally from visible right panels
                total_right = sum(sizes[i] for i in right_indices)
                take = total_right // 2
                # Distribute the reduction proportionally
                for i in right_indices:
                    share = int(take * sizes[i] / total_right) if total_right else 0
                    sizes[i] -= share
                sizes[lib_idx] = take
            else:
                # Fall back: take from player
                player_idx = self.splitter.indexOf(self.player)
                player_min = self.player.minimumSizeHint().width() or 200
                available = max(0, sizes[player_idx] - player_min)
                sizes[player_idx] -= available
                sizes[lib_idx] = available
            lib_widget.setVisible(True)
            self.splitter.setSizes(sizes)
        else:
            freed = sizes[lib_idx]
            if right_indices:
                # Give space back to right panels proportionally
                total_right = sum(sizes[i] for i in right_indices)
                for i in right_indices:
                    share = int(freed * sizes[i] / total_right) if total_right else freed // len(right_indices)
                    sizes[i] += share
            else:
                sizes[self.splitter.indexOf(self.player)] += freed
            sizes[lib_idx] = 0
            lib_widget.setVisible(False)
            self.splitter.setSizes(sizes)

    def _on_toggle_tracklist(self, checked):
        self._toggle_panel(self.album_view, checked)

    def _on_toggle_lyrics(self, checked):
        if self.is_maxplayer:
            self._toggle_max_lyrics()
        else:
            self._toggle_panel(self.lyrics_widget, checked)

    def _toggle_panel(self, widget, show):
        """Toggle a panel, redistributing space to minimize empty area."""
        sizes = self.splitter.sizes()
        idx = self.splitter.indexOf(widget)
        player_idx = self.splitter.indexOf(self.player)
        player_min = self.player.minimumSizeHint().width() or 200

        # Determine if this is a right-side panel (tracklist or lyrics)
        right_panels = {self.album_view, self.lyrics_widget}
        is_right = widget in right_panels
        other = (right_panels - {widget}).pop() if is_right else None
        other_idx = self.splitter.indexOf(other) if other else None
        other_visible = other.isVisible() if other else False

        if show:
            if is_right and other_visible:
                # Split the other right panel's space equally
                total = sizes[other_idx]
                half = total // 2
                sizes[other_idx] = total - half
                sizes[idx] = half
            else:
                # Take space from the player
                available = max(0, sizes[player_idx] - player_min)
                sizes[player_idx] -= available
                sizes[idx] = available
            widget.setVisible(True)
            self.splitter.setSizes(sizes)
        else:
            if is_right and other_visible:
                # Give this panel's space to the other right panel
                sizes[other_idx] += sizes[idx]
            else:
                # Return the panel's space to the player
                sizes[player_idx] += sizes[idx]
            sizes[idx] = 0
            widget.setVisible(False)
            self.splitter.setSizes(sizes)

    def toggle_library(self):
        if self._mode == 'podcast':
            lib = self.podcast_view
        elif self._mode == 'radio':
            lib = self.radio_view
        else:
            lib = self.folder_view
        vis = not lib.isVisible()
        self._toggle_library_panel(lib, vis)

    def _on_album_changed(self, title):
        """Single handler for album changes — batches all updates."""
        self.setWindowTitle(title)
        self._update_accent_for_album()
        self._show_tracklist()
        # Restore saved track position after startup album load
        pending = getattr(self, '_pending_music_restore', None)
        if pending:
            del self._pending_music_restore
            track_pos = pending['track_pos']
            seek_pos = pending['seek_pos']
            if self.album_view.album and track_pos < len(self.album_view.album.tracklist):
                self.player.load_track(self.album_view.album, track_pos, seek_pos)

    def _show_tracklist(self):
        """Ensure the tracklist panel is visible."""
        if not self.album_view.isVisible():
            self._toggle_panel(self.album_view, True)
            self.toggle_tracklist_btn.setChecked(True)

    def toggle_tracklist(self):
        vis = not self.album_view.isVisible()
        self._toggle_panel(self.album_view, vis)
        self.toggle_tracklist_btn.setChecked(vis)

    def toggle_lyrics(self):
        if self.is_maxplayer:
            self._toggle_max_lyrics()
        else:
            vis = not self.lyrics_widget.isVisible()
            self._toggle_panel(self.lyrics_widget, vis)
            self.toggle_lyrics_btn.setChecked(vis)

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

    # ── Lyrics & Track Change Handling ─────────────────────────────

    def _on_track_changed(self, track):
        """Fetch lyrics when the track changes."""
        # Stop radio if music/podcast playback starts
        if self.radio_player.is_playing:
            self.radio_player.stop()
        # Determine playing mode from the track type, not the UI mode
        if hasattr(track, 'audio_url'):
            track_mode = 'podcast'
        else:
            track_mode = 'music'
        self._playing_mode = track_mode
        self._apply_controls_for_mode(track_mode)
        if track_mode == 'music' and self.player.playlist and getattr(self.player.playlist, 'path', None):
            self._playing_album_path = self.player.playlist.path
            self._playing_track_pos = self.player.playlist_pos
            self._playing_seek_pos = 0  # just started
        # Update max mode if active
        if self.is_maxplayer:
            self._update_max_info()
            if self._max_art and self.player.album and self.player.album.art:
                self._set_max_art(QPixmap(str(self.player.album.art)))

        # Podcast episodes show description instead of lyrics
        if track_mode == 'podcast' and hasattr(track, 'description'):
            self.lyrics_widget.set_description(track.description)
            if self.is_maxplayer and self._max_lyrics:
                self._copy_lyrics_to_max()
            return

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
            self._lyrics_thread.lyrics_ready.disconnect(self._on_lyrics_fetched)
            self._lyrics_thread.quit()
            self._lyrics_thread.wait(2000)
        self._lyrics_track_key = track_key
        self._lyrics_thread = LyricsFetchThread(
            track.artist, track.title, track.album, track, self.player.album
        )
        self._lyrics_thread.lyrics_ready.connect(self._on_lyrics_fetched)
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

    def _on_art_clicked(self):
        """Handle album art click — max mode for music/podcast, art picker for radio."""
        if self._mode == 'radio':
            self._pick_station_art()
        else:
            self.toggle_maxplayer()

    # ── Max Mode (Fullscreen Art + Lyrics) ─────────────────────────

    def toggle_maxplayer(self):
        try:
            if self.is_maxplayer:
                self.exit_maxplayer()
            else:
                self.enter_maxplayer()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f'LOG: Max mode error: {e}')

    def enter_maxplayer(self):
        if self.is_maxplayer:
            return
        self.is_maxplayer = True

        # Save state
        self._pre_max_geometry = self.saveGeometry()
        self._pre_max_splitter = self.splitter.saveState()
        self._pre_max_library = self.folder_view.isVisible()
        self._pre_max_tracklist = self.album_view.isVisible()
        self._pre_max_lyrics = self.lyrics_widget.isVisible()

        # Hide normal UI
        self.splitter.setVisible(False)
        self.toolbar_widget.setVisible(False)

        # Build max mode widget
        self._max_widget = QWidget()
        self._max_widget.setObjectName('max-mode')
        max_layout = QVBoxLayout()
        max_layout.setContentsMargins(0, 0, 0, 0)
        max_layout.setSpacing(0)

        # Accent divider line
        self._max_divider = QWidget()
        self._max_divider.setObjectName('max-divider')
        self._max_divider.setFixedHeight(2)
        max_layout.addWidget(self._max_divider)

        # Content: art (2/3) + lyrics (1/3)
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

        # Lyrics container — aligned with album art vertical extent
        lyrics_outer = QVBoxLayout()
        lyrics_outer.setContentsMargins(0, 0, 0, 0)
        lyrics_outer.setSpacing(0)

        # Track info header (sticky above lyrics scroll)
        self._max_track_label = QLabel()
        self._max_track_label.setObjectName('max-track-label')
        self._max_track_label.setWordWrap(True)
        self._max_track_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._update_max_info()
        lyrics_outer.addWidget(self._max_track_label)

        self._max_lyrics = LyricsWidget()
        self._max_lyrics.setObjectName('max-lyrics')
        self._max_lyrics.seek_requested.connect(self._on_lyrics_seek)
        self._copy_lyrics_to_max()
        self._max_lyrics.setVisible(True)
        lyrics_outer.addWidget(self._max_lyrics, stretch=1)

        self._max_lyrics_wrapper = QWidget()
        self._max_lyrics_wrapper.setObjectName('max-lyrics-wrapper')
        self._max_lyrics_wrapper.setLayout(lyrics_outer)
        content_layout.addWidget(self._max_lyrics_wrapper, stretch=1)

        content.setLayout(content_layout)
        self._max_content = content

        max_layout.addWidget(content, stretch=1)
        self._max_widget.setLayout(max_layout)

        self.layout_app.addWidget(self._max_widget)
        self._max_widget.setFocusPolicy(Qt.StrongFocus)
        self._max_widget.setFocus()

        # Apply theme to max mode
        self._style_max_mode()

        # Go fullscreen
        self.showFullScreen()

        # Defer art scaling so the layout settles at fullscreen size first
        # (macOS fullscreen animation delays the final resize)
        if self.player.album and self.player.album.art:
            QTimer.singleShot(150, lambda: self._set_max_art(QPixmap(str(self.player.album.art)))
                              if self._max_art else None)

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
            #max-divider {{
                background-color: {t['accent']};
            }}
            #max-lyrics-wrapper {{
                background-color: {t['bg']};
            }}
            #max-track-label {{
                background-color: {t['bg']};
                color: {t['fg']};
                font-family: {theme.FONT};
                font-size: {fs + 12}pt;
                font-weight: bold;
                padding: 8px 20px 20px 20px;
            }}
        """)
        if not self._max_lyrics:
            return
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
        """Set max mode art scaled to 75% of screen height, centered."""
        if pixmap.isNull():
            return
        screen_h = self.height()
        max_side = int(screen_h * 0.85)
        m = self._max_art.contentsMargins()
        avail_w = min(self._max_art.width() - m.left() - m.right(), max_side)
        avail_h = min(self._max_art.height() - m.top() - m.bottom(), max_side)
        avail = QSize(max(avail_w, 100), max(avail_h, 100))
        scaled = pixmap.scaled(avail, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._max_art.setPixmap(scaled)
        self._max_art_pixmap = pixmap  # keep original for resize
        # Align lyrics wrapper with the art's vertical extent
        self._align_lyrics_to_art(scaled)

    def _align_lyrics_to_art(self, scaled_pixmap):
        """Set lyrics wrapper margins so it aligns with the art vertically."""
        wrapper = getattr(self, '_max_lyrics_wrapper', None)
        if not wrapper or not self._max_art:
            return
        art_widget_h = self._max_art.height()
        art_pixmap_h = scaled_pixmap.height()
        m = self._max_art.contentsMargins()
        # The art is centered in its label: equal space above and below the pixmap
        pad_top = m.top() + (art_widget_h - m.top() - m.bottom() - art_pixmap_h) // 2
        pad_bottom = art_widget_h - pad_top - art_pixmap_h
        wrapper.setContentsMargins(0, max(pad_top, 0), 0, max(pad_bottom, 0))

    def _copy_lyrics_to_max(self):
        """Copy lyrics or podcast description from normal widget to max mode."""
        if not self._max_lyrics:
            return
        try:
            src = self.lyrics_widget
            if src._synced_lines:
                lrc_text = '\n'.join(
                    f'[{int(ts//60):02d}:{ts%60:05.2f}] {line}'
                    for ts, line in src._synced_lines
                )
                self._max_lyrics.set_lyrics(lrc_text)
            elif src._desc_segments:
                self._max_lyrics._desc_segments = src._desc_segments
                self._max_lyrics._desc_preamble = getattr(src, '_desc_preamble', None)
                self._max_lyrics._synced_lines = None
                self._max_lyrics._current_line = -1
                self._max_lyrics._render_description(-1)
            elif hasattr(src, '_full_description'):
                self._max_lyrics.set_description(src._full_description)
            else:
                plain = src.label.toPlainText() if src.label.textFormat() == Qt.RichText else src.label.text()
                self._max_lyrics.set_lyrics(plain or '')
        except Exception:
            self._max_lyrics.set_lyrics('')

    def _update_max_info(self):
        label = getattr(self, '_max_track_label', None)
        if not label:
            return
        track = self.player.current_track
        if track and track.title:
            label.setText(str(track.title))
        else:
            label.setText('')


    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.is_maxplayer and self._max_art:
            if hasattr(self, '_max_art_pixmap'):
                self._set_max_art(self._max_art_pixmap)

    def _update_max_mode(self):
        """Update max mode lyrics and info on timer tick."""
        if not self.is_maxplayer or not self._max_lyrics:
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
            self._max_lyrics_wrapper = None
            self._max_track_label = None

        # Restore normal UI
        self.splitter.setVisible(True)
        self.toolbar_widget.setVisible(True)

        # Restore side panels
        self.folder_view.setVisible(self._pre_max_library)
        self.album_view.setVisible(self._pre_max_tracklist)
        self.lyrics_widget.setVisible(self._pre_max_lyrics)
        self.toggle_tracklist_btn.setChecked(self._pre_max_tracklist)
        self.toggle_lyrics_btn.setChecked(self._pre_max_lyrics)

        # Restyle
        self.apply_theme(self.current_theme)

        # Exit fullscreen and restore geometry
        self.showNormal()
        self._was_inactive = False
        if self._pre_max_geometry:
            self.restoreGeometry(self._pre_max_geometry)
            self.splitter.restoreState(self._pre_max_splitter)
        # macOS fullscreen exit animation delays focus — retry until it sticks
        def _force_focus():
            self.raise_()
            self.activateWindow()
            self.player.setFocus()
            self._was_inactive = False
        QTimer.singleShot(200, _force_focus)
        QTimer.singleShot(500, _force_focus)
        QTimer.singleShot(1000, _force_focus)

    # ── Podcast mode ──────────────────────────────────────────────

    def _update_radio_icon(self):
        pass

    # ── Mode Switching (Music / Podcast / Radio) ────────────────────

    def _set_mode(self, mode):
        """Switch between music, podcast, and radio modes.

        Each mode swaps the left panel and adjusts player controls:
        - music:   folder_view, prev/next track buttons
        - podcast: podcast_view, ±30s seek buttons, episode download
        - radio:   radio_view, play/pause only (no seek/skip)
        """
        if mode == self._mode:
            # Same mode clicked again — toggle the library panel
            self.toggle_library()
            self.mode_music_btn.setChecked(mode == 'music')
            self.mode_podcast_btn.setChecked(mode == 'podcast')
            self.mode_radio_btn.setChecked(mode == 'radio')
            self._update_radio_icon()
            return
        self._save_music_position()
        self._save_podcast_position()
        if self._mode == 'music':
            self._save_music_folder_position()
        self._mode = mode
        self.mode_music_btn.setChecked(mode == 'music')
        self.mode_podcast_btn.setChecked(mode == 'podcast')
        self.mode_radio_btn.setChecked(mode == 'radio')
        self._update_radio_icon()

        # Hide all left panels first
        self.folder_view.setVisible(False)
        self.podcast_view.setVisible(False)
        self.radio_view.setVisible(False)

        # Restore panels if leaving radio/podcast
        pre = getattr(self, '_pre_mode_panels', None)
        if pre is not None and mode == 'music':
            self.album_view.setVisible(pre['tracklist'])
            self.toggle_tracklist_btn.setChecked(pre['tracklist'])
            self.lyrics_widget.setVisible(pre['lyrics'])
            self.toggle_lyrics_btn.setChecked(pre['lyrics'])
            self._pre_mode_panels = None

        if mode == 'podcast':
            # Save panel state and hide both
            if not hasattr(self, '_pre_mode_panels') or self._pre_mode_panels is None:
                self._pre_mode_panels = {
                    'tracklist': self.album_view.isVisible(),
                    'lyrics': self.lyrics_widget.isVisible(),
                }
            self.album_view.setVisible(False)
            self.toggle_tracklist_btn.setChecked(False)
            self.lyrics_widget.setVisible(False)
            self.toggle_lyrics_btn.setChecked(False)
            self.podcast_view.setVisible(True)
            self.podcast_view.load_saved_feeds()
        elif mode == 'radio':
            # Save panel state and hide both
            if not hasattr(self, '_pre_mode_panels') or self._pre_mode_panels is None:
                self._pre_mode_panels = {
                    'tracklist': self.album_view.isVisible(),
                    'lyrics': self.lyrics_widget.isVisible(),
                }
            self.album_view.setVisible(False)
            self.toggle_tracklist_btn.setChecked(False)
            self.lyrics_widget.setVisible(False)
            self.toggle_lyrics_btn.setChecked(False)
            self.radio_view.setVisible(True)
            self.radio_view.load_saved_stations()
        else:
            self.folder_view.setVisible(True)
            self._restore_music_folder_position()
            # Reconnect album_view click to music handler
            try:
                self.album_view.track_list_widget.itemClicked.disconnect()
            except TypeError:
                pass
            self.album_view.track_list_widget.itemClicked.connect(
                self.album_view.set_current_track)
            self.album_view.track_list_widget.setContextMenuPolicy(Qt.NoContextMenu)

    def _restore_podcast_state(self):
        """Restore the last-played podcast feed and episode on startup."""
        last_feed_url = self.settings.value('podcast/last_feed', '')
        if not last_feed_url:
            return
        self._pending_podcast_restore = {
            'feed_url': last_feed_url,
            'episode_idx': int(self.settings.value('podcast/last_episode', 0)),
            'seek_pos': float(self.settings.value('podcast/last_seek', 0)),
        }
        self._playing_mode = 'podcast'
        self._apply_controls_for_mode('podcast')
        # Tell podcast view to auto-select this feed once it loads
        self.podcast_view._auto_select_url = last_feed_url

    def _try_podcast_restore(self, feed):
        """Called after a feed loads — check if it matches the pending restore."""
        pending = getattr(self, '_pending_podcast_restore', None)
        if not pending or feed.url != pending['feed_url']:
            return
        idx = pending['episode_idx']
        seek = pending['seek_pos']
        del self._pending_podcast_restore
        if idx < len(feed.tracklist):
            ep = feed.tracklist[idx]
            if ep.is_downloaded:
                self._play_episode(feed, idx)
                if seek > 0:
                    def _do_seek():
                        if self.player.playback.active:
                            self.player.playback.seek(seek)
                    QTimer.singleShot(500, _do_seek)

    def _apply_controls_for_mode(self, mode):
        """Switch player controls to match the given mode, if not already."""
        if mode == self._controls_mode:
            return
        self._controls_mode = mode
        if mode == 'podcast':
            self._set_podcast_controls()
        elif mode == 'radio':
            self._set_radio_controls()
        else:
            self._set_music_controls()

    def _set_podcast_controls(self):
        """Switch prev/next buttons to ±30s seek for podcast mode."""
        p = self.player
        try:
            p.prev_track_button.pressed.disconnect()
            p.next_track_button.pressed.disconnect()
        except TypeError:
            pass
        p.prev_track_button.pressed.connect(lambda: self._seek_relative(-30))
        p.next_track_button.pressed.connect(lambda: self._seek_relative(30))
        color = getattr(p, '_icon_color', 'black')
        hover_color = getattr(p, '_icon_hover_color', None)
        small_bold = f'font-size: {max(self.font_size - 3, 7)}pt; font-weight: bold;'
        p._set_btn_hover_icons(p.prev_track_button, 'fast_rewind', color, hover_color)
        p.prev_track_button.setText('30s')
        p.prev_track_button.setStyleSheet(small_bold)
        p.prev_track_button.setLayoutDirection(Qt.RightToLeft)
        p._set_btn_hover_icons(p.next_track_button, 'fast_forward', color, hover_color)
        p.next_track_button.setText('30s')
        p.next_track_button.setStyleSheet(small_bold)
        p.next_track_button.setLayoutDirection(Qt.LeftToRight)
        # Restore visibility (radio mode hides these)
        p.prev_track_button.setVisible(True)
        p.next_track_button.setVisible(True)
        p.progress_bar.setVisible(True)
        p.track_progress_label.setVisible(True)
        p.track_length_label.setVisible(True)
        # Reconnect play button to just_playback
        self._reconnect_play_button()
        p.update_layout()

    def _set_radio_controls(self):
        """Hide prev/next and progress bar — only play/pause for radio."""
        p = self.player
        p.prev_track_button.setVisible(False)
        p.next_track_button.setVisible(False)
        p.progress_bar.setVisible(False)
        p.track_progress_label.setVisible(False)
        p.track_length_label.setVisible(False)
        # Reconnect play button to radio player
        try:
            p.play_button.pressed.disconnect()
        except TypeError:
            pass
        p.play_button.pressed.connect(self._radio_toggle_play_pause)
        p.update_layout()

    def _reconnect_play_button(self):
        """Reconnect play button to the standard just_playback toggle."""
        p = self.player
        try:
            p.play_button.pressed.disconnect()
        except TypeError:
            pass
        p.play_button.pressed.connect(p.toggle_play_pause_button_text)

    def _radio_toggle_play_pause(self):
        """Toggle play/pause for radio streaming."""
        if self.radio_player.is_playing:
            self.radio_player.pause()
            self.player._set_play_icon(False)
        else:
            if self._current_radio_station:
                self.radio_player.resume()
                self.player._set_play_icon(True)

    def _set_music_controls(self):
        """Restore prev/next buttons to track skip for music mode."""
        p = self.player
        try:
            p.prev_track_button.pressed.disconnect()
            p.next_track_button.pressed.disconnect()
        except TypeError:
            pass
        p.prev_track_button.pressed.connect(p.prev_track)
        p.next_track_button.pressed.connect(p.next_track)
        p.prev_track_button.setText('')
        p.next_track_button.setText('')
        p.prev_track_button.setStyleSheet('')
        p.next_track_button.setStyleSheet('')
        p.prev_track_button.setLayoutDirection(Qt.LeftToRight)
        p.next_track_button.setLayoutDirection(Qt.LeftToRight)
        p.update_button_icons()
        # Restore visibility (radio mode hides these)
        p.prev_track_button.setVisible(True)
        p.next_track_button.setVisible(True)
        p.progress_bar.setVisible(True)
        p.track_progress_label.setVisible(True)
        p.track_length_label.setVisible(True)
        # Reconnect play button to just_playback
        self._reconnect_play_button()
        p.update_layout()

    # ── Radio mode ────────────────────────────────────────────────

    def _on_station_selected(self, station):
        """Start streaming a radio station."""
        # Save positions BEFORE stopping playback (curr_pos resets to 0 on stop)
        self._save_music_position()
        self._save_podcast_position()
        self.player.playback.stop()
        self.player.timer.stop()
        self.radio_player.stop()

        # Detach shared player from music/podcast state so future
        # _save_podcast_position / _save_music_position calls don't
        # overwrite good saved positions with stale zeroed-out values.
        self.player.current_track = None
        self.player.album = None
        self.player.playlist = None

        self._playing_mode = 'radio'
        self._apply_controls_for_mode('radio')
        self._current_radio_station = station
        self._radio_now_playing = ''
        self.player.track_info.setText(station.name)
        self.player._set_play_icon(True)
        self._load_station_art(station.name)

        # Clear tracklist
        self.album_view.track_list_widget.clear()
        self.lyrics_widget.clear()

        self.radio_player.play_stream(station.stream_url)

    def _load_station_art(self, station_name):
        """Load cached station art, or fall back to the SVG placeholder."""
        art = station_art_path(station_name)
        if art.exists():
            px = QPixmap(str(art))
            if not px.isNull():
                self.player.album_widget.setPixmap(px)
                return
        self._set_radio_art()

    def _pick_station_art(self):
        """Open the station art picker dialog for the current radio station."""
        if self._current_radio_station:
            self._pick_station_art_for(self._current_radio_station)

    def _pick_station_art_for(self, station):
        """Open the station art picker dialog for any station."""
        t = dict(self.current_theme)
        t['accent'] = self.accent_color
        t['selection'] = self.accent_color
        t['selection_text'] = text_color_for(self.accent_color)
        dlg = StationArtDialog(station.name, t, parent=self)
        dlg.art_selected.connect(self._on_station_art_picked)
        dlg.exec_()

    def _on_station_art_picked(self, pixmap):
        """Display the user-chosen station art."""
        if not pixmap.isNull():
            self.player.album_widget.setPixmap(pixmap)

    def _on_radio_metadata(self, title):
        """Update now-playing display when stream metadata changes."""
        self._radio_now_playing = title
        if self._current_radio_station:
            display = f'{self._current_radio_station.name}  \u2022  {title}'
            self.player.track_info.setText(display)
            # Show now-playing in the lyrics panel (set HTML directly)
            import html as html_mod
            t = getattr(self, 'current_theme', theme.LIGHT)
            fg = t.get('fg', '#e0e0e0')
            accent = self.accent_color
            safe_title = html_mod.escape(title)
            safe_name = html_mod.escape(self._current_radio_station.name)
            self.lyrics_widget._synced_lines = None
            self.lyrics_widget._desc_segments = None
            self.lyrics_widget.label.setTextFormat(Qt.RichText)
            self.lyrics_widget.label.setText(
                f'<div style="text-align:center; padding:20px; font-family:{theme.FONT};">'
                f'<p style="font-size:14pt; color:{fg}; opacity:0.6;">Now Playing</p>'
                f'<p style="font-size:16pt; font-weight:bold; color:{accent};">{safe_title}</p>'
                f'<p style="font-size:12pt; color:{fg}; opacity:0.5;">{safe_name}</p>'
                f'</div>')

    def _set_radio_art(self):
        """Set a radio-themed visual in the album art area."""
        t = getattr(self, 'current_theme', theme.LIGHT)
        accent = t.get('accent', '#888888')
        fg = t.get('fg', '#ffffff')
        bg = t.get('bg', '#1a1a2e')
        # Render a radio-themed SVG as album art — sine wave
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
  <rect width="400" height="400" rx="24" fill="{bg}"/>
  <path d="M40 200 C80 120, 120 120, 160 200 S240 280, 280 200 S360 120, 360 200"
        fill="none" stroke="{accent}" stroke-width="6" stroke-linecap="round" opacity="0.8"/>
  <path d="M40 200 C80 140, 120 140, 160 200 S240 260, 280 200 S360 140, 360 200"
        fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" opacity="0.4"/>
  <path d="M40 200 C80 160, 120 160, 160 200 S240 240, 280 200 S360 160, 360 200"
        fill="none" stroke="{accent}" stroke-width="3" stroke-linecap="round" opacity="0.2"/>
  <text x="200" y="340" text-anchor="middle" fill="{fg}" font-family="sans-serif"
        font-size="16" opacity="0.5">RADIO</text>
</svg>'''
        from PyQt5.QtSvg import QSvgRenderer
        from PyQt5.QtGui import QPixmap, QPainter
        from PyQt5.QtCore import QByteArray
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        pixmap = QPixmap(400, 400)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        self.player.album_widget.setPixmap(pixmap)

    def _restore_radio_state(self):
        """Restore last radio station on startup."""
        url = self.settings.value('radio/last_station_url', '')
        if not url:
            return
        name = self.settings.value('radio/last_station_name', url)
        self._current_radio_station = RadioStation(name, url)
        self._playing_mode = 'radio'
        self._apply_controls_for_mode('radio')
        self.player.track_info.setText(name)
        self.player._set_play_icon(False)
        self._load_station_art(name)

    # ── Podcast mode ─────────────────────────────────────────────

    def _on_podcast_feed_selected(self, feed):
        """Load episodes from a podcast feed into the album view."""
        self._save_podcast_position()
        self._current_podcast_feed = feed
        self.album_view.track_list_widget.clear()

        # Disconnect music click, connect podcast click
        try:
            self.album_view.track_list_widget.itemClicked.disconnect()
        except TypeError:
            pass
        self.album_view.track_list_widget.itemClicked.connect(
            self._on_episode_clicked)

        for i, ep in enumerate(feed.tracklist):
            item = QListWidgetItem(self._episode_label(ep))
            item.setData(Qt.UserRole, i)
            self.album_view.track_list_widget.addItem(item)

        # Enable right-click context menu for episode actions
        self.album_view.track_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        try:
            self.album_view.track_list_widget.customContextMenuRequested.disconnect()
        except TypeError:
            pass
        self.album_view.track_list_widget.customContextMenuRequested.connect(
            self._episode_context_menu)

        self.setWindowTitle(feed.title)

        # Show podcast description in lyrics panel
        self.lyrics_widget.set_description(feed.description)

        # Check if we need to restore a previous episode
        self._try_podcast_restore(feed)

        # Download and display podcast artwork
        if feed.image_url and not feed.art:
            self._image_thread = ImageDownloadThread(
                feed.image_url, feed.title, parent=self)
            self._image_thread.finished.connect(
                lambda path: self._on_podcast_art_downloaded(feed, path))
            self._image_thread.start()
        elif feed.art:
            self.player.album_widget.setPixmap(QPixmap(str(feed.art)))
            self.player.album = feed
            self._update_accent_for_album(force=True)

    def _on_podcast_art_downloaded(self, feed, path):
        from pathlib import Path as P
        feed.art = P(path)
        self.player.album_widget.setPixmap(QPixmap(path))
        # Set feed as player album temporarily so accent extraction works
        self.player.album = feed
        self._update_accent_for_album(force=True)

    def _episode_label(self, ep, progress=None):
        """Format an episode list label with download indicator."""
        if progress is not None:
            marker = f'\u2913 {progress}%'  # ⤓ downloading
        elif ep.is_downloaded:
            marker = '\u25cf'  # ●
        elif getattr(ep, 'guid', None) and ep.guid in self._download_threads:
            marker = '\u2913'  # ⤓ queued/downloading
        else:
            marker = '\u25cb'  # ○
        dur = ep.length_to_string(ep.length)
        return f"{marker}  {ep.date_str}  {ep.title} ({dur})"

    def _episode_context_menu(self, pos):
        """Right-click menu on podcast episode list."""
        widget = self.album_view.track_list_widget
        item = widget.itemAt(pos)
        if not item or not self._current_podcast_feed:
            return
        idx = item.data(Qt.UserRole)
        ep = self._current_podcast_feed.tracklist[idx]

        menu = QMenu(widget)
        guid = getattr(ep, 'guid', None) or str(idx)
        if ep.is_downloaded:
            delete_action = menu.addAction('Delete download')
            action = menu.exec_(widget.mapToGlobal(pos))
            if action == delete_action:
                try:
                    ep.cache_path().unlink()
                except OSError:
                    pass
                ep.path = ''
                item.setText(self._episode_label(ep))
        elif guid not in self._download_threads:
            dl_action = menu.addAction('Download')
            action = menu.exec_(widget.mapToGlobal(pos))
            if action == dl_action:
                self._download_episode(self._current_podcast_feed, idx)

    def _on_episode_clicked(self, item):
        """Download and play a podcast episode."""
        idx = item.data(Qt.UserRole)
        if idx is None or not self._current_podcast_feed:
            return
        feed = self._current_podcast_feed
        ep = feed.tracklist[idx]

        if ep.is_downloaded:
            self._play_episode(feed, idx)
        else:
            self._download_episode(feed, idx, auto_play=True)

    def _download_episode(self, feed, idx, auto_play=False):
        """Start downloading a podcast episode in the background."""
        ep = feed.tracklist[idx]
        guid = getattr(ep, 'guid', None) or str(idx)

        # Already downloading
        if guid in self._download_threads:
            if auto_play:
                self._download_play_guid = guid
            return

        if auto_play:
            self._download_play_guid = guid

        thread = EpisodeDownloadThread(ep, parent=self)
        self._download_threads[guid] = thread

        # Update list item to show downloading state
        item = self.album_view.track_list_widget.item(idx)
        if item:
            item.setText(self._episode_label(ep))

        thread.progress.connect(
            lambda p, g=guid, i=idx, e=ep: self._on_download_progress(g, i, e, p))
        thread.finished.connect(
            lambda path, g=guid, f=feed, i=idx: self._on_episode_downloaded(g, f, i, path))
        thread.error.connect(
            lambda msg, g=guid, i=idx, e=ep: self._on_download_error(g, i, e, msg))
        thread.start()

        self._update_download_status()

    def _on_download_progress(self, guid, idx, ep, percent):
        """Update the episode label with download progress."""
        item = self.album_view.track_list_widget.item(idx)
        if item:
            item.setText(self._episode_label(ep, progress=percent))
        self._update_download_status()

    def _on_episode_downloaded(self, guid, feed, idx, path):
        """Handle a completed episode download."""
        self._download_threads.pop(guid, None)
        ep = feed.tracklist[idx]
        ep.path = path
        # Update list item
        item = self.album_view.track_list_widget.item(idx)
        if item:
            item.setText(self._episode_label(ep))
        self._update_download_status()
        # Auto-play if this was the episode the user double-clicked
        if self._download_play_guid == guid:
            self._download_play_guid = None
            self._play_episode(feed, idx)

    def _on_download_error(self, guid, idx, ep, msg):
        """Handle a failed episode download."""
        self._download_threads.pop(guid, None)
        item = self.album_view.track_list_widget.item(idx)
        if item:
            item.setText(self._episode_label(ep))
        if self._download_play_guid == guid:
            self._download_play_guid = None
        self._update_download_status()
        self.podcast_view.status_label.setText(f'Error: {msg[:50]}')

    def _update_download_status(self):
        """Update the podcast status label with active download count."""
        n = len(self._download_threads)
        if n == 0:
            self.podcast_view.status_label.setText('')
        elif n == 1:
            self.podcast_view.status_label.setText('Downloading 1 episode...')
        else:
            self.podcast_view.status_label.setText(f'Downloading {n} episodes...')

    def _save_podcast_position(self):
        """Save current podcast playback position to QSettings."""
        if (self._current_podcast_feed
                and self.player.current_track
                and hasattr(self.player.current_track, 'audio_url')):
            pos = self.player.playback.curr_pos
            self.settings.setValue('podcast/last_feed', self._current_podcast_feed.url)
            self.settings.setValue('podcast/last_episode', self.player.track_pos)
            self.settings.setValue('podcast/last_seek', pos)
            # Per-episode position
            guid = self.player.current_track.guid
            if guid:
                self._episode_positions[guid] = pos
                self.settings.setValue('podcast/episode_positions', self._episode_positions)

    def _save_music_position(self):
        """Snapshot current music playback position."""
        if (self.player.current_track
                and not hasattr(self.player.current_track, 'audio_url')
                and self.player.playback.active):
            self._playing_seek_pos = self.player.playback.curr_pos

    def _save_music_folder_position(self):
        """Save the current folder_view scroll/selection for restore."""
        self._music_folder_index = self.folder_view.view.currentIndex()
        self._music_folder_scroll = self.folder_view.view.verticalScrollBar().value()

    def _restore_music_folder_position(self):
        """Restore saved folder_view scroll/selection."""
        idx = getattr(self, '_music_folder_index', None)
        if idx and idx.isValid():
            self.folder_view.view.setCurrentIndex(idx)
            self.folder_view.view.scrollTo(idx)
        scroll = getattr(self, '_music_folder_scroll', None)
        if scroll is not None:
            self.folder_view.view.verticalScrollBar().setValue(scroll)

    def _auto_fit_folder_width(self):
        """Resize the folder_view splitter pane to fit content width."""
        ideal = self.folder_view.ideal_width()
        if ideal < 150:
            return
        sizes = self.splitter.sizes()
        if len(sizes) < 5:
            return
        total = sum(sizes)
        # Allow up to 40% of total width
        ideal = min(ideal, int(total * 0.40))
        remaining = total - ideal
        # Distribute remaining proportionally to other panes
        other = sum(sizes[1:])
        if other > 0:
            ratio = remaining / other
            new_sizes = [ideal] + [int(s * ratio) for s in sizes[1:]]
        else:
            new_sizes = sizes
        self.splitter.setSizes(new_sizes)

    def _play_episode(self, feed, idx):
        """Play a podcast episode through the player."""
        self._save_music_position()
        self._save_podcast_position()
        # Show tracklist when a podcast is selected
        if not self.album_view.isVisible():
            self.album_view.setVisible(True)
            self.toggle_tracklist_btn.setChecked(True)
        ep = feed.tracklist[idx]
        ep.path = str(ep.cache_path())

        # Build a minimal Album-like object for the player
        feed.path = str(ep.cache_path().parent)
        self.player.album = feed
        self.player.track_pos = idx
        self.player.playlist = feed
        self.player.playlist_pos = idx
        self.player.current_track = ep
        self.player.track_changed.emit(ep)

        # Update player UI
        self.player.track_info.setText(ep.title)
        self.player._set_play_icon(True)
        self.player._update_time_label(0)

        # Play
        try:
            self.player.playback.load_file(ep.path)
            self.player.playback.play()
            self.player.timer.start(self.player.APP_UPDATE_TIME)
            # Resume from saved position
            saved_pos = self._episode_positions.get(ep.guid, 0)
            if saved_pos > 0:
                def _do_seek():
                    if self.player.playback.active:
                        self.player.playback.seek(saved_pos)
                QTimer.singleShot(500, _do_seek)
        except Exception as e:
            print(f"LOG: Unable to play podcast: {e}")
            self.player._set_play_icon(False)

        # Highlight in tracklist
        self.album_view.track_list_widget.setCurrentRow(idx)

        # Show podcast art
        if feed.art:
            self.player.album_widget.setPixmap(QPixmap(str(feed.art)))

        self.player.update_layout()

    def closeEvent(self, event):
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('splitter', self.splitter.saveState())
        self.settings.setValue('dark_mode', 'true' if self.current_theme is theme.DARK else 'false')
        self.settings.setValue('font_size', self.font_size)
        self.settings.setValue('accent_color', self.accent_color)
        # Save font family (extract from CSS format)
        font_family = theme.FONT.strip("'\"")
        self.settings.setValue('font_family', font_family)
        self.settings.setValue('album_accents', self._album_accents)
        # Determine library visibility from the actual panel state
        if self._mode == 'podcast':
            lib_vis = self.podcast_view.isVisible()
        elif self._mode == 'radio':
            lib_vis = self.radio_view.isVisible()
        else:
            lib_vis = self.folder_view.isVisible()
        self.settings.setValue('library_visible', 'true' if lib_vis else 'false')
        self.settings.setValue('tracklist_visible', 'true' if self.toggle_tracklist_btn.isChecked() else 'false')
        self.settings.setValue('lyrics_visible', 'true' if self.toggle_lyrics_btn.isChecked() else 'false')
        self.settings.setValue('app_mode', self._playing_mode or self._mode)
        # Save music state from the last actual music playback
        self._save_music_position()  # update snapshot if still playing music
        if self._playing_album_path:
            self.settings.setValue('last_album', self._playing_album_path)
            self.settings.setValue('last_track_pos', self._playing_track_pos)
            self.settings.setValue('last_seek_pos', self._playing_seek_pos)
        # Save podcast state (only writes if last playback was podcast)
        self._save_podcast_position()
        # Save radio state
        if self._current_radio_station:
            self.settings.setValue('radio/last_station_url', self._current_radio_station.stream_url)
            self.settings.setValue('radio/last_station_name', self._current_radio_station.name)
        self.radio_player.stop()
        self._media_keys.cleanup()
        super().closeEvent(event)

def main():
    # Start native media key backend BEFORE QApplication
    # (Qt auto-connects to D-Bus and would intercept our messages)
    media_signals, media_backend = start_native_backend()

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
    app_ui = App(media_signals=media_signals, media_backend=media_backend)
    app.installEventFilter(app_ui)
    app_ui.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
