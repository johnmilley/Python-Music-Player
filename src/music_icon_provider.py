# Purpose: remove default icons from FolderView and
# replace with transparent bitmaps

from PyQt5.QtWidgets import QFileIconProvider
from PyQt5.QtCore import Qt, QFileInfo
from PyQt5.QtGui import QIcon, QPixmap

class MusicIconProvider(QFileIconProvider):
    def __init__(self):
        super().__init__()
        self.music_icon = QIcon.fromTheme("audio-x-generic")
        transparent_pixmap = QPixmap(1, 1)
        transparent_pixmap.fill(Qt.transparent)
        self.no_icon = QIcon(transparent_pixmap)

    def icon(self, arg):
        # Check if arg is QFileInfo before accessing file system methods
        if isinstance(arg, QFileInfo) and arg.isDir():
            return self.no_icon
        return super().icon(arg)
