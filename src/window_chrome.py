# Frameless-window chrome: invisible edge-resize grips, plus the draggable
# side-pane dividers (PaneDivider).
#
# The main window runs with Qt.FramelessWindowHint (no OS titlebar — it's
# moved by dragging the album art). Content runs edge to edge (just a 1px
# hairline outline, no padded margin); resizing is handled by eight
# invisible grip widgets floating over the window's edges and corners.
#
# Dragging/resizing goes through QWindow.startSystemMove()/startSystemResize()
# (Qt 5.15+), which hands control to the OS/window manager, so snapping,
# multi-monitor and Wayland all behave like a normal titled window even
# though decorations are off.

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QWidget

GRIP_SIZE = 7     # thickness of the edge strips
CORNER_SIZE = 18  # corner squares — big enough to hit diagonals easily

_CURSOR_FOR_EDGES = {
    Qt.LeftEdge: Qt.SizeHorCursor,
    Qt.RightEdge: Qt.SizeHorCursor,
    Qt.TopEdge: Qt.SizeVerCursor,
    Qt.BottomEdge: Qt.SizeVerCursor,
    Qt.TopEdge | Qt.LeftEdge: Qt.SizeFDiagCursor,
    Qt.BottomEdge | Qt.RightEdge: Qt.SizeFDiagCursor,
    Qt.TopEdge | Qt.RightEdge: Qt.SizeBDiagCursor,
    Qt.BottomEdge | Qt.LeftEdge: Qt.SizeBDiagCursor,
}


class EdgeGrip(QWidget):
    """One invisible resize zone: paints nothing, just sets the resize
    cursor and hands the drag to the window manager on press."""

    def __init__(self, window, edges):
        super().__init__(window)
        self._window = window
        self.edges = edges
        self.setCursor(_CURSOR_FOR_EDGES[edges])

    def mousePressEvent(self, event):
        handle = self._window.windowHandle()
        if event.button() == Qt.LeftButton and handle is not None:
            handle.startSystemResize(self.edges)
            event.accept()
        else:
            super().mousePressEvent(event)


class WindowGrips:
    """Eight invisible resize grips floating over the window's edges.

    The grips are children of the main window itself, raised above the
    content, so edge clicks resize even where a pane runs right up to the
    window border — no layout margin, no visible strip. Corner grips are
    oversized squares so diagonal grabs are easy to hit. Call relayout() from the window's
    resizeEvent; disable while maximized/fullscreen.
    """

    def __init__(self, window):
        self._window = window
        self._grips = [EdgeGrip(window, edges) for edges in _CURSOR_FOR_EDGES]

    def relayout(self):
        w, h = self._window.width(), self._window.height()
        g, c = GRIP_SIZE, CORNER_SIZE
        rects = {
            Qt.TopEdge | Qt.LeftEdge: (0, 0, c, c),
            Qt.TopEdge: (c, 0, w - 2 * c, g),
            Qt.TopEdge | Qt.RightEdge: (w - c, 0, c, c),
            Qt.LeftEdge: (0, c, g, h - 2 * c),
            Qt.RightEdge: (w - g, c, g, h - 2 * c),
            Qt.BottomEdge | Qt.LeftEdge: (0, h - c, c, c),
            Qt.BottomEdge: (c, h - g, w - 2 * c, g),
            Qt.BottomEdge | Qt.RightEdge: (w - c, h - c, c, c),
        }
        for grip in self._grips:
            grip.setGeometry(*rects[grip.edges])
            grip.raise_()

    def set_enabled(self, enabled):
        for grip in self._grips:
            grip.setVisible(enabled)


class PaneDivider(QWidget):
    """Draggable boundary between a side pane and the art (App owns the
    geometry — see App._pane_drag). Invisible until hovered/dragged, then a
    thin accent line; double-click resets the pane to its default width.

    Signals carry the cursor's global x so the drag math is independent of
    the widget moving under the cursor as the window resizes."""

    drag_started = pyqtSignal(int)
    dragged = pyqtSignal(int)
    drag_finished = pyqtSignal()
    reset_requested = pyqtSignal()

    HIT_W = 7       # grab zone width
    LINE_W = 2      # hover/drag indicator

    def __init__(self, parent, line_offset):
        super().__init__(parent)
        # x of the indicator line within the grab zone: the zone sits mostly
        # over the art so it never covers the pane's scrollbar
        self._line_x = line_offset
        self._hover = False
        self._dragging = False
        self._color = QColor('orange')
        self.setCursor(Qt.SplitHCursor)
        self.setToolTip('Drag to resize · double-click to reset')
        self.hide()

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        if self._hover or self._dragging:
            p = QPainter(self)
            p.fillRect(self._line_x, 0, self.LINE_W, self.height(), self._color)
            p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.update()
            self.drag_started.emit(event.globalPos().x())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.dragged.emit(event.globalPos().x())
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            self.update()
            self.drag_finished.emit()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.reset_requested.emit()
            event.accept()
