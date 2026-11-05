# Frameless-window chrome: invisible edge-resize grips.
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

from PyQt5.QtCore import Qt
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
