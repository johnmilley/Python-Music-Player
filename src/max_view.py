# MaxView — fullscreen "max mode" page: large album art beside lyrics.
#
# Lives permanently as a page on the app's root QStackedWidget. It reuses
# the player's art pipeline (via the art_changed signal) and borrows the
# app's single LyricsWidget while active — nothing is duplicated or rebuilt
# per entry, so there is no copy-over bookkeeping and no settle timers.

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt

from art_label import AlbumArtLabel


class MaxView(QWidget):
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

        # Lyrics column: track title header + a slot the app's lyrics
        # widget is reparented into while max mode is active
        self.lyrics_column = QWidget()
        self.lyrics_column.setObjectName('max-lyrics-column')
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.track_label = QLabel()
        self.track_label.setObjectName('max-track-label')
        self.track_label.setWordWrap(True)
        self.track_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        col.addWidget(self.track_label)
        self.lyrics_slot = QVBoxLayout()
        self.lyrics_slot.setContentsMargins(0, 0, 0, 0)
        col.addLayout(self.lyrics_slot, stretch=1)
        self.lyrics_column.setLayout(col)
        content.addWidget(self.lyrics_column, stretch=1)

        layout.addLayout(content, stretch=1)
        self.setLayout(layout)

        player.art_changed.connect(self.art.set_source)
        player.track_changed.connect(self._on_track_changed)
        # Hover arrows scroll the album's art gallery here too
        player.register_art_label(self.art)

    def _on_track_changed(self, track):
        self.set_title(str(getattr(track, 'title', '') or ''))

    def set_title(self, title):
        self.track_label.setText(title)

    def attach_lyrics(self, lyrics_widget):
        """Borrow the app's lyrics widget (reparents it into this view)."""
        self.lyrics_slot.addWidget(lyrics_widget)
        lyrics_widget.setVisible(True)
