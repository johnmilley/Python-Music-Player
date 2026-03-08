# Lyrics display widget - scrollable text area for song lyrics
# Supports both plain text and synced (LRC) lyrics with line highlighting

import re
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel
from PyQt5.QtCore import Qt

import theme


def parse_lrc(text):
    """Parse LRC format into list of (seconds, line_text).
    Returns None if text is not valid LRC."""
    lines = []
    pattern = re.compile(r'\[(\d+):(\d+)\.(\d+)\]\s*(.*)')
    for line in text.splitlines():
        m = pattern.match(line)
        if m:
            mins, secs, centis = int(m.group(1)), int(m.group(2)), int(m.group(3))
            timestamp = mins * 60 + secs + centis / 100.0
            lines.append((timestamp, m.group(4)))
    return lines if lines else None


class LyricsWidget(QWidget):
    """Scrollable widget that displays lyrics text with optional sync."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('lyrics-widget')
        self._synced_lines = None  # list of (seconds, text) if synced
        self._current_line = -1
        self._theme = None

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

    def set_theme(self, t):
        """Store theme dict for building highlighted HTML."""
        self._theme = t

    def set_lyrics(self, text):
        """Set lyrics text. Detects LRC format automatically."""
        self._current_line = -1
        if not text:
            self._synced_lines = None
            self.label.setText('No lyrics found')
            self.scroll.verticalScrollBar().setValue(0)
            return

        # Try to parse as synced LRC
        parsed = parse_lrc(text)
        if parsed:
            self._synced_lines = parsed
            self._render_synced(-1)
        else:
            self._synced_lines = None
            self.label.setText(text)
        self.scroll.verticalScrollBar().setValue(0)

    def update_position(self, seconds):
        """Update the highlighted line based on playback position."""
        if not self._synced_lines:
            return

        # Find the current line
        line_idx = -1
        for i, (ts, _) in enumerate(self._synced_lines):
            if seconds >= ts:
                line_idx = i
            else:
                break

        if line_idx != self._current_line:
            self._current_line = line_idx
            self._render_synced(line_idx)

    def _render_synced(self, active_idx):
        """Render synced lyrics as HTML with the active line highlighted."""
        t = self._theme or {}
        accent = t.get('accent', 'orange')
        fg = t.get('fg', 'white')
        dim = t.get('grip', '#888888')
        font = theme.FONT

        html_lines = []
        for i, (_, text) in enumerate(self._synced_lines):
            if not text.strip():
                html_lines.append('<br>')
                continue
            if i == active_idx:
                html_lines.append(
                    f'<div id="line-{i}" style="color: {accent}; '
                    f'font-weight: bold; font-size: 105%; '
                    f'padding: 2px 0;">{text}</div>')
            else:
                color = fg if i > active_idx or active_idx < 0 else dim
                html_lines.append(
                    f'<div style="color: {color}; padding: 2px 0;">{text}</div>')

        self.label.setTextFormat(Qt.RichText)
        self.label.setText(
            f'<div style="font-family: {font};">'
            + ''.join(html_lines)
            + '</div>'
        )

        # Auto-scroll to keep active line visible
        if active_idx >= 0:
            self._scroll_to_line(active_idx)

    def _scroll_to_line(self, idx):
        """Scroll so the active line is roughly centered."""
        if not self._synced_lines:
            return
        total = len(self._synced_lines)
        if total == 0:
            return
        scrollbar = self.scroll.verticalScrollBar()
        max_val = scrollbar.maximum()
        # Estimate position as fraction of total lines
        frac = max(0, (idx - 3)) / max(1, total - 1)
        scrollbar.setValue(int(frac * max_val))

    def clear(self):
        self._synced_lines = None
        self._current_line = -1
        self.label.setTextFormat(Qt.PlainText)
        self.label.setText('No lyrics loaded')
