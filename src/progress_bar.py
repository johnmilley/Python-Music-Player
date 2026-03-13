# subclass QProgressBar and override methods for custom progress bar implementation

from PyQt5.QtWidgets import QProgressBar
from PyQt5.QtCore import Qt, pyqtSignal

class ClickableProgressBar(QProgressBar):

    seek_requested = pyqtSignal(int)
    start_playback = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.width() > 0:
            val = event.x() / self.width()
            new_pos = int(val * self.maximum())
            self.setValue(new_pos)
            self.seek_requested.emit(new_pos)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._handle_click(event)
        super().mouseMoveEvent(event)

    def _handle_click(self, event):
        if self.width() == 0:
            return
        ratio = max(0, min(event.x(), self.width())) / self.width()
        new_pos = int(ratio * self.maximum())
        
        self.setValue(new_pos)
        self.seek_requested.emit(new_pos)
        self.repaint()  # Force immediate visual update

    def mouseReleaseEvent(self, event):
        if event.button() & Qt.LeftButton:
            self._handle_release(event)
        super().mouseReleaseEvent(event)

    def _handle_release(self, event):
        self.start_playback.emit()