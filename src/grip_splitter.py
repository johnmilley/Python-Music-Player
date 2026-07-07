# GripSplitter — a QSplitter whose handles paint a faint center hairline.
#
# The default Qt handle is nearly invisible; here each handle draws a 1px
# hairline along its full length so the drag target reads clearly at rest,
# lighting up in the accent color on hover. Colors are theme-driven via
# set_colors().

from PyQt5.QtWidgets import QSplitter, QSplitterHandle
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor


class _GripHandle(QSplitterHandle):
    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self._hover = False

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        sp = self.splitter()
        painter = QPainter(self)
        rect = self.rect()
        cx, cy = rect.center().x(), rect.center().y()

        # Faint hairline along the handle's full length (accent on hover)
        line = QColor(sp._accent_color if self._hover else sp._line_color)
        if self.orientation() == Qt.Horizontal:
            painter.fillRect(cx, rect.top(), 1, rect.height(), line)
        else:
            painter.fillRect(rect.left(), cy, rect.width(), 1, line)


class GripSplitter(QSplitter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._line_color = '#888888'
        self._grip_color = '#888888'
        self._accent_color = '#888888'
        self.setHandleWidth(12)

    def createHandle(self):
        return _GripHandle(self.orientation(), self)

    def set_colors(self, line, grip, accent):
        self._line_color = line
        self._grip_color = grip
        self._accent_color = accent
        for i in range(1, self.count()):
            h = self.handle(i)
            if h is not None:
                h.update()
