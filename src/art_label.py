# AlbumArtLabel — efficient album art display.
#
# Replaces the old QLabel + setScaledContents(True) approach, which repainted
# the full-resolution source pixmap (iTunes covers are 3000x3000) on every
# paint. Here the source is downscaled once on load, a display-sized copy is
# cached and refreshed on a debounce timer, and painting draws the cached
# pixmap centered with aspect-ratio letterboxing and rounded corners.

from PyQt5.QtWidgets import QWidget, QSizePolicy, QToolButton, QApplication
from PyQt5.QtCore import Qt, QTimer, QRectF, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QCursor


class AlbumArtLabel(QWidget):
    clicked = pyqtSignal()
    prev_requested = pyqtSignal()  # hover nav arrows (multi-art galleries)
    next_requested = pyqtSignal()

    MAX_SOURCE_SIDE = 1200   # downscale huge covers once on load
    RESCALE_DELTA = 16       # px change that triggers a fresh smooth rescale

    def __init__(self, parent=None, square=False):
        super().__init__(parent)
        self._source = None   # load-time downscaled original
        self._display = None  # cached display-sized copy
        self._square = square  # center-crop sources to square (vinyl feel)
        self.setObjectName('album-art')
        self.setMinimumSize(80, 80)
        # Keep a square footprint so the art doesn't reserve a tall box and
        # leave letterbox gaps above/below the (square) cover
        sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self.setCursor(Qt.PointingHandCursor)
        self._rescale_timer = QTimer(self)
        self._rescale_timer.setSingleShot(True)
        self._rescale_timer.setInterval(120)
        self._rescale_timer.timeout.connect(self._refresh_display)

        # Prev/next arrows for scrolling a gallery of artwork. Enabled by
        # whoever owns the gallery (Player); only shown while hovered, and
        # hidden again whenever the application loses focus.
        self._nav_enabled = False
        self._prev_btn = self._make_nav_button('❮')
        self._prev_btn.clicked.connect(self.prev_requested.emit)
        self._next_btn = self._make_nav_button('❯')
        self._next_btn.clicked.connect(self.next_requested.emit)
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_app_state_changed)

    # ── Gallery nav arrows ──────────────────────────────────────────

    def _make_nav_button(self, glyph):
        btn = QToolButton(self)
        btn.setText(glyph)
        btn.setCursor(Qt.ArrowCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setFixedSize(28, 28)
        # Styled independent of the app theme: a translucent scrim over the
        # artwork reads well on any cover, light or dark
        btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(20, 20, 20, 110);
                color: white;
                border: none;
                border-radius: 14px;
                font-size: 11pt;
            }
            QToolButton:hover { background-color: rgba(20, 20, 20, 180); }
        """)
        btn.hide()
        return btn

    def set_nav_enabled(self, enabled):
        self._nav_enabled = enabled
        if enabled and self._cursor_inside():
            self._show_nav()
        elif not enabled:
            self._hide_nav()

    def _cursor_inside(self):
        return self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    def _show_nav(self):
        if not (self._nav_enabled and self._source):
            return
        self._position_nav()
        for btn in (self._prev_btn, self._next_btn):
            btn.show()
            btn.raise_()

    def _hide_nav(self):
        self._prev_btn.hide()
        self._next_btn.hide()

    def _position_nav(self):
        """Pin the arrows to the vertical middle of the displayed art."""
        target = self._target_size()
        if target is None or target.isEmpty():
            return
        x0 = (self.width() - target.width()) // 2
        y = (self.height() - self._prev_btn.height()) // 2
        inset = 8
        self._prev_btn.move(x0 + inset, y)
        self._next_btn.move(
            x0 + target.width() - inset - self._next_btn.width(), y)

    def enterEvent(self, event):
        self._show_nav()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Moving onto a child (the arrows) also fires Leave — only hide
        # when the cursor has really left the label
        if not self._cursor_inside():
            self._hide_nav()
        super().leaveEvent(event)

    def _on_app_state_changed(self, state):
        if state != Qt.ApplicationActive:
            self._hide_nav()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return width

    def set_source(self, pixmap):
        """Set the artwork. Oversized sources are downscaled once here so no
        later paint or rescale ever touches the full-resolution image."""
        if pixmap is None or pixmap.isNull():
            self.clear()
            return
        if self._square and pixmap.width() != pixmap.height():
            # Center-crop to square — keeps every image (back covers,
            # inserts) reading like an LP sleeve
            crop = min(pixmap.width(), pixmap.height())
            pixmap = pixmap.copy((pixmap.width() - crop) // 2,
                                 (pixmap.height() - crop) // 2, crop, crop)
        side = max(pixmap.width(), pixmap.height())
        if side > self.MAX_SOURCE_SIDE:
            pixmap = pixmap.scaled(
                self.MAX_SOURCE_SIDE, self.MAX_SOURCE_SIDE,
                Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._source = pixmap
        self._display = None
        self._refresh_display()

    def pixmap(self):
        return self._source

    def hasArt(self):
        return self._source is not None

    def clear(self):
        self._source = None
        self._display = None
        self._hide_nav()
        self.update()

    def _target_size(self):
        if not self._source:
            return None
        return self._source.size().scaled(self.size(), Qt.KeepAspectRatio)

    def _refresh_display(self):
        if not self._source:
            return
        target = self._target_size()
        if target.isEmpty():
            return
        self._display = self._source.scaled(
            target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if self._prev_btn.isVisible():
            self._position_nav()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._prev_btn.isVisible():
            self._position_nav()
        if not self._source:
            return
        target = self._target_size()
        if self._display is None:
            self._refresh_display()
        elif (abs(self._display.width() - target.width()) > self.RESCALE_DELTA
              or abs(self._display.height() - target.height()) > self.RESCALE_DELTA):
            # Paint keeps stretching the stale cache cheaply in the meantime
            self._rescale_timer.start()

    def paintEvent(self, event):
        if not self._display:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        target = self._target_size()
        rect = QRectF((self.width() - target.width()) / 2,
                      (self.height() - target.height()) / 2,
                      target.width(), target.height())
        # Square corners — no rounding, no clip path needed
        painter.drawPixmap(rect.toRect(), self._display)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
