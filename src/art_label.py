# AlbumArtLabel — efficient album art display.
#
# Replaces the old QLabel + setScaledContents(True) approach, which repainted
# the full-resolution source pixmap (iTunes covers are 3000x3000) on every
# paint. Here the source is downscaled once on load, a display-sized copy is
# cached and refreshed on a debounce timer, and painting draws the cached
# pixmap centered with aspect-ratio letterboxing and rounded corners.

from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtCore import Qt, QTimer, QRectF, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter


class AlbumArtLabel(QWidget):
    clicked = pyqtSignal()

    MAX_SOURCE_SIDE = 1200   # downscale huge covers once on load
    RESCALE_DELTA = 16       # px change that triggers a fresh smooth rescale

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None   # load-time downscaled original
        self._display = None  # cached display-sized copy
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
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
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
