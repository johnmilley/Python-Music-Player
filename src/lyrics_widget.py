# Lyrics display widget — QTextBrowser-based with measured auto-scroll.
# Supports plain text, synced (LRC) lyrics, and podcast descriptions with
# clickable timestamps.
#
# Each lyric line / description segment is one QTextBlock. The active-line
# highlight is applied with QTextCharFormat on just the affected blocks (no
# document rebuild per line), and auto-scroll uses the block's real measured
# y-position — wrapped long lines no longer cause drift.

import html as html_mod
import re

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextBrowser
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QTextCharFormat, QTextCursor

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
        self._synced_lines = None   # list of (seconds, text) if synced
        self._current_line = -1
        self._desc_segments = None  # list of (seconds, text) for descriptions
        self._desc_preamble = None
        self._full_description = None
        self._theme = None
        self._font_size = None
        self._line_blocks = []      # block number per synced line / segment

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.view = QTextBrowser()
        self.view.setObjectName('lyrics-text')
        self.view.setFrameShape(QTextBrowser.NoFrame)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setOpenLinks(False)
        self.view.setOpenExternalLinks(False)
        self.view.setFocusPolicy(Qt.NoFocus)
        self.view.anchorClicked.connect(
            lambda url: self._on_link_clicked(url.toString()))
        self.view.document().setDocumentMargin(12)

        layout.addWidget(self.view)
        self.setLayout(layout)

    # ── Colors / theme ──────────────────────────────────────────────

    def _colors(self):
        """Active-line/timestamp color, body text color, dim (past-line) color.

        The first value is 'accent_text' (not 'accent') — a stricter,
        readability-checked variant of the accent color so the highlighted
        line always stays legible against the page background, regardless of
        which accent the user (or the album art palette) picked.
        """
        t = self._theme or {}
        accent_text = t.get('accent_text', t.get('accent', 'orange'))
        return (accent_text,
                t.get('fg', 'white'),
                t.get('grip', '#888888'))  # grip → fg_dim alias

    def set_theme(self, t, fs=None):
        """Store theme dict and font size, then re-render with new colors."""
        self._theme = t
        self._font_size = fs
        family = theme.FONT.strip("'\"")
        font = QFont(family)
        font.setPointSize(fs or 13)
        self.view.document().setDefaultFont(font)
        if self._synced_lines:
            self._render_synced()
        elif self._desc_segments:
            self._render_description()

    # ── Link handling ───────────────────────────────────────────────

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

    # ── Content setters ─────────────────────────────────────────────

    def set_lyrics(self, text):
        """Set lyrics text. Detects LRC format automatically."""
        self._current_line = -1
        self._desc_segments = None
        self._full_description = None
        if not text:
            self._synced_lines = None
            self._line_blocks = []
            self.view.setPlainText('No lyrics found')
            self.view.verticalScrollBar().setValue(0)
            return

        parsed = parse_lrc(text)
        if parsed:
            self._synced_lines = parsed
            self._render_synced()
        else:
            self._synced_lines = None
            self._line_blocks = []
            self.view.setPlainText(text)
        self.view.verticalScrollBar().setValue(0)

    def set_status_html(self, html):
        """Show one-off status HTML (e.g. radio now-playing)."""
        self._synced_lines = None
        self._desc_segments = None
        self._current_line = -1
        self._line_blocks = []
        self.view.setHtml(html)

    def clear(self):
        self._synced_lines = None
        self._desc_segments = None
        self._current_line = -1
        self._line_blocks = []
        self.view.setPlainText('No lyrics loaded')

    # ── Position sync ───────────────────────────────────────────────

    def update_position(self, seconds):
        """Update the highlighted line/segment from the playback position."""
        entries = self._synced_lines or self._desc_segments
        if not entries:
            return
        line_idx = -1
        for i, (ts, _) in enumerate(entries):
            if seconds >= ts:
                line_idx = i
            else:
                break
        if line_idx != self._current_line:
            old = self._current_line
            self._current_line = line_idx
            self._update_block_formats(old, line_idx)
            if line_idx >= 0:
                self._scroll_to_block(line_idx)

    # ── Rendering (one QTextBlock per line/segment) ─────────────────

    def _line_pad(self):
        fs = self._font_size or 13
        return max(2, fs // 3)

    def _render_synced(self):
        """Full render of synced lyrics — runs on load and theme change only."""
        accent, fg, dim = self._colors()
        pad = self._line_pad()
        parts = []
        for i, (_, text) in enumerate(self._synced_lines):
            content = (f'<a href="seek:{i}" style="color: {fg}; '
                       f'text-decoration: none;">{html_mod.escape(text)}</a>'
                       if text.strip() else ' ')
            parts.append(f'<p style="margin: {pad}px 0;">{content}</p>')
        self.view.setHtml(''.join(parts))
        self._index_blocks(len(self._synced_lines))
        if self._current_line >= 0:
            self._update_block_formats(-1, self._current_line)
            self._scroll_to_block(self._current_line)

    def _index_blocks(self, count):
        """Record the block number of each rendered line/segment."""
        doc = self.view.document()
        # Blocks map 1:1 to the <p> elements, in order
        self._line_blocks = list(range(min(count, doc.blockCount())))

    def _block_format(self, category):
        accent, fg, dim = self._colors()
        fmt = QTextCharFormat()
        if category == 'active':
            fmt.setForeground(QColor(accent))
            fmt.setFontWeight(QFont.Bold)
        elif category == 'dim':
            fmt.setForeground(QColor(dim))
            fmt.setFontWeight(QFont.Normal)
        else:
            fmt.setForeground(QColor(fg))
            fmt.setFontWeight(QFont.Normal)
        return fmt

    def _update_block_formats(self, old_idx, new_idx):
        """Recolor only the blocks whose category changed."""
        if not self._line_blocks:
            return
        doc = self.view.document()
        lo = 0 if old_idx < 0 or new_idx < 0 else min(old_idx, new_idx)
        hi = max(old_idx, new_idx)
        for i in range(lo, hi + 1):
            if i >= len(self._line_blocks):
                break
            block = doc.findBlockByNumber(self._line_blocks[i])
            if not block.isValid():
                continue
            if i == new_idx:
                category = 'active'
            elif new_idx >= 0 and i < new_idx:
                category = 'dim'
            else:
                category = 'normal'
            cursor = QTextCursor(block)
            cursor.setPosition(block.position())
            cursor.setPosition(block.position() + max(block.length() - 1, 0),
                               QTextCursor.KeepAnchor)
            cursor.mergeCharFormat(self._block_format(category))

    def _scroll_to_block(self, idx):
        """Scroll so the active block sits ~30% down the viewport, using the
        block's real measured position (accurate with wrapped lines)."""
        if idx < 0 or idx >= len(self._line_blocks):
            return
        doc = self.view.document()
        block = doc.findBlockByNumber(self._line_blocks[idx])
        if not block.isValid():
            return
        y = doc.documentLayout().blockBoundingRect(block).y()
        viewport_h = self.view.viewport().height()
        scrollbar = self.view.verticalScrollBar()
        target = int(y - viewport_h * 0.30)
        scrollbar.setValue(max(0, min(target, scrollbar.maximum())))

    # ── Podcast descriptions with timestamp seek links ──────────────

    def set_description(self, text):
        """Display text with timestamps (e.g. 12:34, 1:02:30) as clickable
        seek links. Segments between timestamps highlight like synced lyrics."""
        self._synced_lines = None
        self._desc_segments = None
        self._current_line = -1
        self._line_blocks = []
        self._full_description = text
        if not text:
            self.view.setPlainText('')
            return

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
            _, fg, _ = self._colors()
            display = html_mod.escape(text).replace('\n', '<br>')
            self.view.setHtml(f'<div style="color: {fg};">{display}</div>')
            self.view.verticalScrollBar().setValue(0)
            return

        self._desc_segments = segments
        self._desc_preamble = preamble
        self._render_description()
        self.view.verticalScrollBar().setValue(0)

    def _render_description(self):
        """Full render of description segments — one block per segment."""
        if not self._desc_segments:
            return
        accent, fg, dim = self._colors()
        pad = self._line_pad()
        ts_re = re.compile(r'\b((\d{1,2}):)?(\d{1,2}):(\d{2})\b')
        parts = []
        preamble_blocks = 0
        if self._desc_preamble:
            pre = html_mod.escape(self._desc_preamble.strip('\n')).replace('\n', '<br>')
            parts.append(f'<p style="margin: {pad}px 0; color: {fg};">{pre}</p>')
            preamble_blocks = 1

        for i, (secs, segment_text) in enumerate(self._desc_segments):
            # <br> keeps multi-line segments inside a single block
            seg = html_mod.escape(segment_text.strip('\n')).replace('\n', '<br>')
            seg = ts_re.sub(
                lambda m: (f'<a href="seekto:{secs}" style="color: {accent}; '
                           f'text-decoration: none; font-weight: bold;">'
                           f'{m.group(0)}</a>'),
                seg,
                count=1,
            )
            parts.append(
                f'<p style="margin: {pad}px 0; color: {fg};">{seg or "&nbsp;"}</p>')

        self.view.setHtml(''.join(parts))
        # Segment i lives at block preamble_blocks + i
        self._line_blocks = [preamble_blocks + i
                             for i in range(len(self._desc_segments))]
        if self._current_line >= 0:
            self._update_block_formats(-1, self._current_line)
