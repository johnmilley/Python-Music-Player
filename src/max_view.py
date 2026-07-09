# MaxView — fullscreen "max mode" page: large album art beside a side column
# with the track title, and independently toggleable tracklist/lyrics panes.
#
# Lives permanently as a page on the app's root QStackedWidget. It reuses
# the player's art pipeline (via the art_changed signal) and borrows the
# app's single AlbumView/LyricsWidget while active — nothing is duplicated
# or rebuilt per entry, so there is no copy-over bookkeeping and no settle
# timers.

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QIcon

from art_label import AlbumArtLabel
from player import _render_svg


class MaxView(QWidget):
    exit_requested = pyqtSignal()

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.setObjectName('max-mode')
        self.setFocusPolicy(Qt.StrongFocus)
        # Required for QSS background painting on QWidget subclasses
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Accent divider along the top edge
        self.divider = QWidget()
        self.divider.setObjectName('max-divider')
        self.divider.setFixedHeight(2)
        layout.addWidget(self.divider)

        content = QHBoxLayout()
        content.setContentsMargins(24, 24, 24, 24)
        content.setSpacing(24)

        self.art = AlbumArtLabel()
        self.art.setMinimumSize(300, 300)
        content.addWidget(self.art, stretch=2)

        # Side column: track title (always visible) + a tracklist slot and a
        # lyrics slot, each independently toggleable and each a reparenting
        # slot for the app's one true AlbumView / LyricsWidget. The whole
        # column hides itself when both slots are empty of content.
        self.side_column = QWidget()
        self.side_column.setObjectName('max-lyrics-column')
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        self.track_label = QLabel()
        self.track_label.setObjectName('max-track-label')
        self.track_label.setWordWrap(True)
        self.track_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        col.addWidget(self.track_label)

        self.tracklist_on = False
        self.lyrics_on = True
        self.tracklist_wrap = QWidget()
        self.tracklist_slot = QVBoxLayout(self.tracklist_wrap)
        self.tracklist_slot.setContentsMargins(0, 0, 0, 0)
        self.tracklist_wrap.hide()  # off by default each time max mode opens
        col.addWidget(self.tracklist_wrap, stretch=1)

        self.lyrics_wrap = QWidget()
        self.lyrics_slot = QVBoxLayout(self.lyrics_wrap)
        self.lyrics_slot.setContentsMargins(0, 0, 0, 0)
        col.addWidget(self.lyrics_wrap, stretch=1)

        self.side_column.setLayout(col)
        content.addWidget(self.side_column, stretch=1)

        layout.addLayout(content, stretch=1)
        self.setLayout(layout)

        # Corner close button — overlaid top-right, since there's no toolbar
        # visible in fullscreen max mode to hold an exit control
        self.close_btn = QToolButton(self)
        self.close_btn.setObjectName('max-close-btn')
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setIconSize(QSize(14, 14))
        self.close_btn.setToolTip('Back to normal window (Esc)')
        self.close_btn.clicked.connect(self.exit_requested.emit)
        self.close_btn.raise_()

        player.art_changed.connect(self.art.set_source)
        player.track_changed.connect(self._on_track_changed)
        # Hover arrows scroll the album's art gallery here too
        player.register_art_label(self.art)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.close_btn.move(self.width() - self.close_btn.width() - 12, 12)

    def set_close_icon_color(self, color):
        self.close_btn.setIcon(QIcon(_render_svg('close', color, 14)))

    def _on_track_changed(self, track):
        self.set_title(str(getattr(track, 'title', '') or ''))

    def set_title(self, title):
        self.track_label.setText(title)

    def attach_lyrics(self, lyrics_widget):
        """Borrow the app's lyrics widget (reparents it into this view)."""
        self.lyrics_slot.addWidget(lyrics_widget)
        lyrics_widget.setVisible(True)

    def attach_tracklist(self, album_view):
        """Borrow the app's AlbumView/tracklist (reparents it into this view)."""
        self.tracklist_slot.addWidget(album_view)
        album_view.setVisible(True)

    def set_lyrics_visible(self, on):
        self.lyrics_on = on
        self.lyrics_wrap.setVisible(on)
        self._update_side_column()

    def set_tracklist_visible(self, on):
        self.tracklist_on = on
        self.tracklist_wrap.setVisible(on)
        self._update_side_column()

    def _update_side_column(self):
        """Collapse the whole side column when neither pane is showing, so
        the art gets the full width (mirrors PanelManager's right-column
        collapse in normal mode). Tracked with explicit flags rather than
        isVisible(), since a wrap's own visible-flag is unreliable to read
        back the instant its ancestor (this column) is hidden/shown too."""
        self.side_column.setVisible(self.tracklist_on or self.lyrics_on)
