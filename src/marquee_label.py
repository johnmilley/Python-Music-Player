# Marquee scrolling label — Winamp-style text scroller

from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QPainter, QFontMetrics


class MarqueeLabel(QLabel):
    """QLabel that scrolls text horizontally when it overflows."""

    SCROLL_SPEED = 50  # ms per tick
    PAUSE_TICKS = 40   # pause at start before scrolling
    GAP = '       '     # gap between repeats

    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self._offset = 0
        self._pause_counter = self.PAUSE_TICKS
        self._needs_scroll = False

        self._timer = QTimer(self)
        self._timer.setInterval(self.SCROLL_SPEED)
        self._timer.timeout.connect(self._tick)

    def setText(self, text):
        self._full_text = text
        super().setText(text)  # keep QLabel in sync for non-scrolling display
        self._offset = 0
        self._pause_counter = self.PAUSE_TICKS
        self._check_overflow()
        self.update()

    def text(self):
        return self._full_text

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        return QSize(200, fm.lineSpacing() + 4)

    def minimumSizeHint(self):
        fm = QFontMetrics(self.font())
        return QSize(40, fm.lineSpacing() + 4)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._check_overflow()

    def showEvent(self, event):
        super().showEvent(event)
        self._check_overflow()

    def hideEvent(self, event):
        # Don't keep repainting at 20fps while hidden behind max/mini mode
        self._timer.stop()
        super().hideEvent(event)

    def _check_overflow(self):
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(self._full_text)
        self._needs_scroll = text_w > self.width()
        if self._needs_scroll and self.isVisible():
            if not self._timer.isActive():
                self._offset = 0
                self._pause_counter = self.PAUSE_TICKS
                self._timer.start()
        else:
            self._timer.stop()
            self._offset = 0

    def _tick(self):
        if self._pause_counter > 0:
            self._pause_counter -= 1
            return
        self._offset += 1
        loop_text = self._full_text + self.GAP
        fm = QFontMetrics(self.font())
        loop_w = fm.horizontalAdvance(loop_text)
        if self._offset >= loop_w:
            self._offset = 0
            self._pause_counter = self.PAUSE_TICKS
        self.update()

    def paintEvent(self, event):
        if not self._needs_scroll:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(self.foregroundRole()))

        fm = QFontMetrics(self.font())
        y = (self.height() + fm.ascent() - fm.descent()) // 2
        loop_text = self._full_text + self.GAP

        # Draw two copies so text wraps seamlessly
        loop_w = fm.horizontalAdvance(loop_text)
        x = -self._offset
        painter.drawText(int(x), y, loop_text)
        painter.drawText(int(x + loop_w), y, loop_text)
        painter.end()
