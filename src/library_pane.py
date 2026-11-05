# Side panes of the main window (v2): LibraryPane to the LEFT of the art,
# LyricsPane to the RIGHT. Both are plain layout containers — the app owns
# the real content widgets (the mode views, the one AlbumView, the one
# LyricsWidget) and parents them in here; max mode borrows AlbumView and
# LyricsWidget and hands them back via the *_slot layouts.
#
# LibraryPane is a two-level drill-down rather than two side-by-side panes,
# so opening the library never widens the window more than once:
#
#   ┌──────────────────────┐
#   │ ♪  🎙  📻  ♥          │  mode tabs (the toolbar's old job)
#   │ ‹  Artist — Album  ▸  │  nav row: back (tracks page only), title,
#   │                       │  'Now playing' (when browsing elsewhere)
#   ├──────────────────────┤
#   │ library | tracks      │  QStackedWidget: page 0 = mode views,
#   └──────────────────────┘                  page 1 = tracklist
#
# 'h' / the back arrow go up to the library, opening an album/feed/
# collection goes down to its tracks. Which page is showing never affects
# what's playing.

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QToolButton, QStackedWidget, QSizePolicy)
from PyQt5.QtCore import Qt, QSize, pyqtSignal

MODES = (
    ('music', 'music_note', 'Music (1)'),
    ('podcast', 'podcast', 'Podcasts (2)'),
    ('radio', 'radio_waves', 'Radio (3)'),
    ('favorites', 'heart', 'Favourites (0)'),
)

LIBRARY_PAGE, TRACKS_PAGE = 0, 1


class LibraryPane(QWidget):
    mode_clicked = pyqtSignal(str)
    back_clicked = pyqtSignal()
    now_playing_clicked = pyqtSignal()

    def __init__(self, library_stack, parent=None):
        super().__init__(parent)
        self.setObjectName('library-pane')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(180)
        self._library_title = ''
        self._tracks_title = ''

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Mode tabs
        tabs = QHBoxLayout()
        tabs.setContentsMargins(6, 6, 6, 2)
        tabs.setSpacing(2)
        self.mode_buttons = {}
        for mode, icon, tip in MODES:
            btn = QToolButton()
            btn.setObjectName('mode-tab')
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setAutoExclusive(False)  # re-clicking the active tab toggles the pane
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIconSize(QSize(18, 18))
            btn.setFixedHeight(26)
            btn._icon_name = icon
            btn.clicked.connect(lambda _=False, m=mode: self.mode_clicked.emit(m))
            self.mode_buttons[mode] = btn
            tabs.addWidget(btn)
        tabs.addStretch(1)
        lay.addLayout(tabs)

        # Nav row: back arrow (tracks page only) + page title
        nav = QHBoxLayout()
        nav.setContentsMargins(6, 2, 8, 4)
        nav.setSpacing(2)
        self.back_btn = QToolButton()
        self.back_btn.setObjectName('pane-back')
        self.back_btn.setText('‹')
        self.back_btn.setToolTip('Back to library (h)')
        self.back_btn.setFocusPolicy(Qt.NoFocus)
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.back_clicked.emit)
        nav.addWidget(self.back_btn)
        self.title = QLabel()
        self.title.setObjectName('pane-title')
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        nav.addWidget(self.title, stretch=1)
        # Shown only while the tracks page lists something other than
        # what's playing — one click back to the playing album
        self.now_playing_btn = QToolButton()
        self.now_playing_btn.setObjectName('now-playing-btn')
        self.now_playing_btn.setText('Now playing')
        self.now_playing_btn.setToolTip('Show the playing album (n)')
        self.now_playing_btn.setFocusPolicy(Qt.NoFocus)
        self.now_playing_btn.setCursor(Qt.PointingHandCursor)
        self.now_playing_btn.clicked.connect(self.now_playing_clicked.emit)
        self.now_playing_btn.hide()
        nav.addWidget(self.now_playing_btn)
        lay.addLayout(nav)

        self.pages = QStackedWidget()
        self.pages.addWidget(library_stack)
        self.tracks_page = QWidget()
        self.tracks_slot = QVBoxLayout(self.tracks_page)
        self.tracks_slot.setContentsMargins(0, 0, 0, 0)
        self.pages.addWidget(self.tracks_page)
        lay.addWidget(self.pages, stretch=1)

        self.show_library()

    # ── Pages ───────────────────────────────────────────────────────

    def show_library(self):
        self.pages.setCurrentIndex(LIBRARY_PAGE)
        self.back_btn.hide()
        self._apply_title()

    def show_tracks(self):
        self.pages.setCurrentIndex(TRACKS_PAGE)
        self.back_btn.show()
        self._apply_title()

    def on_tracks_page(self):
        return self.pages.currentIndex() == TRACKS_PAGE

    def set_library_title(self, text):
        self._library_title = text or ''
        self._apply_title()

    def set_tracks_title(self, text):
        self._tracks_title = text or ''
        self._apply_title()

    def _apply_title(self):
        text = self._tracks_title if self.on_tracks_page() else self._library_title
        avail = self.title.width()
        metrics = self.title.fontMetrics()
        self.title.setText(metrics.elidedText(text, Qt.ElideRight, avail)
                           if avail > 0 else text)
        self.title.setToolTip(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_title()

    # ── Mode tabs ───────────────────────────────────────────────────

    def set_mode(self, mode):
        for m, btn in self.mode_buttons.items():
            btn.setChecked(m == mode)

    def set_icons(self, make_icon):
        """make_icon(name) -> QIcon (stateful dim/fg/accent, built by App)."""
        for btn in self.mode_buttons.values():
            btn.setIcon(make_icon(btn._icon_name))


class LyricsPane(QWidget):
    """Lyrics to the right of the art, with the track title above it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('lyrics-pane')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(180)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 8, 8)
        lay.setSpacing(6)
        self.title = QLabel()
        self.title.setObjectName('pane-title')
        self.title.setWordWrap(True)
        lay.addWidget(self.title)
        self.slot = QVBoxLayout()
        self.slot.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self.slot, stretch=1)

    def set_title(self, text):
        self.title.setText(text or '')
