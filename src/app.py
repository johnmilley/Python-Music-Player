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
from player import Player, _render_svg
from album_view import AlbumView
from lyrics_widget import LyricsWidget
from lyrics_fetcher import LyricsFetchThread, lyrics_path_for_track
from color_extract import most_readable, text_color_for, ensure_contrast, PaletteExtractThread
from podcast_view import PodcastView
from podcast_feed import PodcastFeed, EpisodeDownloadThread, ImageDownloadThread
from radio_view import RadioView
from radio_player import _make_radio_player, StationArtDialog, station_art_path
from radio_station import RadioStation
from media_keys import MediaKeyHandler, start_native_backend
from panel_manager import PanelManager
from grip_splitter import GripSplitter
from max_view import MaxView
from window_chrome import TitleBar, WindowGrips
import theme

from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout,
    QAction, QSplitter, QStackedWidget, QColorDialog, QShortcut, QDialog, QMenu,
    QVBoxLayout, QLabel, QLineEdit, QListWidgetItem, QSizePolicy, QFileDialog,
    QPushButton, QToolButton, QComboBox, QFormLayout, QDialogButtonBox)
from PyQt5.QtCore import Qt, QEvent, QSettings, QTimer, QSize
from PyQt5.QtGui import QColor, QPixmap, QIcon, QKeySequence


