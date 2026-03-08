# FolderView displays filesystem contents

# std libraries
import os
import subprocess
import sys
from pathlib import Path

# pyqt5 libraries
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QFileSystemModel, QMenu
)
from PyQt5.QtCore import Qt, QDir, pyqtSignal

# project files
from album_view import AlbumView
from music_icon_provider import MusicIconProvider
from vim_views import VimTreeView, SearchBar

class FolderView(QWidget):
    """
    Widget that displays folders on filesystem that
    contain music.
    """
    album_changed = pyqtSignal(str)

    def __init__(self, album_view=None):
        super().__init__()
        self.album_view = album_view
        self.setMinimumWidth(150)

        self.model = QFileSystemModel()

        self.model.setIconProvider(MusicIconProvider())

        # root = '/Users/jlm/Downloads/music'
        root = '/mnt/media/02_PLEX_MEDIA/music'
        self.model.setRootPath(root)
        self.model.setFilter(QDir.Dirs | QDir.NoDotAndDotDot )

        self.layout = QVBoxLayout()
        self.view = VimTreeView()
        self.view.setContextMenuPolicy(Qt.CustomContextMenu) # for right click open
        self.view.customContextMenuRequested.connect(self.open_context_menu)
        self.view.header().hide()
        self.view.setModel(self.model)
        self.view.setItemsExpandable(True)
        self.view.setRootIsDecorated(False)

        self.view.setRootIndex(self.model.index(root))

        for i in range(1, self.model.columnCount()):
            self.view.hideColumn(i)

        self.view.setIndentation(20)

        self.view.setWordWrap(True)

        self.view.clicked.connect(self.toggle_expand)
        self.view.doubleClicked.connect(self.on_item_double_clicked)

        # Search bar
        self.search_bar = SearchBar(self.view)
        self.view.set_search_bar(self.search_bar)
        self.search_bar.textChanged.connect(self._on_search)

        self.layout.addWidget(self.search_bar)
        self.layout.addWidget(self.view)

        self.setLayout(self.layout)

    def _on_search(self, text):
        """Jump to first folder matching the search text."""
        if not text:
            return
        root = self.view.rootIndex()
        for row in range(self.model.rowCount(root)):
            idx = self.model.index(row, 0, root)
            name = self.model.fileName(idx)
            if text.lower() in name.lower():
                self.view.setCurrentIndex(idx)
                self.view.scrollTo(idx)
                break

    def toggle_expand(self, index):
        if self.view.isExpanded(index):
            self.view.collapse(index)
        else:
            self.view.expand(index)

    def on_item_double_clicked(self, index):
        # Load Album in AlbumViewer if the item is
        # a directory and contains music

        path = self.model.filePath(index)
        info = self.model.fileInfo(index)

        print(f"LOG: {path} {info.baseName}")
        if info.isDir():
            content = os.listdir(path)
            if any(f.lower().endswith(('.mp3', '.flac', '.m4a')) for f in content):
                if self.album_view:
                    self.album_view.load_album_listing(path)

    def open_context_menu(self, pos):
        index = self.view.indexAt(pos)
        if not index.isValid():
            return

        path = self.model.filePath(index)
        menu = QMenu()
        open_action = menu.addAction("Open folder.")
        action = menu.exec_(self.view.mapToGlobal(pos))

        if action == open_action:
            if sys.platform == 'darwin':  # macOS
                subprocess.Popen(['open', path])
            elif sys.platform == 'linux': # Linux
                subprocess.Popen(['xdg-open', path])
            elif sys.platform == 'win32': # Windows
                os.startfile(path)


def main():
    app = QApplication(sys.argv)
    folder_view = FolderView()
    folder_view.show()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
