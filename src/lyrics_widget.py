# Lyrics display widget - scrollable text area for song lyrics
# Supports both plain text and synced (LRC) lyrics with line highlighting

import re
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

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
    seek_requested = pyqtSignal(float)  # seconds to seek to

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('lyrics-widget')
        self._synced_lines = None  # list of (seconds, text) if synced
        self._current_line = -1
        self._theme = None
        self._font_size = None

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
        self.label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.label.setOpenExternalLinks(False)
        self.label.linkActivated.connect(self._on_link_clicked)
        self.label.setContentsMargins(9, 9, 9, 9)

        self.scroll.setWidget(self.label)
        layout.addWidget(self.scroll)
        self.setLayout(layout)

    def _on_link_clicked(self, url):
        """Handle click on a lyrics line — seek to its timestamp."""
        if url.startswith('seek:') and self._synced_lines:
            try:
                idx = int(url.split(':')[1])
                if 0 <= idx < len(self._synced_lines):
                    self.seek_requested.emit(self._synced_lines[idx][0])
            except (ValueError, IndexError):
                pass

    def set_theme(self, t, fs=None):
        """Store theme dict and font size, then re-render lyrics with new colors."""
        self._theme = t
        self._font_size = fs
        # Re-render synced lyrics so inline colors update
        if self._synced_lines:
            self._render_synced(self._current_line)

    def set_lyrics(self, text):
        """Set lyrics text. Detects LRC format automatically."""
        self._current_line = -1
        if not text:
            self._synced_lines = None
            self.label.setTextFormat(Qt.PlainText)
            self.label.setText('No lyrics found')
            self.scroll.verticalScrollBar().setValue(0)
            return

        # Try to parse as synced LRC
        parsed = parse_lrc(text)
        if parsed:
            self._synced_lines = parsed
            self._render_synced(-1)
        else:
            self.label.setTextFormat(Qt.PlainText)
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

        fs = self._font_size or 13
        line_pad = max(2, fs // 3)

        html_lines = []
        next_idx = active_idx + 1
        for i, (_, text) in enumerate(self._synced_lines):
            if not text.strip():
                html_lines.append('<br>')
                continue
            # Place anchor at the next line after active
            anchor = f'<a name="scroll-target"></a>' if i == next_idx else ''
            if i == active_idx:
                html_lines.append(
                    f'<div style="color: {accent}; '
                    f'font-weight: bold; font-size: 105%; '
                    f'padding: {line_pad}px 0;">'
                    f'<a href="seek:{i}" style="color: {accent}; text-decoration: none;">{text}</a>'
                    f'</div>')
            else:
                color = fg if i > active_idx or active_idx < 0 else dim
                html_lines.append(
                    f'{anchor}<div style="color: {color}; padding: {line_pad}px 0;">'
                    f'<a href="seek:{i}" style="color: {color}; text-decoration: none;">{text}</a>'
                    f'</div>')

        self.label.setTextFormat(Qt.RichText)
        self.label.setText(
            f'<div style="font-family: {font};">'
            + ''.join(html_lines)
            + '</div>'
        )

        # Auto-scroll after layout updates
        if active_idx >= 0:
            QTimer.singleShot(0, lambda: self._scroll_to_line(active_idx))

    def _scroll_to_line(self, idx):
        """Scroll so the active line sits roughly in the top third of the viewport."""
        if not self._synced_lines:
            return
        total = len(self._synced_lines)
        if total == 0:
            return
        scrollbar = self.scroll.verticalScrollBar()
        max_val = scrollbar.maximum()
        viewport_h = self.scroll.viewport().height()
        if max_val == 0:
            return

        # Ratio-based scroll: estimate position from line index
        content_h = max_val + viewport_h
        next_idx = min(idx + 1, total - 1)
        line_y = (next_idx / max(1, total)) * content_h

        # Place it at ~30% from the top
        target = int(line_y - viewport_h * 0.30)
        target = max(0, min(target, max_val))
        scrollbar.setValue(target)

    def clear(self):
        self._synced_lines = None
        self._current_line = -1
        self.label.setTextFormat(Qt.PlainText)
        self.label.setText('No lyrics loaded')
