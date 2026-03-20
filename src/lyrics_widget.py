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
        self._desc_segments = None
        self._desc_preamble = None
        self._full_description = None
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
        """Handle click on a lyrics line or timestamp — seek to position."""
        if url.startswith('seekto:'):
            try:
                seconds = float(url.split(':', 1)[1])
                self.seek_requested.emit(seconds)
            except (ValueError, IndexError):
                pass
        elif url.startswith('seek:') and self._synced_lines:
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

        # Cache line HTML parts; only rebuild if theme/font changed or first render
        cache_key = (accent, fg, dim, fs, len(self._synced_lines))
        if getattr(self, '_synced_cache_key', None) != cache_key:
            # Full rebuild — cache each line's normal and active HTML
            self._synced_cache_key = cache_key
            self._synced_normal = []
            self._synced_active = []
            self._synced_dim = []
            for i, (_, text) in enumerate(self._synced_lines):
                if not text.strip():
                    self._synced_normal.append('<br>')
                    self._synced_active.append('<br>')
                    self._synced_dim.append('<br>')
                    continue
                self._synced_active.append(
                    f'<div style="color: {accent}; '
                    f'font-weight: bold; font-size: 105%; '
                    f'padding: {line_pad}px 0;">'
                    f'<a href="seek:{i}" style="color: {accent}; text-decoration: none;">{text}</a>'
                    f'</div>')
                self._synced_normal.append(
                    f'<div style="color: {fg}; padding: {line_pad}px 0;">'
                    f'<a href="seek:{i}" style="color: {fg}; text-decoration: none;">{text}</a>'
                    f'</div>')
                self._synced_dim.append(
                    f'<div style="color: {dim}; padding: {line_pad}px 0;">'
                    f'<a href="seek:{i}" style="color: {dim}; text-decoration: none;">{text}</a>'
                    f'</div>')
            self._synced_font = font

        # Assemble from cache — pick the right variant per line
        html_lines = []
        for i in range(len(self._synced_lines)):
            if i == active_idx:
                html_lines.append(self._synced_active[i])
            elif active_idx >= 0 and i < active_idx:
                html_lines.append(self._synced_dim[i])
            else:
                html_lines.append(self._synced_normal[i])

        self.label.setTextFormat(Qt.RichText)
        self.label.setText(
            f'<div style="font-family: {self._synced_font};">'
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

    def set_description(self, text):
        """Display text with timestamps (e.g. 12:34, 1:02:30) as clickable seek links.

        Segments between timestamps are tracked so update_position() can
        highlight the currently-playing section, just like synced lyrics.
        """
        self._synced_lines = None
        self._desc_segments = None
        self._current_line = -1
        self._full_description = text
        if not text:
            self.label.setTextFormat(Qt.PlainText)
            self.label.setText('')
            return

        # Find timestamps in the text so we can make them clickable seek links.
        ts_pattern = re.compile(r'\b((\d{1,2}):)?(\d{1,2}):(\d{2})\b')
        segments = []  # list of (seconds, segment_text)
        last_end = 0
        preamble = None

        for m in ts_pattern.finditer(text):
            if last_end == 0 and m.start() > 0:
                preamble = text[:m.start()]
            elif last_end > 0:
                segments.append((prev_secs, text[last_end:m.start()]))

            hours = int(m.group(2)) if m.group(2) else 0
            mins = int(m.group(3))
            secs_val = int(m.group(4))
            prev_secs = hours * 3600 + mins * 60 + secs_val
            last_end = m.start()

        if last_end > 0:
            segments.append((prev_secs, text[last_end:]))

        if not segments:
            # No timestamps found — render as rich text (preserving UTF-8)
            import html as html_mod
            display = html_mod.escape(text).replace('\n', '<br>')
            t = self._theme or {}
            font = theme.FONT
            self.label.setTextFormat(Qt.RichText)
            self.label.setText(f'<div style="font-family: {font};">{display}</div>')
            self.scroll.verticalScrollBar().setValue(0)
            return

        self._desc_segments = segments
        self._desc_preamble = preamble
        self._render_description(-1)
        self.scroll.verticalScrollBar().setValue(0)

    def _render_description(self, active_idx):
        """Render description segments with the active one highlighted."""
        if not self._desc_segments:
            return
        t = self._theme or {}
        accent = t.get('accent', 'orange')
        fg = t.get('fg', 'white')
        dim = t.get('grip', '#888888')
        font = theme.FONT
        fs = self._font_size or 13
        line_pad = max(2, fs // 3)

        html_parts = []

        import html as html_mod

        # Preamble (text before first timestamp)
        if self._desc_preamble:
            pre = html_mod.escape(self._desc_preamble).replace('\n', '<br>')
            html_parts.append(
                f'<div style="color: {fg}; padding: {line_pad}px 0;">{pre}</div>')

        for i, (secs, segment_text) in enumerate(self._desc_segments):
            segment_html = html_mod.escape(segment_text).replace('\n', '<br>')
            # Make the timestamp itself a seek link
            ts_re = re.compile(r'\b((\d{1,2}):)?(\d{1,2}):(\d{2})\b')
            segment_html = ts_re.sub(
                lambda m: (f'<a href="seekto:{secs}" style="color: {accent}; '
                           f'text-decoration: none; font-weight: bold;">'
                           f'{m.group(0)}</a>'),
                segment_html,
                count=1,
            )

            if i == active_idx:
                html_parts.append(
                    f'<div style="color: {accent}; font-weight: bold; '
                    f'padding: {line_pad}px 0;">{segment_html}</div>')
            else:
                color = fg if i > active_idx or active_idx < 0 else dim
                html_parts.append(
                    f'<div style="color: {color}; '
                    f'padding: {line_pad}px 0;">{segment_html}</div>')

        self.label.setTextFormat(Qt.RichText)
        self.label.setText(
            f'<div style="font-family: {font};">'
            + ''.join(html_parts)
            + '</div>'
        )

        if active_idx >= 0:
            total = len(self._desc_segments)
            QTimer.singleShot(0, lambda: self._scroll_to_desc(active_idx, total))

    def _scroll_to_desc(self, idx, total):
        """Scroll so the active description segment is visible."""
        scrollbar = self.scroll.verticalScrollBar()
        max_val = scrollbar.maximum()
        viewport_h = self.scroll.viewport().height()
        if max_val == 0:
            return
        content_h = max_val + viewport_h
        line_y = ((idx + 1) / max(1, total)) * content_h
        target = int(line_y - viewport_h * 0.30)
        target = max(0, min(target, max_val))
        scrollbar.setValue(target)

    def clear(self):
        self._synced_lines = None
        self._current_line = -1
        self.label.setTextFormat(Qt.PlainText)
        self.label.setText('No lyrics loaded')
