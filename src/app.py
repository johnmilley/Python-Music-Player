# App — main window orchestrator (v2: the old mini mode is the main window)
# Creates all widgets, wires signals between them, and manages:
#   - Four content modes: music, podcast, radio, favourites (see _set_mode)
#   - The stage: library pane | album art + floating controls | lyrics pane,
#     with the window widening/narrowing as side panes open/close so the
#     art stays square; max mode (fullscreen art) is a second page
#   - Theming: light/dark with per-album accent colors
#   - Keyboard shortcuts and media key handling
#   - Session persistence (window state, playback position, settings)

import os
import sys
from pathlib import Path

# local
from folder_view import FolderView
from player import Player, _render_svg
from album_view import AlbumView
from lyrics_widget import LyricsWidget
import bg_threads
from lyrics_fetcher import LyricsFetchThread
from color_extract import most_readable, text_color_for, ensure_contrast, PaletteExtractThread
from podcast_view import PodcastView
from podcast_feed import PodcastFeed, EpisodeDownloadThread, ImageDownloadThread
from radio_view import RadioView
from radio_player import _make_radio_player, StationArtDialog, station_art_path
from radio_station import RadioStation
from media_keys import MediaKeyHandler, start_native_backend
from favorites import FavoritesStore
from favorites_view import FavoritesView
from playlist import Playlist
from max_view import MaxView
from library_pane import LibraryPane, LyricsPane
from quick_switcher import QuickSwitcher
from media_server import LibraryCache
from album import Album, same_listing
from window_chrome import WindowGrips
from version import __version__
import play_log
import theme
import overlay_controls

from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout,
    QAction, QStackedWidget, QColorDialog, QShortcut, QDialog, QMenu,
    QVBoxLayout, QLabel, QLineEdit, QListWidgetItem, QSizePolicy, QFileDialog,
    QPushButton, QToolButton, QSlider, QDialogButtonBox, QMessageBox,
    QWidgetAction, QGridLayout)
from PyQt5.QtCore import Qt, QEvent, QSettings, QTimer, QUrl, QPoint, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap, QIcon, QKeySequence, QDesktopServices