class ToolBar(QWidget):
    """Slim, always-visible top bar of icon toggles.

    Mode toggles sit on the left; panel toggles and the gear menu on the right.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('toolbar')
        # Subclassed QWidgets ignore stylesheet background-color unless set
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._layout = QHBoxLayout()
        self._layout.setContentsMargins(8, 1, 8, 1)
        self._layout.setSpacing(2)
        self.setLayout(self._layout)
        self.update_height(theme.DEFAULT_SIZE_CONTROLS)

    def update_height(self, fs):
        """Size the bar to fit the icon buttons.

        Floor matches the titlebar/tabbar height (30px) used by the sibling
        'text' app, so the two apps' chrome reads as the same height.
        """
        self.setFixedHeight(max(fs + 18, 30))

    def addWidget(self, widget):
        self._layout.addWidget(widget, 0, Qt.AlignVCenter)

    def addSpacing(self, px):
        self._layout.addSpacing(px)

    def addStretch(self):
        self._layout.addStretch()


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
        self._was_inactive = False

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

        # Frameless custom window (own titlebar below), matching the
        # non-system window style of the sibling 'text' app
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        self.setWindowTitle("lp")
        # Support both normal and PyInstaller-bundled paths
        if getattr(sys, '_MEIPASS', None):
            icon_path = Path(sys._MEIPASS) / 'icon.png'
        else:
            icon_path = Path(__file__).parent.parent / 'icon.png'
        self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(600, 350)

        # Left panel: one stacked widget swaps between the three mode views
        self.left_stack = QStackedWidget()
        self.left_stack.setObjectName('left-stack')
        self.left_stack.addWidget(self.folder_view)
        self.left_stack.addWidget(self.podcast_view)
        self.left_stack.addWidget(self.radio_view)

        # Right column: tracklist stacked over lyrics
        self.right_splitter = GripSplitter(Qt.Vertical)
        self.right_splitter.setObjectName('right-splitter')
        self.right_splitter.addWidget(self.album_view)
        self.right_splitter.addWidget(self.lyrics_widget)
        self.right_splitter.setChildrenCollapsible(False)

        self.main_splitter = GripSplitter(Qt.Horizontal)
        self.main_splitter.setObjectName('main-splitter')
        self.main_splitter.addWidget(self.left_stack)
        self.main_splitter.addWidget(self.player)
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setStretchFactor(0, 2)  # library
        self.main_splitter.setStretchFactor(1, 3)  # player
        self.main_splitter.setStretchFactor(2, 3)  # tracklist + lyrics
        self.main_splitter.setChildrenCollapsible(False)

        # Single source of truth for panel visibility and remembered sizes
        self.panels = PanelManager(self.main_splitter, self.right_splitter,
                                   self.left_stack, self.album_view,
                                   self.lyrics_widget, parent=self)

        self.layout_app = QVBoxLayout()
        self.layout_app.setContentsMargins(0, 0, 0, 0)
        self.layout_app.setSpacing(0)
        self.layout_app.addWidget(self.main_splitter)
        self.app_widget.setLayout(self.layout_app)

        # Top-level stack: normal page now; max-mode page swaps in on demand.
        # Content runs edge to edge; the frameless window's own 1px outline
        # is drawn by root_stack's stylesheet border.
        self.root_stack = QStackedWidget()
        self.root_stack.setObjectName('root-stack')
        self.root_stack.setAttribute(Qt.WA_StyledBackground, True)
        self.root_stack.addWidget(self.app_widget)
        self.setCentralWidget(self.root_stack)

        # Invisible grips floating over the edges/corners handle resizing
        # (positioned in resizeEvent, hidden while maximized/fullscreen)
        self._grips = WindowGrips(self)

        self.settings = QSettings('lp', 'music-player')
        self._episode_positions = self.settings.value('podcast/episode_positions', {}) or {}

        # Hide the native menu bar — settings live in the gear menu instead
        self.menuBar().setVisible(False)

        # Single slim top bar
        self.toolbar_widget = ToolBar(self)
        hm = self.toolbar_widget

        # Left: mode toggle icon buttons
        self.mode_music_btn = self._make_tool_button(
            'music_note', 'mode-toggle', 'Music mode (1)',
            lambda: self._set_mode('music'), checkable=True)
        self.mode_music_btn.setChecked(True)
        self.mode_podcast_btn = self._make_tool_button(
            'podcast', 'mode-toggle', 'Podcast mode (2)',
            lambda: self._set_mode('podcast'), checkable=True)
        self.mode_radio_btn = self._make_tool_button(
            'radio_waves', 'mode-toggle', 'Radio mode (3)',
            lambda: self._set_mode('radio'), checkable=True)

        # Settings menus (Theme / Preferences / Help) — reached via the gear button
        self.font_size = theme.DEFAULT_SIZE_CONTROLS  # legacy, used by some calcs
        self.font_size_controls = theme.DEFAULT_SIZE_CONTROLS
        self.font_size_tracklist = theme.DEFAULT_SIZE_TRACKLIST
        self.font_size_lyrics = theme.DEFAULT_SIZE_LYRICS

        self.prefs_menu = QMenu('Preferences', self)
        self.font_action = QAction('Fonts...', self)
        self.font_action.triggered.connect(self._open_font_settings)
        self.prefs_menu.addAction(self.font_action)
        self.change_art_action = QAction('Change Album Art...', self)
        self.change_art_action.triggered.connect(self._change_album_art)
        self.prefs_menu.addAction(self.change_art_action)
        self.prefs_menu.addSeparator()
        self.library_action = QAction('Music Library...', self)
        self.library_action.triggered.connect(self._pick_library)
        self.prefs_menu.addAction(self.library_action)

        self.colour_menu = QMenu('Theme', self)
        self.accent_color = theme.DEFAULT_ACCENT
        self._album_accents = {}
        self._last_palette_colors = []
        self._palette_thread = None
        self._accent_match = self.settings.value('accent_match', 'true') == 'true'
        self._populate_accent_menu([])

        self.help_menu = QMenu('Help', self)
        self.shortcuts_action = QAction('Display Shortcuts', self)
        self.shortcuts_action.setShortcut(QKeySequence('Shift+?'))
        self.shortcuts_action.triggered.connect(self.show_help)
        self.help_menu.addAction(self.shortcuts_action)
        self.about_action = QAction('About', self)
        self.about_action.triggered.connect(self.show_about)
        self.help_menu.addAction(self.about_action)

        # Gear button aggregates the settings menus into one entry point
        self.gear_menu = QMenu(self)
        self.gear_menu.addMenu(self.colour_menu)
        self.gear_menu.addMenu(self.prefs_menu)
        self.gear_menu.addSeparator()
        self.gear_menu.addMenu(self.help_menu)
        self.gear_btn = self._make_tool_button(
            'settings', 'icon-button', 'Settings', None)
        self.gear_btn.setMenu(self.gear_menu)
        self.gear_btn.setPopupMode(QToolButton.InstantPopup)

        # Panel toggle icon buttons
        self.toggle_library_btn = self._make_tool_button(
            'library', 'panel-toggle', 'Toggle Library (1)',
            self._on_toggle_library, checkable=True)
        self.toggle_library_btn.setChecked(True)
        self.toggle_tracklist_btn = self._make_tool_button(
            'tracklist', 'panel-toggle', 'Toggle Tracklist (4)',
            self._on_toggle_tracklist, checkable=True)
        self.toggle_tracklist_btn.setChecked(True)
        self.toggle_lyrics_btn = self._make_tool_button(
            'lyrics', 'panel-toggle', 'Toggle Lyrics (5)',
            self._on_toggle_lyrics, checkable=True)
        self.toggle_lyrics_btn.setChecked(True)

        # Assemble: modes (left) | stretch | panel toggles + gear (right)
        hm.addWidget(self.mode_music_btn)
        hm.addWidget(self.mode_podcast_btn)
        hm.addWidget(self.mode_radio_btn)
        hm.addStretch()
        hm.addWidget(self.toggle_library_btn)
        hm.addWidget(self.toggle_tracklist_btn)
        hm.addWidget(self.toggle_lyrics_btn)
        hm.addSpacing(8)
        hm.addWidget(self.gear_btn)

        # Toggle buttons mirror PanelManager state — they are display only
        self.panels.visibility_changed.connect(self._on_panel_visibility)

        # The always-visible toolbar, with a slim accent strip pinned just
        # below it — both at the top of the layout
        self.accent_bar = QWidget()
        self.accent_bar.setObjectName('accent-bar')
        self.accent_bar.setAttribute(Qt.WA_StyledBackground, True)
        self.accent_bar.setFixedHeight(3)

        # Custom titlebar (frameless window) sits above the toolbar, same
        # background, so the two read as one continuous strip of chrome
        self.title_bar = TitleBar(self)
        self.title_bar.set_title(self.windowTitle())
        self.layout_app.insertWidget(0, self.title_bar)
        self.layout_app.insertWidget(1, self.toolbar_widget)
        self.layout_app.insertWidget(2, self.accent_bar)

        # Max mode state — the MaxView page is created lazily on first use
        self.is_maxplayer = False
        self._max_view = None

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
        self.lyrics_widget.seek_requested.connect(self._on_lyrics_seek)

        # Focus change tracking for pane highlighting (property-driven)
        for view in (self.folder_view.view, self.album_view.track_list_widget):
            view.setProperty('paneFocused', False)
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
        """Apply the theme: one consolidated stylesheet on the main window.

        Runs only on theme/accent/font changes — focus changes just flip the
        'paneFocused' property (see _on_focus_changed).
        """
        self.current_theme = t
        # Effective theme: user's accent, contrast-checked against the bg.
        # 'accent' is contrast-checked at a lower bar (3:1) since it's mostly
        # used as a background/decorative fill with its own paired text color;
        # 'accent_text' is checked at a stricter bar (4.5:1, WCAG body text)
        # for the few spots that render accent AS text directly on the page
        # background (lyrics active line, description timestamps) — those
        # must stay readable before they stay on-brand.
        t = dict(t)
        accent = ensure_contrast(self.accent_color, t['bg'])
        t['accent'] = accent
        t['accent_fg'] = text_color_for(accent)
        t['accent_text'] = ensure_contrast(self.accent_color, t['bg'], min_ratio=4.5)
        # Legacy aliases still read by dialogs and the lyrics HTML renderer
        t['selection'] = accent
        t['selection_text'] = t['accent_fg']
        self.effective_theme = t

        self.setStyleSheet(theme.build_qss(
            t, self.font_size_controls,
            self.font_size_tracklist, self.font_size_lyrics))
        self.player.update_button_icons(t['fg'], hover_color=accent)
        self.player.set_control_scale(self.font_size_controls)
        self.toolbar_widget.update_height(self.font_size_controls)
        self._refresh_toolbar_icons()
        self.main_splitter.set_colors(t['hairline'], t['fg_dim'], accent)
        self.right_splitter.set_colors(t['hairline'], t['fg_dim'], accent)
        self.lyrics_widget.set_theme(t, self.font_size_lyrics)
        if self.is_maxplayer:
            self._style_max_mode()

    def _make_tool_button(self, icon_name, obj_name, tooltip, handler,
                          checkable=False):
        """Build an icon-only toolbar button. Icons are colored later by
        _refresh_toolbar_icons (dim / fg on hover / accent when checked)."""
        btn = QToolButton()
        btn.setObjectName(obj_name)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setIconSize(QSize(20, 20))
        btn.setFixedHeight(22)
        btn._icon_name = icon_name
        if checkable:
            btn.setCheckable(True)
        if handler is not None:
            btn.clicked.connect(handler)
        return btn

    def _toolbar_icon(self, name, size=20):
        """A stateful QIcon: fg_dim normally, fg on hover, accent when checked."""
        t = self.effective_theme
        icon = QIcon()
        icon.addPixmap(_render_svg(name, t['fg_dim'], size), QIcon.Normal, QIcon.Off)
        icon.addPixmap(_render_svg(name, t['fg'], size), QIcon.Active, QIcon.Off)
        icon.addPixmap(_render_svg(name, t['accent'], size), QIcon.Normal, QIcon.On)
        icon.addPixmap(_render_svg(name, t['accent'], size), QIcon.Active, QIcon.On)
        return icon

    def _refresh_toolbar_icons(self):
        for btn in (self.mode_music_btn, self.mode_podcast_btn,
                    self.mode_radio_btn, self.toggle_library_btn,
                    self.toggle_tracklist_btn, self.toggle_lyrics_btn,
                    self.gear_btn):
            name = getattr(btn, '_icon_name', None)
            if name:
                btn.setIcon(self._toolbar_icon(name))

    def toggle_theme(self):
        new_theme = theme.DARK if self.current_theme is theme.LIGHT else theme.LIGHT
        # Ensure accent is readable against the new background
        self.accent_color = ensure_contrast(self.accent_color, new_theme['bg'])
        self.apply_theme(new_theme)
        # Refresh colour menu so Dark/Light label stays in sync. Reuse the
        # cached album palette — never extract on the UI thread; if there is
        # no cache yet, a background extraction repopulates the menu when done.
        self._populate_accent_menu(self._last_palette_colors)
        if (not self._last_palette_colors
                and self.player.album and self.player.album.art
                and not (self._palette_thread and self._palette_thread.isRunning())):
            album_path = self.player.album.path
            self._palette_thread = PaletteExtractThread(str(self.player.album.art))
            self._palette_thread.finished.connect(
                lambda colors, p=album_path: self._on_palette_extracted(colors, p))
            self._palette_thread.start()

    def set_font_size(self, size):
        self.font_size = size
        self.font_size_controls = size
        self.font_size_tracklist = size
        self.font_size_lyrics = size
        self.apply_theme(self.current_theme)

    def _step_font_size(self, delta):
        sizes = theme.SIZES_CONTROLS
        try:
            idx = sizes.index(self.font_size_controls)
        except ValueError:
            idx = sizes.index(theme.DEFAULT_SIZE_CONTROLS)
        idx = max(0, min(len(sizes) - 1, idx + delta))
        new_size = sizes[idx]
        self.font_size = new_size
        self.font_size_controls = new_size
        self.apply_theme(self.current_theme)

    def set_accent(self, color):
        self.accent_color = color
        # Save per-album preference
        if self.player.album and self.player.album.path:
            self._album_accents[self.player.album.path] = color
        self.apply_theme(self.current_theme)

    def _open_font_settings(self):
        """Open custom font settings dialog with 3 categories."""
        dlg = QDialog(self)
        dlg.setWindowTitle('Font Settings')
        dlg.setMinimumWidth(340)
        layout = QVBoxLayout(dlg)

        fonts = theme.AVAILABLE_FONTS
        accent = self.effective_theme.get('accent_text', self.effective_theme['accent'])
        dlg.setStyleSheet(theme.dialog_qss(self.effective_theme))

        def _strip(f):
            return f.strip("'\"")

        def _make_row(label, current_font, current_size, sizes):
            section = QLabel(label)
            section.setStyleSheet(f'font-weight: bold; color: {accent}; font-size: 12pt; margin-top: 8px;')
            layout.addWidget(section)
            form = QFormLayout()
            form.setSpacing(6)

            font_cb = QComboBox()
            for f in fonts:
                font_cb.addItem(f)
                # Show each item in its own font
                font_cb.setItemData(font_cb.count() - 1, f, Qt.FontRole)
            cur = _strip(current_font)
            idx = fonts.index(cur) if cur in fonts else 0
            font_cb.setCurrentIndex(idx)

            size_cb = QComboBox()
            for s in sizes:
                size_cb.addItem(str(s))
            try:
                size_idx = sizes.index(current_size)
            except ValueError:
                size_idx = 0
            size_cb.setCurrentIndex(size_idx)

            # Live preview: set font_cb's own font to the selected font
            def _update_preview():
                from PyQt5.QtGui import QFont
                f = QFont(font_cb.currentText())
                f.setPointSize(int(size_cb.currentText()))
                font_cb.setFont(f)
            font_cb.currentIndexChanged.connect(lambda: _update_preview())
            size_cb.currentIndexChanged.connect(lambda: _update_preview())
            _update_preview()

            form.addRow('Font:', font_cb)
            form.addRow('Size:', size_cb)
            layout.addLayout(form)
            return font_cb, size_cb

        ctrl_font, ctrl_size = _make_row(
            'Controls', theme.FONT_CONTROLS,
            self.font_size_controls, theme.SIZES_CONTROLS)
        track_font, track_size = _make_row(
            'Tracklist', theme.FONT_TRACKLIST,
            self.font_size_tracklist, theme.SIZES_TRACKLIST)
        lyrics_font, lyrics_size = _make_row(
            'Lyrics', theme.FONT_LYRICS,
            self.font_size_lyrics, theme.SIZES_LYRICS)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addSpacing(12)
        layout.addWidget(buttons)

        if dlg.exec_() == QDialog.Accepted:
            theme.FONT_CONTROLS = f"'{ctrl_font.currentText()}'"
            theme.FONT_TRACKLIST = f"'{track_font.currentText()}'"
            theme.FONT_LYRICS = f"'{lyrics_font.currentText()}'"
            theme.FONT = theme.FONT_CONTROLS  # legacy alias
            self.font_size_controls = int(ctrl_size.currentText())
            self.font_size_tracklist = int(track_size.currentText())
            self.font_size_lyrics = int(lyrics_size.currentText())
            self.font_size = self.font_size_controls
            self.apply_theme(self.current_theme)

    def pick_custom_accent(self):
        color = QColorDialog.getColor(QColor(self.accent_color), self, 'Pick Accent Color')
        if color.isValid():
            self.set_accent(color.name())

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
        self._add_colour_section('Presets', list(theme.ACCENT_PRESETS.values()))
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
        self._last_palette_colors = []  # cache belongs to the previous album
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
        self._last_palette_colors = colors
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
        t = self.effective_theme
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
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
        # Panel visibility + splitter sizes (PanelManager owns both;
        # first run without saved state gets the minimal default layout)
        self.panels.load(self.settings)
        # Restore per-category font settings
        for cat, attr, sizes_list, font_var in [
            ('controls', 'font_size_controls', theme.SIZES_CONTROLS, 'FONT_CONTROLS'),
            ('tracklist', 'font_size_tracklist', theme.SIZES_TRACKLIST, 'FONT_TRACKLIST'),
            ('lyrics', 'font_size_lyrics', theme.SIZES_LYRICS, 'FONT_LYRICS'),
        ]:
            saved_sz = self.settings.value(f'font_size_{cat}', type=int)
            if saved_sz:
                lo, hi = sizes_list[0], sizes_list[-1]
                setattr(self, attr, max(lo, min(hi, saved_sz)))
            saved_fam = self.settings.value(f'font_family_{cat}')
            if saved_fam:
                setattr(theme, font_var, f"'{saved_fam}'")
        self.font_size = self.font_size_controls
        theme.FONT = theme.FONT_CONTROLS
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
        # Restore app mode
        saved_mode = self.settings.value('app_mode', 'music')
        if saved_mode == 'podcast':
            self._set_mode('podcast')
            self._restore_podcast_state()
        elif saved_mode == 'radio':
            self._set_mode('radio')
            self._restore_radio_state()
        else:
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
            ('Alt',     'Toggle menu bar',     None),
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

    def setWindowTitle(self, title):
        super().setWindowTitle(title)
        if hasattr(self, 'title_bar'):
            self.title_bar.set_title(title)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._grips.relayout()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self._update_window_state_chrome()

    def _update_window_state_chrome(self):
        """Keep the custom titlebar/border/grips in sync with window state.

        Frameless windows have no OS border to draw a maximize/restore
        distinction for us, so the titlebar's square glyph, the window's
        hairline outline (hidden while maximized/fullscreen, like a normal
        window's border merging with the screen edge) and the resize grips
        (pointless without a normal-state border) are driven from here.
        """
        maximized = self.isMaximized()
        edgeless = maximized or self.isFullScreen()
        self.title_bar.set_maximized(maximized)
        self._grips.set_enabled(not edgeless)
        if self.root_stack.property('maximized') != edgeless:
            self.root_stack.setProperty('maximized', edgeless)
            self.root_stack.style().unpolish(self.root_stack)
            self.root_stack.style().polish(self.root_stack)
        # Windows draws frameless+maximized windows a few px off-screen
        # (the invisible native resize border still swells outward); inset
        # the content to compensate. Not an issue on Linux/macOS.
        if sys.platform == 'win32':
            m = 8 if maximized else 0
            self.setContentsMargins(m, m, m, m)

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
                Qt.Key_5: self.toggle_lyrics,
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
        if t == event.KeyPress and not isinstance(self.focusWidget(), QLineEdit):
            key = event.key()
            if key == Qt.Key_Tab:
                self._cycle_pane_focus()
                return True
            # h/l on album tracklist → switch to folder view
            if obj is self.album_view.track_list_widget and key in (Qt.Key_H, Qt.Key_L):
                if not self.panels.is_visible('library'):
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
                        self.panels.set_visible('tracklist', True)
                        self.album_view.track_list_widget.setFocus()
                        return True
                # h at top level → switch to tracklist
                if key == Qt.Key_H:
                    root = self.folder_view.view.rootIndex()
                    at_top = not idx.isValid() or (not self.folder_view.view.isExpanded(idx)
                                                   and idx.parent() == root)
                    if at_top:
                        self.panels.set_visible('tracklist', True)
                        self.album_view.track_list_widget.setFocus()
                        return True
        return super().eventFilter(obj, event)

    def _toggle_and_focus_library(self):
        """Toggle library panel and focus it if shown."""
        if self.is_maxplayer:
            return
        self.toggle_library()
        if self.panels.is_visible('library'):
            current = self.left_stack.currentWidget()
            if current is self.podcast_view:
                self.podcast_view.feed_list.setFocus()
            elif current is self.radio_view:
                self.radio_view.station_list.setFocus()
            else:
                self.folder_view.view.setFocus()
        elif self.panels.is_visible('tracklist'):
            self.album_view.track_list_widget.setFocus()

    def _toggle_and_focus_tracklist(self):
        """Toggle tracklist panel and focus it if shown."""
        if self.is_maxplayer:
            return
        self.toggle_tracklist()
        if self.panels.is_visible('tracklist'):
            self.album_view.track_list_widget.setFocus()
        elif self.panels.is_visible('library'):
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
        """Flip the 'paneFocused' property on the panes whose state changed.

        The stylesheet targets [paneFocused="true"] selectors, so only the
        affected view is repolished — no stylesheet regeneration.
        """
        for view in (self.folder_view.view, self.album_view.track_list_widget):
            focused = view.hasFocus()
            if view.property('paneFocused') != focused:
                view.setProperty('paneFocused', focused)
                view.style().unpolish(view)
                view.style().polish(view)
                view.viewport().update()

    def show_help(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Keyboard Shortcuts')
        dialog.setStyleSheet(theme.dialog_qss(self.effective_theme, fs=12))
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
        dialog = QDialog(self)
        dialog.setWindowTitle('About lp')
        dialog.setStyleSheet(theme.dialog_qss(self.effective_theme, fs=12))
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

    def _on_panel_visibility(self, name, visible):
        """Mirror PanelManager state onto the toolbar toggle buttons."""
        btn = {'library': self.toggle_library_btn,
               'tracklist': self.toggle_tracklist_btn,
               'lyrics': self.toggle_lyrics_btn}.get(name)
        if btn:
            btn.setChecked(visible)

    def _on_toggle_library(self, checked):
        self.panels.set_visible('library', checked)

    def _on_toggle_tracklist(self, checked):
        self.panels.set_visible('tracklist', checked)

    def _on_toggle_lyrics(self, checked):
        if self.is_maxplayer:
            self._toggle_max_lyrics()
        else:
            self.panels.set_visible('lyrics', checked)

    def toggle_library(self):
        self.panels.toggle('library')

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
        self.panels.set_visible('tracklist', True, remember_size=False)

    def toggle_tracklist(self):
        self.panels.toggle('tracklist')

    def toggle_lyrics(self):
        if self.is_maxplayer:
            self._toggle_max_lyrics()
        else:
            self.panels.toggle('lyrics')

    def _toggle_max_lyrics(self):
        if self._max_view:
            col = self._max_view.lyrics_column
            col.setVisible(not col.isVisible())

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
        # Podcast episodes show description instead of lyrics
        if track_mode == 'podcast' and hasattr(track, 'description'):
            self.lyrics_widget.set_description(track.description)
            return

        if not self.player.album:
            return
        path = lyrics_path_for_track(track, self.player.album)

        # Already cached on disk
        if path.exists():
            text = path.read_text(encoding='utf-8')
            self.lyrics_widget.set_lyrics(text)
            return

        # Already tried and failed for this track
        track_key = f'{track.artist}:{track.title}:{track.album}'
        if track_key in self._failed_lyrics:
            self.lyrics_widget.set_lyrics('')
            return

        self.lyrics_widget.set_lyrics('Fetching lyrics...')
        # Stop any in-progress fetch before starting a new one
        if self._lyrics_thread and self._lyrics_thread.isRunning():
            self._lyrics_thread.lyrics_ready.disconnect(self._on_lyrics_fetched)
            self._lyrics_thread.quit()
            self._lyrics_thread.wait(2000)
        self._lyrics_track_key = track_key
        self._lyrics_thread = LyricsFetchThread(
            track.artist, track.title, track.album, track, self.player.album,
            duration=track.length
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

        if file_path and text:
            self.lyrics_widget.set_lyrics(text)
        else:
            if current:
                self._failed_lyrics.add(self._lyrics_track_key)
            self.lyrics_widget.set_lyrics('')

    def _update_lyrics_position(self):
        """Feed current playback position to lyrics widget for sync."""
        if self.player.playback.playing and self.lyrics_widget.isVisible():
            self.lyrics_widget.update_position(self.player.playback.curr_pos)

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

        # The normal page is untouched behind the stack — only the window
        # geometry needs restoring after fullscreen
        self._pre_max_geometry = self.saveGeometry()
        self.panels.locked = True

        if self._max_view is None:
            self._max_view = MaxView(self.player)
            self._max_view.art.clicked.connect(self.toggle_maxplayer)
            self.root_stack.addWidget(self._max_view)

        # Seed current state; player signals keep it in sync from here on
        track = self.player.current_track
        self._max_view.set_title(str(track.title) if track and track.title else '')
        art_px = self.player.album_widget.pixmap()
        if art_px:
            self._max_view.art.set_source(art_px)
        else:
            self._max_view.art.clear()

        # Borrow the one true lyrics widget — same content, same highlight
        self._max_view.attach_lyrics(self.lyrics_widget)

        self._style_max_mode()
        self.root_stack.setCurrentWidget(self._max_view)
        self._max_view.setFocus()
        # Grips/border are hidden by _update_window_state_chrome when the
        # fullscreen state change lands
        self.showFullScreen()

    def _style_max_mode(self):
        """Bump the borrowed lyrics widget's font while in max mode.

        The max view chrome itself is styled by the main stylesheet; this
        per-widget override is cleared again on exit.
        """
        t = self.effective_theme
        fs = self.font_size_lyrics + 8
        self.lyrics_widget.setStyleSheet(f"""
            #lyrics-text {{
                background-color: {t['bg']};
                color: {t['fg']};
                font-family: {theme.FONT_LYRICS};
                font-size: {fs}pt;
            }}
        """)
        self.lyrics_widget.set_theme(t, fs)

    def exit_maxplayer(self):
        if not self.is_maxplayer:
            return
        self.is_maxplayer = False

        # Return the borrowed lyrics widget to the right column
        self.right_splitter.insertWidget(1, self.lyrics_widget)
        self.lyrics_widget.setStyleSheet('')  # drop the max-mode font bump
        self.panels.locked = False
        self.lyrics_widget.setVisible(self.panels.is_visible('lyrics'))
        self.panels.reapply_size('lyrics')
        self._max_view.lyrics_column.setVisible(True)  # reset for next entry

        self.root_stack.setCurrentWidget(self.app_widget)

        # Restyle (also restores the normal lyrics font size)
        self.apply_theme(self.current_theme)

        # Exit fullscreen and restore geometry
        self.showNormal()
        self._was_inactive = False
        if self._pre_max_geometry:
            self.restoreGeometry(self._pre_max_geometry)
        self._update_window_state_chrome()
        # macOS fullscreen exit animation delays focus — retry once it settles
        def _force_focus():
            self.raise_()
            self.activateWindow()
            self.player.setFocus()
            self._was_inactive = False
        _force_focus()
        QTimer.singleShot(300, _force_focus)

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
            # Remember which right panels music mode had open
            self.panels.snapshot('music')
        self._mode = mode
        self.mode_music_btn.setChecked(mode == 'music')
        self.mode_podcast_btn.setChecked(mode == 'podcast')
        self.mode_radio_btn.setChecked(mode == 'radio')
        self._update_radio_icon()

        if mode == 'podcast':
            self.left_stack.setCurrentWidget(self.podcast_view)
            self.panels.set_visible('tracklist', False, remember_size=False)
            self.panels.set_visible('lyrics', False, remember_size=False)
            self.podcast_view.load_saved_feeds()
        elif mode == 'radio':
            self.left_stack.setCurrentWidget(self.radio_view)
            self.panels.set_visible('tracklist', False, remember_size=False)
            self.panels.set_visible('lyrics', False, remember_size=False)
            self.radio_view.load_saved_stations()
        else:
            self.left_stack.setCurrentWidget(self.folder_view)
            self.panels.restore('music')
            self._restore_music_folder_position()
            # Reconnect album_view click to music handler
            try:
                self.album_view.track_list_widget.itemClicked.disconnect()
            except TypeError:
                pass
            self.album_view.track_list_widget.itemClicked.connect(
                self.album_view.set_current_track)
            self.album_view.track_list_widget.setContextMenuPolicy(Qt.NoContextMenu)

        # Switching modes always reveals the new mode's library panel
        self.panels.set_visible('library', True, remember_size=False)

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
        small_bold = f'font-size: {max(self.font_size_controls - 3, 7)}pt; font-weight: bold;'
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
                self.player.set_art(px)
                return
        self._set_radio_art()

    def _pick_station_art(self):
        """Open the station art picker dialog for the current radio station."""
        if self._current_radio_station:
            self._pick_station_art_for(self._current_radio_station)

    def _pick_station_art_for(self, station):
        """Open the station art picker dialog for any station."""
        dlg = StationArtDialog(station.name, self.effective_theme, parent=self)
        dlg.art_selected.connect(self._on_station_art_picked)
        dlg.exec_()

    def _on_station_art_picked(self, pixmap):
        """Display the user-chosen station art."""
        if not pixmap.isNull():
            self.player.set_art(pixmap)

    def _on_radio_metadata(self, title):
        """Update now-playing display when stream metadata changes."""
        self._radio_now_playing = title
        if self._current_radio_station:
            display = f'{self._current_radio_station.name}  \u2022  {title}'
            self.player.track_info.setText(display)
            # Show now-playing in the lyrics panel (set HTML directly)
            import html as html_mod
            t = self.effective_theme
            fg = t.get('fg', '#e0e0e0')
            accent = t.get('accent_text', t['accent'])
            safe_title = html_mod.escape(title)
            safe_name = html_mod.escape(self._current_radio_station.name)
            self.lyrics_widget.set_status_html(
                f'<div style="text-align:center; padding:20px; font-family:{theme.FONT};">'
                f'<p style="font-size:14pt; color:{fg}; opacity:0.6;">Now Playing</p>'
                f'<p style="font-size:16pt; font-weight:bold; color:{accent};">{safe_title}</p>'
                f'<p style="font-size:12pt; color:{fg}; opacity:0.5;">{safe_name}</p>'
                f'</div>')

    def _set_radio_art(self):
        """Set a radio-themed visual in the album art area."""
        t = getattr(self, 'effective_theme', theme.LIGHT)
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
        self.player.set_art(pixmap)

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
            item.setToolTip(self._episode_label(ep))
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
            self.player.set_art(QPixmap(str(feed.art)))
            self.player.album = feed
            self._update_accent_for_album(force=True)

    def _on_podcast_art_downloaded(self, feed, path):
        from pathlib import Path as P
        feed.art = P(path)
        self.player.set_art(QPixmap(path))
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

    def _play_episode(self, feed, idx):
        """Play a podcast episode through the player."""
        self._save_music_position()
        self._save_podcast_position()
        # Show tracklist when a podcast is selected
        self.panels.set_visible('tracklist', True, remember_size=False)
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
            self.player.set_art(QPixmap(str(feed.art)))


    def closeEvent(self, event):
        self.settings.setValue('geometry', self.saveGeometry())
        self.panels.save(self.settings)
        self.settings.setValue('dark_mode', 'true' if self.current_theme is theme.DARK else 'false')
        # Save per-category font settings
        for cat, sz_attr, font_var in [
            ('controls', 'font_size_controls', 'FONT_CONTROLS'),
            ('tracklist', 'font_size_tracklist', 'FONT_TRACKLIST'),
            ('lyrics', 'font_size_lyrics', 'FONT_LYRICS'),
        ]:
            self.settings.setValue(f'font_size_{cat}', getattr(self, sz_attr))
            self.settings.setValue(f'font_family_{cat}', getattr(theme, font_var).strip("'\""))
        self.settings.setValue('accent_color', self.accent_color)
        self.settings.setValue('album_accents', self._album_accents)
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
    theme.resolve_fonts()

    app.setDesktopFileName('lp')
    app_ui = App(media_signals=media_signals, media_backend=media_backend)
    app.installEventFilter(app_ui)
    app_ui.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
