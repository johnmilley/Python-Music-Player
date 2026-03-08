# Lyrics display widget - scrollable text area for song lyrics

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel
from PyQt5.QtCore import Qt


class LyricsWidget(QWidget):
    """Scrollable widget that displays lyrics text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('lyrics-widget')

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setObjectName('lyrics-scroll')

        self.label = QLabel('No lyrics loaded')
        self.label.setObjectName('lyrics-text')
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label.setContentsMargins(10, 10, 10, 10)

        self.scroll.setWidget(self.label)
        layout.addWidget(self.scroll)
        self.setLayout(layout)

    def set_lyrics(self, text):
        """Set the lyrics text and scroll to top."""
        if text:
            self.label.setText(text)
        else:
            self.label.setText('No lyrics found')
        self.scroll.verticalScrollBar().setValue(0)

    def clear(self):
        self.label.setText('No lyrics loaded')