class AccentSwatchGrid(QWidget):
    """A grid of colour swatches embedded in the accent menu.

    Hovering a swatch previews that accent live across the app; moving off
    the grid without clicking emits hovered('') so the owner can restore
    the pre-preview colour; clicking commits the pick.
    """
    hovered = pyqtSignal(str)   # colour under the cursor; '' = left the grid
    picked = pyqtSignal(str)

    PER_ROW = 5

    def __init__(self, colors, theme_dict, current='', names=None, parent=None):
        super().__init__(parent)
        t = theme_dict
        grid = QGridLayout(self)
        grid.setContentsMargins(16, 4, 16, 6)
        grid.setSpacing(6)
        names = names or {}
        for i, c in enumerate(colors):
            btn = QToolButton()
            btn.setFixedSize(24, 24)
            btn.setCursor(Qt.PointingHandCursor)
            tip = names.get(c)
            btn.setToolTip(f'{tip}  ({c})' if tip else c)
            ring = t['fg'] if c == current else 'transparent'
            btn.setStyleSheet(f"""
                QToolButton {{
                    background-color: {c};
                    border: 2px solid {ring};
                    border-radius: 12px;
                }}
                QToolButton:hover {{ border: 2px solid {t['fg']}; }}
            """)
            btn._swatch_color = c
            btn.installEventFilter(self)
            btn.clicked.connect(lambda _, color=c: self.picked.emit(color))
            grid.addWidget(btn, i // self.PER_ROW, i % self.PER_ROW)
        # Left-align partial rows instead of spreading them out
        grid.setColumnStretch(self.PER_ROW, 1)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Enter and hasattr(obj, '_swatch_color'):
            self.hovered.emit(obj._swatch_color)
        return super().eventFilter(obj, event)

    def leaveEvent(self, event):
        self.hovered.emit('')
        super().leaveEvent(event)


# Default first-run window side, and the narrowest a side pane opens to
DEFAULT_SIDE = 400
PANE_MIN_W = 200


class App(QMainWindow):
    """Main application window — owns all widgets and wires them together.

    Layout (stage page of root_stack):
        library_pane | player (art + floating ControlPanel) | lyrics_pane

    The library pane's mode tabs swap left_stack (folder_view, podcast_view,
    radio_view, favorites_view); opening an album drills the pane down to
    the tracklist. Max mode replaces the stage with fullscreen art.
    """

    def __init__(self, media_signals=None, media_backend=None):
        super().__init__()
        self._media_signals = media_signals
        self._media_backend = media_backend
        self._was_inactive = False

        self.player = Player()
        self.album_view = AlbumView()
        self.lyrics_widget = LyricsWidget()
        self.folder_view = FolderView(self.album_view)
        self.podcast_view = PodcastView()
        self.radio_view = RadioView()
        self.radio_player = _make_radio_player()

        # Favourites: persistent store + the left-pane collections view
        self.fav_store = FavoritesStore()
        self.favorites_view = FavoritesView(self.fav_store)
        self.album_view.fav_store = self.fav_store
        self.album_view.favorites_changed.connect(self._on_favorites_changed)
        self.favorites_view.collection_selected.connect(
            self._load_favorites_collection)
        self.favorites_view.shuffle_toggled.connect(self._on_shuffle_toggled)
        self._last_playlist_folder = None  # per-song art/accent tracking
        self._last_playlist_cover = None

        # Mode: 'music', 'podcast', 'radio', or 'favorites'
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
        self.player.listen_ended.connect(self._on_listen_ended)

        # Stage panel — same signals max mode wires up, since it's the same
        # ControlPanel class. Prev/play/next continue to route
        # through the legacy pressed-based mode-swap wiring (see
        # _set_music_controls/_set_podcast_controls/_set_radio_controls),
        # so those aren't connected here.
        self.player.panel.heart_clicked.connect(self._toggle_current_favorite)
        self.player.panel.shuffle_clicked.connect(self._toggle_shuffle)
        self.player.panel.repeat_clicked.connect(self._toggle_repeat)

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
        self.setMinimumSize(180, 180)

        # Library pane (left): mode tabs over a library ⇄ tracks drill-down.
        # left_stack swaps between the four mode views.
        self.left_stack = QStackedWidget()
        self.left_stack.setObjectName('left-stack')
        self.left_stack.addWidget(self.folder_view)
        self.left_stack.addWidget(self.podcast_view)
        self.left_stack.addWidget(self.radio_view)
        self.left_stack.addWidget(self.favorites_view)
        self.library_pane = LibraryPane(self.left_stack)
        self.library_pane.tracks_slot.addWidget(self.album_view)
        self.library_pane.mode_clicked.connect(self._set_mode)
        self.library_pane.back_clicked.connect(self._show_library_page)
        self.library_pane.now_playing_clicked.connect(self._show_now_playing)
        self.folder_view.album_opened.connect(lambda _: self._drill_to_tracks())

        # Lyrics pane (right)
        self.lyrics_pane = LyricsPane()
        self.lyrics_pane.slot.addWidget(self.lyrics_widget)

        # Side pane visibility (explicit flags, not isVisible(): the window
        # may be hidden/fullscreen) and the left pane's current width, for
        # keeping the art anchored on screen as the window widens
        self._library_on = False
        self._lyrics_on = False
        self._left_pane_w = 0
        self._resizing_self = False  # guard for programmatic resizes

        self.stage = QWidget()
        self.stage.setObjectName('stage')
        stage_layout = QHBoxLayout(self.stage)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.setSpacing(0)
        stage_layout.addWidget(self.library_pane, stretch=1)
        stage_layout.addWidget(self.player)
        stage_layout.addWidget(self.lyrics_pane, stretch=1)
        self.library_pane.hide()
        self.lyrics_pane.hide()

        # Panel buttons that only exist on the stage's own panel
        self.player.panel.tracklist_btn.setToolTip('Library / tracklist (4)')
        self.player.panel.tracklist_clicked.connect(self._toggle_and_focus_tracklist)
        self.player.panel.lyrics_clicked.connect(self.toggle_lyrics)
        self.player.panel.more_clicked.connect(self._popup_menu_at_more)
        self.player.art_double_clicked.connect(self.toggle_maxplayer)
        self.player.art_menu_requested.connect(self.main_menu_popup)

        # Top-level stack: the stage; max-mode page swaps in on demand.
        # The frameless window's own 1px outline is drawn by root_stack's
        # stylesheet border.
        self.root_stack = QStackedWidget()
        self.root_stack.setObjectName('root-stack')
        self.root_stack.setAttribute(Qt.WA_StyledBackground, True)
        self.root_stack.addWidget(self.stage)
        self.setCentralWidget(self.root_stack)

        # Invisible grips floating over the edges/corners handle resizing
        # (positioned in resizeEvent, hidden while maximized/fullscreen)
        self._grips = WindowGrips(self)

        # Ctrl+K album switcher, floating over the window. Its album list
        # is a background walk of the library (warmed in _restore_state).
        self.library_cache = LibraryCache()
        self.quick_switcher = QuickSwitcher(self)
        self.quick_switcher.album_chosen.connect(self._open_album_by_id)

        self.settings = QSettings('lp', 'music-player')
        self._episode_positions = self.settings.value('podcast/episode_positions', {}) or {}

        # Hide the native menu bar — settings live in the ⋯ menu instead
        self.menuBar().setVisible(False)

        # Settings menus (Theme / Preferences / Help) — reached via the gear button
        # One font (Inter) and one size for the whole app
        self.font_size = theme.DEFAULT_SIZE
        # The floating ControlPanels' scrim opacity — 0
        # (glassy/see-through) .. 100 (solid), floored in
        # overlay_controls.scrim_alpha so text never gets unreadable. The
        # normal-mode player column's panel has no scrim, so this doesn't
        # apply there.
        self.overlay_opacity = overlay_controls.DEFAULT_OPACITY

        self.prefs_menu = QMenu('Preferences', self)
        self.font_action = QAction('Text Size...', self)
        self.font_action.triggered.connect(self._open_text_size)
        self.prefs_menu.addAction(self.font_action)
        self.opacity_action = QAction('Overlay Opacity...', self)
        self.opacity_action.triggered.connect(self._open_overlay_opacity)
        self.prefs_menu.addAction(self.opacity_action)
        self.change_art_action = QAction('Change Cover Art...', self)
        self.change_art_action.triggered.connect(self._change_album_art)
        self.prefs_menu.addAction(self.change_art_action)
        self.add_art_action = QAction('Add Album Art...', self)
        self.add_art_action.triggered.connect(self._add_album_art)
        self.prefs_menu.addAction(self.add_art_action)
        self.find_art_action = QAction('Find More Album Art...', self)
        self.find_art_action.triggered.connect(self._find_extra_art)
        self.prefs_menu.addAction(self.find_art_action)
        self.prefs_menu.addSeparator()
        self.library_action = QAction('Music Library...', self)
        self.library_action.triggered.connect(self._pick_library)
        self.prefs_menu.addAction(self.library_action)
        self.prefs_menu.addSeparator()
        self.remote_action = QAction('Remote Access...', self)
        self.remote_action.triggered.connect(self._open_remote_dialog)
        self.prefs_menu.addAction(self.remote_action)
        self.stats_action = QAction('Listening Stats...', self)
        self.stats_action.triggered.connect(self._open_stats_page)
        self.prefs_menu.addAction(self.stats_action)

        self.colour_menu = QMenu('Theme', self)
        self.accent_color = theme.DEFAULT_ACCENT
        self._album_accents = {}
        self._last_palette_colors = []
        self._palette_thread = None
        self._accent_match = self.settings.value('accent_match', 'true') == 'true'
        # Live accent preview: hovering a swatch applies it immediately;
        # closing the menu without a pick restores what was there before
        self._accent_before_menu = None
        self._accent_committed = False
        self.colour_menu.aboutToShow.connect(self._on_accent_menu_show)
        self.colour_menu.aboutToHide.connect(self._on_accent_menu_hide)
        self._populate_accent_menu([])

        self.help_menu = QMenu('Help', self)
        self.shortcuts_action = QAction('Display Shortcuts', self)
        self.shortcuts_action.setShortcut(QKeySequence('Shift+?'))
        self.shortcuts_action.triggered.connect(self.show_help)
        self.help_menu.addAction(self.shortcuts_action)
        self.about_action = QAction('About', self)
        self.about_action.triggered.connect(self.show_about)
        self.help_menu.addAction(self.about_action)

        # The ⋯ menu (control panel button, or right-click the art) holds
        # everything the old toolbar did besides mode switching
        self.main_menu = QMenu(self)
        self.main_menu.addMenu(self.colour_menu)
        self.main_menu.addMenu(self.prefs_menu)
        self.main_menu.addSeparator()
        self.max_action = QAction('Max Mode', self)
        self.max_action.setShortcut(QKeySequence('Shift+M'))
        self.max_action.setShortcutContext(Qt.WidgetShortcut)  # display only
        self.max_action.triggered.connect(self.toggle_maxplayer)
        self.main_menu.addAction(self.max_action)
        self.on_top_action = QAction('Always on Top', self)
        self.on_top_action.setCheckable(True)
        self.on_top_action.setShortcut(QKeySequence('Shift+T'))
        self.on_top_action.setShortcutContext(Qt.WidgetShortcut)  # display only
        self.on_top_action.toggled.connect(self._set_on_top)
        self.main_menu.addAction(self.on_top_action)
        self.station_art_action = QAction('Change Station Art...', self)
        self.station_art_action.triggered.connect(self._pick_station_art)
        self.main_menu.addAction(self.station_art_action)
        self.main_menu.aboutToShow.connect(self._on_main_menu_show)
        self.main_menu.addSeparator()
        self.main_menu.addMenu(self.help_menu)
        self.quit_action = QAction('Quit', self)
        self.quit_action.setShortcut(QKeySequence('Q'))
        self.quit_action.setShortcutContext(Qt.WidgetShortcut)  # display only
        self.quit_action.triggered.connect(self.close)
        self.main_menu.addAction(self.quit_action)

        # Max mode state — the MaxView page is created lazily on first use
        self.is_maxplayer = False
        self._max_view = None

        # Media server (Remote Access) — created lazily when enabled
        self._media_server = None
        self._media_server_error = ''

        # Theme setup. Appearance settings are restored BEFORE the first
        # apply_theme so the app starts directly in its saved look — apply
        # light first and re-apply dark during state restore and Qt's
        # repolish of a second pre-show stylesheet quietly skips some
        # subtrees (the player column / file browser kept the light
        # background on dark-mode launches).
        saved_sz = (self.settings.value('font_size', type=int)
                    or self.settings.value('font_size_controls', type=int))
        if saved_sz:
            lo, hi = theme.SIZES[0], theme.SIZES[-1]
            self.font_size = max(lo, min(hi, saved_sz))
        saved_opacity = self.settings.value('overlay_opacity', type=int)
        if saved_opacity is not None:
            self.overlay_opacity = max(0, min(100, saved_opacity))
        saved_accent = self.settings.value('accent_color')
        if saved_accent:
            self.accent_color = saved_accent
        saved_album_accents = self.settings.value('album_accents')
        if saved_album_accents and isinstance(saved_album_accents, dict):
            self._album_accents = saved_album_accents
        self.current_theme = (theme.DARK
                              if self.settings.value('dark_mode') == 'true'
                              else theme.LIGHT)
        self.accent_color = ensure_contrast(self.accent_color,
                                            self.current_theme['bg'])
        self.apply_theme(self.current_theme)

        self.album_view.album_changed.connect(self._on_album_changed)

        # Restore saved state
        self._restore_state()

        self.lyrics_widget.setFocusPolicy(Qt.NoFocus)
        self.lyrics_widget.seek_requested.connect(self._on_lyrics_seek)

        # Focus change tracking for pane highlighting (property-driven)
        for view in (self.folder_view.view, self.album_view.track_list_widget):
            view.setProperty('paneFocused', False)
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

        # Tab key cycles between the library pane and the tracklist
        self.folder_view.view.installEventFilter(self)
        self.album_view.track_list_widget.installEventFilter(self)
        self.favorites_view.coll_list.installEventFilter(self)

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
        t['overlay_opacity'] = self.overlay_opacity
        self.effective_theme = t

        self.setStyleSheet(theme.build_qss(t, self.font_size))
        self.player.set_control_scale(self.font_size)
        self.player.panel.set_theme(t, self.font_size)
        self.library_pane.set_icons(self._toolbar_icon)
        self.lyrics_widget.set_theme(t, self.font_size)
        # Accent heart icons in the tracklist / favourites list follow the
        # accent too
        self.album_view.set_heart_color(accent, t['accent_fg'])
        self.favorites_view.set_heart_color(accent, t['accent_fg'])
        if self.is_maxplayer:
            self._style_max_mode()

    def _toolbar_icon(self, name, size=20):
        """A stateful QIcon for the mode tabs: fg_dim normally, fg on
        hover, accent when checked."""
        t = self.effective_theme
        icon = QIcon()
        icon.addPixmap(_render_svg(name, t['fg_dim'], size), QIcon.Normal, QIcon.Off)
        icon.addPixmap(_render_svg(name, t['fg'], size), QIcon.Active, QIcon.Off)
        icon.addPixmap(_render_svg(name, t['accent'], size), QIcon.Normal, QIcon.On)
        icon.addPixmap(_render_svg(name, t['accent'], size), QIcon.Active, QIcon.On)
        return icon

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
            self._last_palette_album = album_path
            self._palette_thread = PaletteExtractThread(str(self.player.album.art))
            self._palette_thread.palette_ready.connect(
                lambda colors, p=album_path: self._on_palette_extracted(colors, p))
            self._palette_thread.start()

    def set_font_size(self, size):
        self.font_size = size
        self.apply_theme(self.current_theme)

    def set_overlay_opacity(self, value):
        """Restyle only the overlay panels — a full apply_theme per slider
        tick would rebuild the app stylesheet and re-render every icon."""
        self.overlay_opacity = max(0, min(100, value))
        t = dict(self.effective_theme)
        t['overlay_opacity'] = self.overlay_opacity
        self.effective_theme = t
        self.player.panel.set_theme(t, self.font_size)
        if self._max_view:
            self._max_view.panel.set_theme(t, self.font_size)

    def _step_font_size(self, delta):
        sizes = theme.SIZES
        try:
            idx = sizes.index(self.font_size)
        except ValueError:
            idx = sizes.index(theme.DEFAULT_SIZE)
        idx = max(0, min(len(sizes) - 1, idx + delta))
        self.set_font_size(sizes[idx])

    def set_accent(self, color):
        self.accent_color = color
        # Save per-album preference
        if self.player.album and self.player.album.path:
            self._album_accents[self.player.album.path] = color
        self.apply_theme(self.current_theme)

    def _open_text_size(self):
        """One text-size control for the whole app: a slider over the size
        scale with a live 'Aa' preview. Changes apply immediately; Cancel
        puts the original size back."""
        dlg = QDialog(self)
        dlg.setWindowTitle('Text Size')
        dlg.setMinimumWidth(320)
        dlg.setStyleSheet(theme.dialog_qss(self.effective_theme))
        t = self.effective_theme
        sizes = theme.SIZES
        original = self.font_size
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        preview = QLabel('Aa')
        preview.setAlignment(Qt.AlignCenter)
        preview.setFixedHeight(64)

        size_label = QLabel()
        size_label.setAlignment(Qt.AlignCenter)
        size_label.setStyleSheet(f'color: {t["fg_dim"]};')

        row = QHBoxLayout()
        small_a = QLabel('A')
        small_a.setStyleSheet(f'font-size: 9pt; color: {t["fg_dim"]};')
        big_a = QLabel('A')
        big_a.setStyleSheet(f'font-size: 15pt; color: {t["fg_dim"]};')
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, len(sizes) - 1)
        try:
            slider.setValue(sizes.index(self.font_size))
        except ValueError:
            slider.setValue(sizes.index(theme.DEFAULT_SIZE))
        slider.setPageStep(1)
        slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 4px; background: {t['hover']}; border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {t['accent']}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 16px; height: 16px; margin: -6px 0;
                border-radius: 8px; background: {t['accent']};
            }}
        """)
        row.addWidget(small_a)
        row.addWidget(slider, stretch=1)
        row.addWidget(big_a)

        def _apply(idx):
            size = sizes[idx]
            preview.setStyleSheet(
                f'font-size: {size + 6}pt; color: {t["fg"]};')
            size_label.setText(f'{size} pt')
            if size != self.font_size:
                self.set_font_size(size)
        slider.valueChanged.connect(_apply)
        _apply(slider.value())

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        reset_btn = buttons.addButton('Reset', QDialogButtonBox.ResetRole)
        reset_btn.clicked.connect(
            lambda: slider.setValue(sizes.index(theme.DEFAULT_SIZE)))
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        layout.addWidget(preview)
        layout.addLayout(row)
        layout.addWidget(size_label)
        layout.addSpacing(4)
        layout.addWidget(buttons)

        if dlg.exec_() != QDialog.Accepted and self.font_size != original:
            self.set_font_size(original)

    def _open_overlay_opacity(self):
        """Slider for the mini/max hover panel's scrim darkness — glassy
        (see more art through it) to solid (safer contrast for text).
        Changes apply immediately; Cancel puts the original value back."""
        dlg = QDialog(self)
        dlg.setWindowTitle('Overlay Opacity')
        dlg.setMinimumWidth(320)
        dlg.setStyleSheet(theme.dialog_qss(self.effective_theme))
        t = self.effective_theme
        original = self.overlay_opacity
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        # A fake "art" backdrop with a translucent scrim label on top —
        # mirrors the real layering (overlay over album art) so the slider
        # previews actual legibility, not just an abstract alpha value.
        preview = QWidget()
        preview.setFixedHeight(64)
        preview.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {t['accent']}, stop:1 {t['bg_elevated']});")
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(20, 12, 20, 12)
        scrim = QLabel('lp')
        scrim.setAlignment(Qt.AlignCenter)
        scrim.setAttribute(Qt.WA_StyledBackground, True)
        preview_layout.addWidget(scrim)

        value_label = QLabel()
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet(f'color: {t["fg_dim"]};')

        row = QHBoxLayout()
        glassy = QLabel('Glassy')
        glassy.setStyleSheet(f'color: {t["fg_dim"]};')
        solid = QLabel('Solid')
        solid.setStyleSheet(f'color: {t["fg_dim"]};')
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(self.overlay_opacity)
        slider.setPageStep(5)
        slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 4px; background: {t['hover']}; border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {t['accent']}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 16px; height: 16px; margin: -6px 0;
                border-radius: 8px; background: {t['accent']};
            }}
        """)
        row.addWidget(glassy)
        row.addWidget(slider, stretch=1)
        row.addWidget(solid)

        def _apply(value):
            alpha = overlay_controls.scrim_alpha(value)
            scrim.setStyleSheet(
                f'color: white; font-weight: bold; font-size: 14pt; '
                f'border-radius: {overlay_controls.PANEL_RADIUS}px; '
                f'background-color: rgba(20, 20, 20, {alpha});')
            value_label.setText(f'{value}%')
            if value != self.overlay_opacity:
                self.set_overlay_opacity(value)
        slider.valueChanged.connect(_apply)
        _apply(slider.value())

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        reset_btn = buttons.addButton('Reset', QDialogButtonBox.ResetRole)
        reset_btn.clicked.connect(
            lambda: slider.setValue(overlay_controls.DEFAULT_OPACITY))
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        layout.addWidget(preview)
        layout.addLayout(row)
        layout.addWidget(value_label)
        layout.addSpacing(4)
        layout.addWidget(buttons)

        if dlg.exec_() != QDialog.Accepted and self.overlay_opacity != original:
            self.set_overlay_opacity(original)

    def pick_custom_accent(self):
        """Colour dialog with live preview — the accent follows the dialog's
        current colour; Cancel restores the original."""
        original = self.accent_color
        dlg = QColorDialog(QColor(original), self)
        dlg.setWindowTitle('Pick Accent Color')
        dlg.currentColorChanged.connect(
            lambda c: self._preview_accent(c.name()) if c.isValid() else None)
        if dlg.exec_() == QDialog.Accepted and dlg.selectedColor().isValid():
            self.set_accent(dlg.selectedColor().name())
        else:
            self._preview_accent(original)

    def _populate_accent_menu(self, album_colors):
        """Rebuild the colour menu: theme toggle, album swatches, presets."""
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
            self._add_swatch_section('Album', album_colors)
            self.colour_menu.addSeparator()
        # Preset colours (named — names show as tooltips)
        self._add_swatch_section(
            'Presets', list(theme.ACCENT_PRESETS.values()),
            names={v: k for k, v in theme.ACCENT_PRESETS.items()})
        self.colour_menu.addSeparator()
        custom_action = QAction('Custom...', self)
        custom_action.triggered.connect(self.pick_custom_accent)
        self.colour_menu.addAction(custom_action)

    def _add_swatch_section(self, label, colors, names=None):
        header = QAction(label, self)
        header.setEnabled(False)
        self.colour_menu.addAction(header)
        grid = AccentSwatchGrid(
            colors, getattr(self, 'effective_theme', theme.LIGHT),
            current=self.accent_color, names=names)
        grid.hovered.connect(self._on_swatch_hovered)
        grid.picked.connect(self._on_swatch_picked)
        act = QWidgetAction(self)
        act.setDefaultWidget(grid)
        self.colour_menu.addAction(act)

    # ── Accent live preview ─────────────────────────────────────────

    def _preview_accent(self, color):
        """Apply an accent visually without recording it anywhere."""
        if color and color != self.accent_color:
            self.accent_color = color
            self.apply_theme(self.current_theme)

    def _on_accent_menu_show(self):
        self._accent_before_menu = self.accent_color
        self._accent_committed = False

    def _on_accent_menu_hide(self):
        # Closed without picking — put the original accent back
        if not self._accent_committed:
            self._preview_accent(self._accent_before_menu)

    def _on_swatch_hovered(self, color):
        # '' means the cursor left the swatch grid — revert the preview.
        # Qt delivers a Leave event to the grid when the menu is hidden out
        # from under the cursor (e.g. right after a click commits a pick),
        # so once committed this must be a no-op or it stomps the commit.
        if self._accent_committed:
            return
        self._preview_accent(color or self._accent_before_menu)

    def _on_swatch_picked(self, color):
        self._accent_committed = True
        self.set_accent(color)
        self.colour_menu.hide()
        self.main_menu.hide()
        # Rebuild so the picked swatch carries the 'current' ring next open
        self._populate_accent_menu(self._last_palette_colors)

    def _toggle_accent_match(self, checked):
        # Clicking this QAction closes colour_menu, firing aboutToHide ->
        # _on_accent_menu_hide; mark committed so it doesn't revert the
        # accent that _update_accent_for_album just applied.
        self._accent_committed = True
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
        # If we have a saved accent, apply it immediately (no extraction
        # needed) — and skip the full restyle when it's already the accent
        if album_path in self._album_accents:
            saved = self._album_accents[album_path]
            if saved != self.accent_color:
                self.accent_color = saved
                self.apply_theme(self.current_theme)
        # Extract palette in background thread. A still-running extraction
        # for the previous album is disconnected and retired (never dropped
        # while running — QThread abort — and never waited on).
        old = self._palette_thread
        if old is not None:
            try:
                old.palette_ready.disconnect()
            except TypeError:
                pass
            bg_threads.retire(old)
        self._palette_thread = PaletteExtractThread(str(self.player.album.art))
        self._palette_thread.palette_ready.connect(
            lambda colors, p=album_path: self._on_palette_extracted(colors, p))
        self._palette_thread.start()

    def _on_palette_extracted(self, colors, album_path):
        """Handle palette extraction results from background thread."""
        if album_path != getattr(self, '_last_palette_album', None):
            return  # stale result from a superseded extraction
        if not colors:
            return
        self._last_palette_colors = colors
        if album_path not in self._album_accents:
            self._album_accents[album_path] = most_readable(colors) or colors[0]
        self._populate_accent_menu(colors)
        # The palette only feeds the accent menu when this album already
        # had a saved accent (applied up front by _update_accent_for_album)
        # — a full stylesheet rebuild is only needed if the accent changed
        accent = self._album_accents[album_path]
        if accent != self.accent_color:
            self.accent_color = accent
            self.apply_theme(self.current_theme)

    def _pick_library(self):
        """Let user pick the root music library folder."""
        current = self.settings.value('library_root', '')
        path = QFileDialog.getExistingDirectory(
            self, 'Select Music Library Folder', current)
        if path:
            self.folder_view.set_root(path)
            self.settings.setValue('library_root', path)
            if self._media_server:
                self._media_server.set_library_root(path)

    # ── Remote Access (media server) ────────────────────────────────

    def _start_media_server(self):
        """Start the phone-streaming HTTP server. Failure (e.g. port in
        use) is recorded for the dialog, never raised."""
        if self._media_server and self._media_server.running:
            return
        from media_server import MediaServer, DEFAULT_PORT, generate_token
        token = self.settings.value('server/token', '')
        if not token:
            token = generate_token()
            self.settings.setValue('server/token', token)
        port = int(self.settings.value('server/port', DEFAULT_PORT))
        root = self.settings.value('library_root', '')
        self._media_server_error = ''
        if not root:
            self._media_server_error = 'no music library folder set'
            return
        try:
            self._media_server = MediaServer(root, port, token)
            self._media_server.start()
        except OSError as e:
            self._media_server_error = str(e)
            self._media_server = None

    def _stop_media_server(self):
        if self._media_server:
            self._media_server.stop()
            self._media_server = None

    def _open_remote_dialog(self):
        from server_dialog import ServerDialog
        ServerDialog(self).exec_()

    def _open_stats_page(self):
        """Open the year-in-review stats page in the default browser.
        Starts the server one-shot if needed — without flipping
        server/enabled, so this never opts the user into LAN serving."""
        if not (self._media_server and self._media_server.running):
            self._start_media_server()
        if not (self._media_server and self._media_server.running):
            QMessageBox.warning(
                self, 'Listening Stats',
                f'Could not start the local server: '
                f'{self._media_server_error or "unknown error"}')
            return
        s = self._media_server
        QDesktopServices.openUrl(
            QUrl(f'http://127.0.0.1:{s.port}/stats?token={s.token}'))

    def _warn_if_playlist_art(self):
        """Album art actions operate on a real album folder; a Playlist has
        no folder of its own (its .path drifts to whatever song is
        currently playing — see App._on_track_changed). Block the action
        with a clear message instead of silently no-opping or, worse,
        writing cover.jpg into an unrelated album's folder."""
        if isinstance(self.player.album, Playlist):
            QMessageBox.information(
                self, 'Album Art',
                "Album art actions aren't available for playlists or "
                'favourites — play from an album to edit its art.')
            return True
        return False

    def _change_album_art(self):
        """Open artwork finder to search for new album cover."""
        if not self.player.album or not self.player.album.path:
            return
        if self._warn_if_playlist_art():
            return
        from artwork_finder import ArtworkFinderDialog
        t = self.effective_theme
        dialog = ArtworkFinderDialog(
            self.player.album.artist, self.player.album.title,
            self.player.album.path, t, parent=self, fs=self.font_size
        )
        dialog.artwork_saved.connect(self.player._on_artwork_saved)
        dialog.artwork_saved.connect(lambda _: self._update_accent_for_album(force=True))
        dialog.exec_()

    def _add_album_art(self):
        """Copy image files (back covers, inserts, lyric sheets...) into the
        album folder — they join the scrollable art gallery."""
        album = self.player.album
        if not album:
            return
        if self._warn_if_playlist_art():
            return
        if not hasattr(album, 'refresh_art'):
            return
        import shutil
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Add Album Art', '', 'Images (*.jpg *.jpeg *.png)')
        if not paths:
            return
        dest_dir = Path(album.path)
        for p in paths:
            src = Path(p)
            dest = dest_dir / src.name
            n = 1
            while dest.exists():
                dest = dest_dir / f'{src.stem}_{n}{src.suffix}'
                n += 1
            try:
                shutil.copy2(src, dest)
            except OSError as e:
                print(f'LOG: could not copy artwork: {e}')
        self.player.refresh_art_gallery()

    def _find_extra_art(self):
        """Search online for additional artwork — saved alongside the cover
        instead of replacing it."""
        album = self.player.album
        if not album:
            return
        if self._warn_if_playlist_art():
            return
        if not hasattr(album, 'refresh_art'):
            return
        from artwork_finder import ArtworkFinderDialog
        dialog = ArtworkFinderDialog(
            album.artist, album.title, album.path,
            self.effective_theme, parent=self, extra=True, fs=self.font_size)
        dialog.artwork_saved.connect(
            lambda _: self.player.refresh_art_gallery())
        dialog.exec_()

    # ── Session Persistence ─────────────────────────────────────────

    def _restore_state(self):
        library_root = self.settings.value('library_root')
        if library_root:
            self.folder_view.set_root(library_root)
            self.quick_switcher.refresh(self.library_cache, library_root)
        # Remote access autostarts if it was enabled last session; a bind
        # failure is remembered for the dialog and must not break startup
        if self.settings.value('server/enabled', 'false') == 'true':
            try:
                self._start_media_server()
            except Exception:
                pass
        # Window: always-on-top pin, geometry, side panes. A v1 install
        # carries its mini-mode geometry over (the v1 main window's wide
        # three-column geometry would make no sense here).
        if self.settings.value('stage/on_top') == 'true':
            self.on_top_action.setChecked(True)
        geometry = (self.settings.value('stage/geometry')
                    or self.settings.value('mini/geometry'))
        self._resizing_self = True
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(DEFAULT_SIDE + PANE_MIN_W, DEFAULT_SIDE)
        self._resizing_self = False
        # Side panes: geometry was saved with them open, so restoring them
        # must not widen the window again
        library_on = self.settings.value('stage/library')
        lyrics_on = self.settings.value('stage/lyrics')
        if library_on is None and lyrics_on is None and geometry is None:
            # First run: open on the library (sized for it just above)
            self._set_side_panes(library=True, resize_window=False)
        else:
            self._set_side_panes(library=library_on == 'true',
                                 lyrics=lyrics_on == 'true', resize_window=False)
        # Appearance (theme, accent, text size, opacity) was already
        # restored in __init__, before the one initial apply_theme.
        # Restore app mode (below). _mode is cleared first so _set_mode
        # doesn't treat it as re-picking the active mode.
        # Shuffle preference (setChecked routes through shuffle_toggled,
        # which sets player.shuffle)
        if self.settings.value('shuffle') == 'true':
            self.favorites_view.shuffle_btn.setChecked(True)
        saved_repeat = self.settings.value('repeat', 'off')
        if saved_repeat in ('off', 'all', 'one'):
            self.player.repeat_mode = saved_repeat
            self._sync_repeat_state()
        saved_mode = self.settings.value('app_mode', 'music')
        if saved_mode == 'podcast':
            self._mode = None
            self._set_mode('podcast', reveal=False)
            self._restore_podcast_state()
        elif saved_mode == 'radio':
            self._mode = None
            self._set_mode('radio', reveal=False)
            self._restore_radio_state()
        elif saved_mode == 'favorites':
            self._mode = None
            self._set_mode('favorites', reveal=False)
        else:
            self._mode = None
            self._set_mode('music', reveal=False)
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
            ('1',       'Music (again: hide)', lambda: self._mode_key('music')),
            ('2',       'Podcasts',            lambda: self._mode_key('podcast')),
            ('3',       'Radio',               lambda: self._mode_key('radio')),
            ('0',       'Favourites',          lambda: self._mode_key('favorites')),
            ('Shift+H', 'Toggle favourite',   self._toggle_current_favorite),
            ('4',       'Library: tracklist',  self._toggle_and_focus_tracklist),
            ('5',       'Toggle lyrics',       self.toggle_lyrics),
            ('n',       'Show now playing',    self._show_now_playing),
            ('s',       'Toggle shuffle',      self._toggle_shuffle),
            ('/',       'Search',              self._open_search),
            ('Ctrl+K',  'Jump to album',       self._open_quick_switcher),
            ('Shift+M', 'Toggle max mode',    self.toggle_maxplayer),
            ('Shift+T', 'Always on top',      self._toggle_on_top),
            ('Shift+D', 'Toggle dark/light',   self.toggle_theme),
            ('Ctrl++',  'Increase font size',  lambda: self._step_font_size(1)),
            ('Ctrl+-',  'Decrease font size',  lambda: self._step_font_size(-1)),
            ('Ctrl+=',  None,                  lambda: self._step_font_size(1)),
            ('q',       'Quit',                self.close),
            ('?',       'Show shortcuts',      self.show_help),
        ]
        # These keys are shown in help but handled by eventFilter/views, not QShortcut
        self._display_bindings = self.keybindings + [
            ('Tab',     'Library ⇄ tracklist', None),
            ('j / k',   'Navigate down / up',  None),
            ('h / l',   'Folder: collapse / expand; Tracklist: back to library', None),
            ('dbl-click art', 'Max mode',      None),
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

    # ── Window geometry: square art, panes widen the window ─────────

    def _edgeless(self):
        return self.isMaximized() or self.isFullScreen()

    def _set_side_panes(self, library=None, lyrics=None, resize_window=True):
        """Show/hide the library (left) and lyrics (right) panes.

        In a normal window the art column stays square (side = window
        height) and the window widens/narrows by a pane's width instead of
        squeezing the art. A plain resize keeps the window's top-left
        fixed, which would push the art rightward when the LEFT pane
        opens — setGeometry with a compensating x-shift keeps the art
        anchored under the cursor. Maximized windows just reflow.
        """
        if library is not None:
            self._library_on = library
        if lyrics is not None:
            self._lyrics_on = lyrics
        self.library_pane.setVisible(self._library_on)
        self.lyrics_pane.setVisible(self._lyrics_on)
        self.player.panel.set_toggle_states(self._library_on, self._lyrics_on)
        side = self.height() - 2  # inside root_stack's 1px border
        pane_w = max(PANE_MIN_W, side // 2)
        left_w = pane_w if self._library_on else 0
        if self._edgeless() or self.is_maxplayer:
            self._unpin_art_width()
            self._left_pane_w = left_w
            return
        if not resize_window:
            self._left_pane_w = left_w
            self._pin_art_width()
            return
        right_w = pane_w if self._lyrics_on else 0
        dx = left_w - self._left_pane_w
        self._left_pane_w = left_w
        x = self.x() - dx
        screen = self.screen()
        if screen is not None:  # never shift the window off-screen
            x = max(screen.availableGeometry().left(), x)
        self._resizing_self = True
        self._pin_art_width()
        self.setGeometry(x, self.y(), side + left_w + right_w + 2, self.height())
        self._resizing_self = False

    def _pin_art_width(self):
        """Art column square, panes take whatever width remains."""
        if self._library_on or self._lyrics_on:
            self.player.setFixedWidth(max(self.height() - 2, 120))
        else:
            self._unpin_art_width()

    def _unpin_art_width(self):
        self.player.setMinimumWidth(160)
        self.player.setMaximumWidth(16777215)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._grips.relayout()
        if self.quick_switcher.isVisible():
            self.quick_switcher._reposition()
        if self.is_maxplayer or self._edgeless():
            return
        if self._library_on or self._lyrics_on:
            self._pin_art_width()
        elif not self._resizing_self and self.width() != self.height():
            # Art only: keep the window square, following whichever edge
            # the user is dragging
            old = event.oldSize()
            if old.isValid() and abs(self.width() - old.width()) < \
                    abs(self.height() - old.height()):
                side = self.height()
            else:
                side = self.width()
            self._resizing_self = True
            self.resize(side, side)
            self._resizing_self = False

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self._update_window_state_chrome()

    def _update_window_state_chrome(self):
        """Keep the border/grips/art pinning in sync with window state.

        Frameless windows have no OS border, so the window's hairline
        outline (hidden while maximized/fullscreen, like a normal window's
        border merging with the screen edge) and the resize grips are
        driven from here.
        """
        maximized = self.isMaximized()
        edgeless = self._edgeless()
        self._grips.set_enabled(not edgeless)
        if edgeless:
            self._unpin_art_width()
        elif not self.is_maxplayer:
            self._pin_art_width()
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

    def _set_on_top(self, on):
        """Always-on-top pin (⋯ menu / Shift+T). Changing window flags
        hides the window, so it's re-shown if it was up."""
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        if visible:
            self.show()
        self.settings.setValue('stage/on_top', 'true' if on else 'false')

    def _toggle_on_top(self):
        # Flipping window flags re-shows the window, which would drop
        # max mode's fullscreen — the pin only applies to the stage
        if not self.is_maxplayer:
            self.on_top_action.setChecked(not self.on_top_action.isChecked())

    def _on_main_menu_show(self):
        self.station_art_action.setVisible(
            self._playing_mode == 'radio' and bool(self._current_radio_station))
        self.max_action.setText('Exit Max Mode' if self.is_maxplayer else 'Max Mode')
        self.on_top_action.setVisible(not self.is_maxplayer)

    def main_menu_popup(self, global_pos):
        self.main_menu.popup(global_pos)

    def _popup_menu_at_more(self):
        panel = self._max_view.panel if self.is_maxplayer else self.player.panel
        btn = panel.more_btn
        self.main_menu.popup(btn.mapToGlobal(QPoint(0, btn.height())))

    def _max_key_map(self):
        """Single-key shortcuts active in max mode. Shared by keyPressEvent
        (App itself has focus) and eventFilter (a borrowed widget — the
        tracklist, the lyrics pane — has focus and would otherwise swallow
        the key before it ever reaches App, e.g. VimListWidget consuming
        printable keys)."""
        return {
            Qt.Key_P: self._shortcut_play_pause,
            Qt.Key_Greater: self._shortcut_next,
            Qt.Key_Less: self._shortcut_prev,
            Qt.Key_F: self._shortcut_seek_forward,
            Qt.Key_B: self._shortcut_seek_back,
            Qt.Key_Period: lambda: self._adjust_volume(0.05),
            Qt.Key_Comma: lambda: self._adjust_volume(-0.05),
            Qt.Key_4: self.toggle_tracklist,
            Qt.Key_5: self.toggle_lyrics,
            Qt.Key_S: self._toggle_shuffle,
            Qt.Key_Left: lambda: self.player.step_art(-1),
            Qt.Key_Right: lambda: self.player.step_art(1),
            Qt.Key_Q: self.close,
            Qt.Key_Question: self.show_help,
        }

    def _dispatch_max_key(self, key, mods):
        """Try to handle a key press as a max-mode shortcut. Returns True if
        handled. Shared by keyPressEvent and eventFilter — see
        _max_key_map."""
        if key == Qt.Key_Escape:
            self.toggle_maxplayer()
            return True
        if key == Qt.Key_M and mods & Qt.ShiftModifier:
            self.toggle_maxplayer()
            return True
        if key == Qt.Key_D and mods & Qt.ShiftModifier:
            self.toggle_theme()
            return True
        if key == Qt.Key_H and mods & Qt.ShiftModifier:
            self._toggle_current_favorite()
            return True
        if mods & Qt.ControlModifier:
            # Text size works in every mode — no dropping back to the
            # normal window just to resize
            if key in (Qt.Key_Equal, Qt.Key_Plus):
                self._step_font_size(1)
                return True
            if key == Qt.Key_Minus:
                self._step_font_size(-1)
                return True
            return False
        handler = self._max_key_map().get(key)
        if handler:
            handler()
            return True
        return False

    def keyPressEvent(self, event):
        """Handle key presses — dispatch shortcuts in max mode."""
        if self.is_maxplayer and self._dispatch_max_key(event.key(), event.modifiers()):
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        """Intercept Tab/vim keys and suppress click-through on refocus."""
        t = event.type()
        if (t == event.KeyPress and self.is_maxplayer and self._max_view is not None
                and isinstance(obj, QWidget)
                and (obj is self._max_view or self._max_view.isAncestorOf(obj))
                and not isinstance(obj, QLineEdit)):
            # A borrowed widget (the tracklist, the lyrics pane) has focus —
            # key presses go to it first and e.g. VimListWidget swallows
            # printable keys, so '4'/'5'/'p'/etc would never reach
            # App.keyPressEvent. Intercept max-mode shortcuts here instead.
            if self._dispatch_max_key(event.key(), event.modifiers()):
                return True
        if t == event.KeyPress and not isinstance(self.focusWidget(), QLineEdit):
            key = event.key()
            if key == Qt.Key_Tab:
                self._cycle_pane_focus()
                return True
            # h/l on the tracklist → up to the library page
            if obj is self.album_view.track_list_widget and key in (Qt.Key_H, Qt.Key_L):
                self._show_library_page()
                return True
            # l on a favourites collection → load it and drill down
            if obj is self.favorites_view.coll_list and key == Qt.Key_L:
                item = self.favorites_view.coll_list.currentItem()
                if item is not None:
                    self._load_favorites_collection(item.data(Qt.UserRole))
                return True
            if obj is self.folder_view.view:
                idx = self.folder_view.view.currentIndex()
                # l on a music directory → load album and drill down
                if key == Qt.Key_L and idx.isValid():
                    path = self.folder_view.model.filePath(idx)
                    if self.folder_view._has_music(path):
                        self.album_view.load_album_listing(path)
                        self._drill_to_tracks()
                        return True
                # h at top level → back down to the tracklist
                if key == Qt.Key_H and self.album_view.album is not None:
                    root = self.folder_view.view.rootIndex()
                    at_top = not idx.isValid() or (not self.folder_view.view.isExpanded(idx)
                                                   and idx.parent() == root)
                    if at_top:
                        self._drill_to_tracks()
                        return True
        return super().eventFilter(obj, event)

    # ── Library pane: library ⇄ tracks drill-down ───────────────────

    def _drill_to_tracks(self, focus=True):
        """Show the tracks page (opening the library pane if needed). In
        max mode — no library pane on screen — show max mode's tracklist
        pane instead, so everything that opens a listing (Ctrl+K, n, a
        feed or collection) works there too."""
        if self.is_maxplayer:
            self.library_pane.show_tracks()  # where it'll be after max mode
            if self._max_view and not self._max_view.tracklist_on:
                self._max_view.set_tracklist_visible(True)
            self._update_now_playing_link()
            if focus:
                self._focus_tracklist()
            return
        self.library_pane.show_tracks()
        if not self._library_on:
            self._set_side_panes(library=True)
        self._update_now_playing_link()
        if focus:
            self._focus_tracklist()

    def _show_library_page(self, focus=True):
        """Back up to the current mode's library page."""
        if self.is_maxplayer:
            return
        self.library_pane.show_library()
        if not self._library_on:
            self._set_side_panes(library=True)
        if focus:
            self._library_focus_widget().setFocus()

    def _toggle_and_focus_tracklist(self):
        """'4' / the panel's tracklist button: close the pane if it's
        already showing tracks, otherwise open it on the tracks page (or
        the library page when nothing has been opened yet)."""
        if self.is_maxplayer:
            self._toggle_max_tracklist()
            return
        if self._library_on and self.library_pane.on_tracks_page():
            self._set_side_panes(library=False)
            self.player.setFocus()
        elif self.album_view.album is None and not self.album_view.track_list_widget.count():
            self._show_library_page()
        else:
            self._drill_to_tracks()

    def _focus_tracklist(self):
        """Focus the tracklist, making sure a row is highlighted so the
        focus jump is visible — the playing track if it's in this list,
        otherwise the first track."""
        lst = self.album_view.track_list_widget
        lst.setFocus()
        if lst.currentRow() < 0 and lst.count():
            row = 0
            if (self.player.current_track and self.player.playlist
                    and same_listing(self.player.playlist, self.album_view.album)):
                row = self.player.playlist_pos
            lst.setCurrentRow(row)

    def _show_now_playing(self):
        """'n' / the pane's 'Now playing' link: list the playing album or
        collection on the tracks page, without re-reading it from disk."""
        playing = self.player.playlist
        if isinstance(playing, Album):
            self.album_view.show_album(playing)
            self.library_pane.set_tracks_title(self._album_title(playing))
        elif getattr(playing, 'is_playlist', False):
            self.album_view.load_playlist(playing)
            self.library_pane.set_tracks_title(playing.title)
        else:
            return
        self.album_view.track_list_widget.setCurrentRow(self.player.playlist_pos)
        self._drill_to_tracks()

    def _open_quick_switcher(self):
        """Ctrl+K: search every album in the library by artist/album."""
        root = self.settings.value('library_root')
        if not root:
            return
        self.quick_switcher.refresh(self.library_cache, root)
        self.quick_switcher.open()

    def _open_album_by_id(self, album_id):
        """Open a quick-switcher pick (relpath under the library root) in
        the library pane's tracklist — switching to music mode if needed,
        and selecting the folder in the tree for when you go back up."""
        root = self.settings.value('library_root')
        if not root:
            return
        path = root if album_id == '.' else str(Path(root) / album_id)
        if self._mode != 'music':
            self._set_mode('music', reveal=False)
        idx = self.folder_view.model.index(path)
        if idx.isValid():
            self.folder_view.view.setCurrentIndex(idx)
            self.folder_view.view.scrollTo(idx)
        self.album_view.load_album_listing(path)
        self._drill_to_tracks()

    def _update_now_playing_link(self):
        playing = self.player.playlist
        browsing_elsewhere = (
            (isinstance(playing, Album) or getattr(playing, 'is_playlist', False))
            and not same_listing(playing, self.album_view.album))
        self.library_pane.now_playing_btn.setVisible(browsing_elsewhere)

    @staticmethod
    def _album_title(album):
        if album.artist and album.title:
            return f'{album.artist} — {album.title}'
        return album.title or ''

    def _open_search(self):
        """Open the search bar of the focused pane (folder view by default;
        in max mode, the tracklist — the only list on screen there)."""
        if self.is_maxplayer:
            if not self._max_view.tracklist_on:
                self._max_view.set_tracklist_visible(True)
            bar = self.album_view.search_bar
        elif self.album_view.track_list_widget.hasFocus():
            bar = self.album_view.search_bar
        else:
            bar = self.folder_view.search_bar
        bar.setVisible(True)
        bar.setFocus()
        bar.clear()

    def _library_focus_widget(self):
        """The focusable list of whichever library view is showing."""
        current = self.left_stack.currentWidget()
        if current is self.podcast_view:
            return self.podcast_view.feed_list
        if current is self.radio_view:
            return self.radio_view.station_list
        if current is self.favorites_view:
            return self.favorites_view.coll_list
        return self.folder_view.view

    def _cycle_pane_focus(self):
        """Tab: flip the library pane between its two pages."""
        if self.library_pane.on_tracks_page():
            self._show_library_page()
        elif self.album_view.album is not None:
            self._drill_to_tracks()

    def _on_focus_changed(self, old, new):
        """Flip the 'paneFocused' property on the panes whose state changed.

        The stylesheet targets [paneFocused="true"] selectors, so only the
        affected view is repolished — no stylesheet regeneration.
        """
        # Focus leaving the album switcher (clicked elsewhere) closes it
        if (self.quick_switcher.isVisible()
                and not self.quick_switcher.contains_focus(new)):
            self.quick_switcher.hide()
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
            f'<p>Version {__version__}</p>'
            '<p>By Johnathan Milley</p>'
            '<p>Licensed under the MIT License</p>'
            '</div>'
        )
        label.setTextFormat(Qt.RichText)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        dialog.setLayout(layout)
        dialog.exec_()

    # ── Album / lyrics panes ─────────────────────────────────────────

    def _on_album_changed(self, title):
        """A browsed album finished loading into the tracklist."""
        album = self.album_view.album
        self.library_pane.set_tracks_title(self._album_title(album))
        self._update_now_playing_link()
        # Nothing playing yet: the browsed album is previewing its art
        # (see AlbumView._on_album_loaded), so its accent follows too
        if self.player.album is album:
            self._update_accent_for_album()
        # Restore saved track position after startup album load
        pending = getattr(self, '_pending_music_restore', None)
        if pending:
            del self._pending_music_restore
            self.library_pane.show_tracks()  # reopen on the restored album
            track_pos = pending['track_pos']
            seek_pos = pending['seek_pos']
            if self.album_view.album and track_pos < len(self.album_view.album.tracklist):
                self.player.load_track(self.album_view.album, track_pos, seek_pos)

    def toggle_lyrics(self):
        if self.is_maxplayer:
            self._toggle_max_lyrics()
        else:
            self._set_side_panes(lyrics=not self._lyrics_on)

    def toggle_tracklist(self):
        """Max mode's tracklist toggle ('4' while in max)."""
        if self.is_maxplayer:
            self._toggle_max_tracklist()
        else:
            self._toggle_and_focus_tracklist()

    def _toggle_max_lyrics(self):
        if self._max_view:
            self._max_view.set_lyrics_visible(not self._max_view.lyrics_on)

    def _toggle_max_tracklist(self):
        if self._max_view:
            self._max_view.set_tracklist_visible(not self._max_view.tracklist_on)

    # ── Lyrics & Track Change Handling ─────────────────────────────

    def _on_listen_ended(self, track, listened):
        """A track's playback ended (replaced or app closing) — log it as a
        play if enough of it was actually heard. Music only; must never be
        able to break playback."""
        try:
            if hasattr(track, 'audio_url'):    # podcast (radio never gets here)
                return
            if not play_log.should_count(track.length, listened):
                return
            album_id = None
            root = self.settings.value('library_root', '')
            if root and track.path:
                try:
                    album_id = Path(track.path).parent.relative_to(root).as_posix()
                except ValueError:
                    pass    # played from outside the library — still logged
            record = play_log.make_record(
                artist=track.artist, album=track.album,
                title=track.title or track.filename, n=track.tracknumber,
                length=track.length, listened=listened, album_id=album_id)
            record['src'] = 'desktop'
            play_log.append(record)
        except Exception as e:
            print(f'LOG: play log write failed: {e}')

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
        self._sync_favorite_heart(track, track_mode)
        title = str(track.title or track.filename or '')
        self.lyrics_pane.set_title(title)
        artist = str(getattr(track, 'artist', '') or '')
        self.setWindowTitle(f'{title} — {artist}' if artist else (title or 'lp'))
        self._update_now_playing_link()
        if track_mode == 'music' and isinstance(self.player.playlist, Album):
            # The accent follows the PLAYING album (deduped per album path)
            self._update_accent_for_album()
        playlist = self.player.playlist
        from_playlist = getattr(playlist, 'is_playlist', False)
        if (track_mode == 'music' and playlist and not from_playlist
                and getattr(playlist, 'path', None)):
            self._playing_album_path = playlist.path
            self._playing_track_pos = self.player.playlist_pos
            self._playing_seek_pos = 0  # just started
        if track_mode == 'music' and from_playlist and track.path:
            # Playlist tracks span albums: point the playlist's path/art at
            # this song's album folder so lyrics caching and per-album
            # accents key exactly as if the album were playing, and show
            # the album cover alone (never the folder's full art gallery)
            folder = str(Path(track.path).parent)
            playlist.path = folder
            # Stat the (possibly NAS) cover only when the folder changes,
            # not on every track change
            if folder != self._last_playlist_folder:
                self._last_playlist_folder = folder
                cover = Path(folder) / 'cover.jpg'
                self._last_playlist_cover = cover if cover.exists() else None
                playlist.art = self._last_playlist_cover
                self.player.set_art_path(
                    str(self._last_playlist_cover) if self._last_playlist_cover else None)
                self._update_accent_for_album(force=True)
            else:
                playlist.art = self._last_playlist_cover
        # Podcast episodes show description instead of lyrics
        if track_mode == 'podcast' and hasattr(track, 'description'):
            self.lyrics_widget.set_description(track.description)
            return

        if not self.player.album or not getattr(self.player.album, 'path', None):
            return

        # Already tried and failed for this track
        track_key = f'{track.artist}:{track.title}:{track.album}'
        if track_key in self._failed_lyrics:
            self.lyrics_widget.set_lyrics('')
            return

        self.lyrics_widget.set_lyrics('Fetching lyrics...')
        # Supersede any in-progress fetch: disconnect its result and retire
        # the thread. Never wait() here — that blocked the UI for up to 2s
        # on every quick track switch, and when the wait timed out the
        # replaced thread object could be destroyed mid-run (the QThread
        # abort crash). The disk-cache check happens inside the thread too,
        # so cached lyrics no longer cost a synchronous NAS read (plus a
        # mkdir) on the UI thread for every track change.
        old = self._lyrics_thread
        if old is not None:
            try:
                old.lyrics_ready.disconnect(self._on_lyrics_fetched)
            except TypeError:
                pass
            bg_threads.retire(old)
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

        # The stage is untouched behind the stack — only the window
        # geometry needs restoring after fullscreen
        self._pre_max_geometry = self.saveGeometry()

        if self._max_view is None:
            self._max_view = MaxView(self.player)
            # Art click still exits max mode (only entry-by-click is removed
            # — see _on_art_clicked)
            self._max_view.art.clicked.connect(self.toggle_maxplayer)
            self._max_view.exit_requested.connect(self.toggle_maxplayer)
            self._max_view.panel.prev_clicked.connect(self._shortcut_prev)
            self._max_view.panel.play_clicked.connect(self._shortcut_play_pause)
            self._max_view.panel.next_clicked.connect(self._shortcut_next)
            self._max_view.panel.tracklist_clicked.connect(self._toggle_max_tracklist)
            self._max_view.panel.lyrics_clicked.connect(self._toggle_max_lyrics)
            self._max_view.panel.heart_clicked.connect(self._toggle_current_favorite)
            self._max_view.panel.shuffle_clicked.connect(self._toggle_shuffle)
            self._max_view.panel.repeat_clicked.connect(self._toggle_repeat)
            self._max_view.panel.more_clicked.connect(self._popup_menu_at_more)
            self._max_view.art.setContextMenuPolicy(Qt.CustomContextMenu)
            self._max_view.art.customContextMenuRequested.connect(
                lambda pos: self.main_menu_popup(self._max_view.art.mapToGlobal(pos)))
            self.root_stack.addWidget(self._max_view)

        # Seed current state; player signals keep it in sync from here on
        track = self.player.current_track
        self._max_view.set_title(str(track.title) if track and track.title else '')
        self._max_view.set_playing(self.player._is_playing)
        self._sync_favorite_heart(track, self._playing_mode)
        self._sync_shuffle_state(self.player.shuffle)
        self._sync_repeat_state()
        art_px = self.player.album_widget.pixmap()
        if art_px:
            self._max_view.art.set_source(art_px)
        else:
            self._max_view.art.clear()

        # Borrow the one true lyrics widget and tracklist — same content,
        # same highlight/selection, no duplication
        self._max_view.attach_lyrics(self.lyrics_widget)
        self._max_view.attach_tracklist(self.album_view)

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
        fs = self.font_size + 8
        self.lyrics_widget.setStyleSheet(f"""
            #lyrics-text {{
                background-color: {t['bg']};
                color: {t['fg']};
                font-family: {theme.FONT};
                font-size: {fs}pt;
            }}
            {theme.minimal_scrollbar_qss(t)}
        """)
        self.lyrics_widget.set_theme(t, fs)
        self._max_view.set_close_icon_color(t['fg_dim'])
        self._max_view.panel.set_theme(t, self.font_size)

    def exit_maxplayer(self):
        if not self.is_maxplayer:
            return
        self.is_maxplayer = False

        # Return the borrowed lyrics widget and tracklist to their panes
        self.library_pane.tracks_slot.addWidget(self.album_view)
        self.lyrics_pane.slot.addWidget(self.lyrics_widget)
        self.lyrics_widget.setStyleSheet('')  # drop the max-mode font bump
        self.album_view.setVisible(True)
        self.lyrics_widget.setVisible(True)
        # Reset the side panes for the next entry: lyrics on, tracklist off
        self._max_view.set_lyrics_visible(True)
        self._max_view.set_tracklist_visible(False)

        self.root_stack.setCurrentWidget(self.stage)

        # Restyle (also restores the normal lyrics font size)
        self.apply_theme(self.current_theme)

        # Exit fullscreen and restore geometry
        self._resizing_self = True
        self.showNormal()
        self._was_inactive = False
        if self._pre_max_geometry:
            self.restoreGeometry(self._pre_max_geometry)
        self._resizing_self = False
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

    # ── Mode Switching (Music / Podcast / Radio / Favourites) ───────

    MODE_TITLES = {'music': 'Music', 'podcast': 'Podcasts',
                   'radio': 'Radio', 'favorites': 'Favourites'}

    def _mode_key(self, mode):
        """1/2/3/0. Max mode has no library pane to switch, so they're
        ignored there rather than changing a pane nobody can see."""
        if not self.is_maxplayer:
            self._set_mode(mode)

    def _set_mode(self, mode, reveal=True):
        """Switch the library pane between music, podcast, radio and
        favourites (the mode tabs, or 1/2/3/0).

        Picking the mode that's already active toggles the library pane
        instead: closed → open on the library page; open on the tracks
        page → back up to the library; open on the library → close.
        reveal=False (startup restore) switches without opening the pane.
        """
        if mode == self._mode:
            self.library_pane.set_mode(mode)  # undo the tab's own toggle
            if self._library_on and not self.library_pane.on_tracks_page():
                self._set_side_panes(library=False)
                self.player.setFocus()
            else:
                self._show_library_page()
            return
        self._save_music_position()
        self._save_podcast_position()
        if self._mode == 'music':
            self._save_music_folder_position()
        self._mode = mode
        self.library_pane.set_mode(mode)
        self.library_pane.set_library_title(self.MODE_TITLES[mode])

        if mode == 'podcast':
            self.left_stack.setCurrentWidget(self.podcast_view)
            self.podcast_view.load_saved_feeds()
        elif mode == 'radio':
            self.left_stack.setCurrentWidget(self.radio_view)
            self.radio_view.load_saved_stations()
        elif mode == 'favorites':
            self.left_stack.setCurrentWidget(self.favorites_view)
            self.favorites_view.refresh()
            self._connect_music_tracklist()
            self._load_favorites_collection(self.favorites_view.current_key(),
                                            drill=False)
        else:
            self.left_stack.setCurrentWidget(self.folder_view)
            self._restore_music_folder_position()
            self._connect_music_tracklist()

        # A new mode always starts on its library page
        if reveal:
            self._show_library_page()
        else:
            self.library_pane.show_library()

    def _connect_music_tracklist(self):
        """Point the tracklist's click/context-menu at the music handlers
        (music and favourites modes share them; podcast mode swaps in its
        own — see _on_podcast_feed_selected)."""
        widget = self.album_view.track_list_widget
        try:
            widget.itemClicked.disconnect()
        except TypeError:
            pass
        widget.itemClicked.connect(self.album_view.set_current_track)
        widget.setContextMenuPolicy(Qt.CustomContextMenu)
        try:
            widget.customContextMenuRequested.disconnect()
        except TypeError:
            pass
        widget.customContextMenuRequested.connect(
            self.album_view._open_context_menu)

    # ── Favourites mode ───────────────────────────────────────────

    def _load_favorites_collection(self, key, drill=True):
        """Show a favourites collection ('' = all) in the tracklist, and
        drill the library pane down to it unless drill=False."""
        records = self.fav_store.records_for(key)
        name = key or 'Favourites'
        playlist = Playlist(name, records, playlist_name=key)
        self.album_view.load_playlist(playlist)
        self.library_pane.set_tracks_title(name)
        if drill:
            self._drill_to_tracks()
        else:
            self._update_now_playing_link()

    def _on_favorites_changed(self):
        """A track was (un)favourited or moved between playlists."""
        self.favorites_view.refresh()
        # A displayed collection may now be stale — reload it in place
        if (self._mode == 'favorites'
                and getattr(self.album_view.album, 'is_playlist', False)):
            self._load_favorites_collection(
                self.album_view.album.playlist_name, drill=False)
        # The change may have been the currently playing track (e.g.
        # (un)favourited from the tracklist's context menu) — keep every
        # heart button in sync regardless of where the change came from
        self._sync_favorite_heart(self.player.current_track, self._playing_mode)

    def _sync_favorite_heart(self, track, track_mode):
        """Keep every heart button (stage and max-mode panels)
        in sync with the playing track — visible for real music tracks
        (incl. playlists/favourites, which are ordinary Track objects),
        hidden for podcast episodes."""
        favoritable = track_mode == 'music'
        is_fav = bool(favoritable and track and track.path
                      and self.fav_store.is_favorite(track.path))
        self.player.panel.set_heart_visible(favoritable)
        self.player.panel.set_favorited(is_fav)
        if self._max_view:
            self._max_view.set_heart_visible(favoritable)
            self._max_view.set_favorited(is_fav)

    def _toggle_current_favorite(self):
        """Heart button (stage or max-mode panel) —
        favourite/unfavourite the currently playing track. _on_favorites_changed
        (called at the end) re-syncs every heart button via _sync_favorite_heart."""
        track = self.player.current_track
        if not track or not track.path or hasattr(track, 'audio_url'):
            return
        self.fav_store.toggle(track)
        # Reflect on the tracklist too, if this track's album is loaded
        # there (accent heart icon; playlist listings don't show one)
        album = self.album_view.album
        if (not getattr(album, 'is_playlist', False) and album is self.player.album):
            pos = self.player.track_pos
            item = self.album_view.track_list_widget.item(pos)
            if item is not None:
                self.album_view._apply_heart(item, track)
        self._on_favorites_changed()

    def _on_shuffle_toggled(self, on):
        self.player.shuffle = on
        self.settings.setValue('shuffle', 'true' if on else 'false')
        self._sync_shuffle_state(on)

    def _sync_shuffle_state(self, on):
        """Keep every panel's shuffle button (stage, max mode) in
        sync — FavoritesView.shuffle_btn stays the single source of truth,
        this just mirrors it visually wherever else it's shown."""
        self.player.panel.set_shuffle_state(on)
        if self._max_view:
            self._max_view.panel.set_shuffle_state(on)

    def _toggle_shuffle(self):
        # The FavoritesView button is the single source of shuffle state
        self.favorites_view.shuffle_btn.toggle()

    def _toggle_repeat(self):
        """Cycle repeat off -> all -> one -> off, from any panel's repeat
        button (stage, max mode)."""
        order = ('off', 'all', 'one')
        self.player.repeat_mode = order[(order.index(self.player.repeat_mode) + 1) % 3]
        self.settings.setValue('repeat', self.player.repeat_mode)
        self._sync_repeat_state()

    def _sync_repeat_state(self):
        """Keep every panel's repeat button in sync with player.repeat_mode."""
        mode = self.player.repeat_mode
        self.player.panel.set_repeat_state(mode)
        if self._max_view:
            self._max_view.panel.set_repeat_state(mode)

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
        p.panel.set_seek_mode(True)
        p.panel.set_seek_visible(True)  # radio mode hides these
        self._reconnect_play_button()

    def _set_radio_controls(self):
        """Hide prev/next and progress bar — only play/pause for radio."""
        p = self.player
        p.panel.set_seek_visible(False)
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
        p.panel.set_seek_mode(False)
        p.panel.set_seek_visible(True)  # radio mode hides these
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
        self.player.panel.set_title(station.name)
        self.lyrics_pane.set_title(station.name)
        self.setWindowTitle(station.name)
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
        dlg = StationArtDialog(station.name, self.effective_theme, parent=self,
                               fs=self.font_size)
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
            self.player.panel.set_title(display)
            # Show now-playing in the lyrics panel (set HTML directly)
            import html as html_mod
            t = self.effective_theme
            fg = t.get('fg', '#e0e0e0')
            accent = t.get('accent_text', t['accent'])
            safe_title = html_mod.escape(title)
            safe_name = html_mod.escape(self._current_radio_station.name)
            fs = self.font_size
            self.lyrics_widget.set_status_html(
                f'<div style="text-align:center; padding:20px; font-family:{theme.FONT};">'
                f'<p style="font-size:{fs + 4}pt; color:{fg}; opacity:0.6;">Now Playing</p>'
                f'<p style="font-size:{fs + 6}pt; font-weight:bold; color:{accent};">{safe_title}</p>'
                f'<p style="font-size:{fs + 2}pt; color:{fg}; opacity:0.5;">{safe_name}</p>'
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
        self.player.panel.set_title(name)
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

        self.library_pane.set_tracks_title(feed.title)
        self._drill_to_tracks()

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
        self.player.panel.set_title(ep.title)
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
        if self.is_maxplayer and self._pre_max_geometry:
            self.settings.setValue('stage/geometry', self._pre_max_geometry)
        else:
            self.settings.setValue('stage/geometry', self.saveGeometry())
        self.settings.setValue('stage/library', 'true' if self._library_on else 'false')
        self.settings.setValue('stage/lyrics', 'true' if self._lyrics_on else 'false')
        self.settings.setValue('dark_mode', 'true' if self.current_theme is theme.DARK else 'false')
        self.settings.setValue('font_size', self.font_size)
        self.settings.setValue('overlay_opacity', self.overlay_opacity)
        self.settings.setValue('accent_color', self.accent_color)
        self.settings.setValue('album_accents', self._album_accents)
        self.settings.setValue('app_mode', self._playing_mode or self._mode)
        # Save music state from the last actual music playback
        self._save_music_position()  # update snapshot if still playing music
        # The in-progress track gets its chance to count as a play
        self.player.flush_listen()
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
        self._stop_media_server()
        # Give background threads (lyrics fetch, palette extraction, album
        # loads — current and retired) a short window to finish; anything
        # still running afterwards is handled by main()'s os._exit fallback
        # so interpreter teardown never destroys a running QThread (abort).
        # Settings are synced here because that fallback skips destructors.
        self._lingering_threads = [
            t for t in (self._lyrics_thread, self._palette_thread,
                        self.player._art_thread, self.quick_switcher._thread,
                        getattr(self.album_view, '_load_thread', None))
            if t is not None]
        for t in self._lingering_threads:
            if t.isRunning():
                t.wait(1500)
        bg_threads.wait_all(1500)
        self.settings.sync()
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
    # App-wide default font so unstyled widgets match the stylesheet
    from PyQt5.QtGui import QFont
    app.setFont(QFont(theme.FONT.strip("'\""), theme.DEFAULT_SIZE))

    app.setDesktopFileName('lp')
    app_ui = App(media_signals=media_signals, media_backend=media_backend)
    app.installEventFilter(app_ui)
    app_ui.show()
    code = app.exec_()
    # If a background thread outlived closeEvent's bounded waits (e.g. a
    # lyrics fetch stuck on a slow network), skip interpreter teardown:
    # destroying a running QThread is a hard abort, and everything that
    # matters (settings, play log) was already flushed in closeEvent.
    lingering = [t for t in getattr(app_ui, '_lingering_threads', [])
                 if t.isRunning()]
    if lingering or bg_threads.any_running():
        os._exit(code)
    sys.exit(code)

if __name__ == '__main__':
    main()
