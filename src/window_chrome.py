# Frameless-window chrome: custom title bar + invisible edge-resize grips.
#
# The main window runs with Qt.FramelessWindowHint (no OS titlebar), styled
# to match the toolbar directly below it — a continuous strip of chrome,
# echoing the titlebar-over-tabbar stack in the sibling 'text' app for a
# consistent look between the two. Content runs edge to edge (just a 1px
# hairline outline, no padded margin); resizing is handled by eight
# invisible grip widgets floating over the window's edges and corners.
#
# Dragging/resizing goes through QWindow.startSystemMove()/startSystemResize()
# (Qt 5.15+), which hands control to the OS/window manager, so snapping,
# multi-monitor and Wayland all behave like a normal titled window even
# though decorations are off.

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QToolButton

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
    oversized squares so diagonal grabs (including the top corners, over
    the titlebar) are easy to hit. Call relayout() from the window's
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


class TitleBar(QWidget):
    """Draggable custom title bar; height matches the toolbar below it."""

    HEIGHT = 30

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self.setObjectName('titlebar')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(self.HEIGHT)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.title_label = QLabel(window.windowTitle())
        self.title_label.setObjectName('titlebar-title')
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        layout.addStretch()
        layout.addWidget(self.title_label)
        layout.addStretch()

        buttons = QWidget(self)
        buttons.setObjectName('titlebar-buttons')
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(0)
        buttons.setLayout(btn_layout)

        btn_layout.addWidget(self._make_button('–', 'Minimize', window.showMinimized))
        self.max_btn = self._make_button('□', 'Maximize', self._toggle_max)
        btn_layout.addWidget(self.max_btn)
        close_btn = self._make_button('✕', 'Close', window.close)
        close_btn.setObjectName('tb-close')
        btn_layout.addWidget(close_btn)

        layout.addWidget(buttons)

    def _make_button(self, text, tip, slot):
        btn = QToolButton(self)
        btn.setText(text)
        btn.setToolTip(tip)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setFixedSize(28, self.HEIGHT)
        btn.clicked.connect(slot)
        return btn

    def _toggle_max(self):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def set_title(self, title):
        self.title_label.setText(title)

    def set_maximized(self, maximized):
        """Swap the maximize glyph for a restore glyph (called on state change)."""
        self.max_btn.setText('⧉' if maximized else '□')
        self.max_btn.setToolTip('Restore' if maximized else 'Maximize')

    def mousePressEvent(self, event):
        # Edge/corner resizing over the titlebar is handled by the grips
        # floating above it — anywhere else on the bar starts a move
        if event.button() != Qt.LeftButton:
            return
        handle = self._window.windowHandle()
        if handle is not None:
            handle.startSystemMove()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_max()
            event.accept()
