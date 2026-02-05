# Purpose: subclass QProgressBar and override methods for custom progress bar implementation

from PyQt5.QtWidgets import QProgressBar
from PyQt5.QtCore import Qt, pyqtSignal

class ClickableProgressBar(QProgressBar):

    seek_requested = pyqtSignal(int)
    start_playback = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Calculate percentage based on click horizontal position
            val = event.x() / self.width()
            new_pos = val * self.maximum()  # pos / 1000
            # print(val, new_pos)
            self.setValue(int(new_pos))     # update bar
            self.seek_requested.emit(int(new_pos))
            # print(new_pos)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._handle_click(event)
        super().mouseMoveEvent(event)

    def _handle_click(self, event):
        # Calculate ratio and clamp within [0, 1]
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