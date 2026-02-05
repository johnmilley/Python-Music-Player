# FolderView displays filesystem contents

# std libraries
import os
import subprocess
import sys
from pathlib import Path

# pyqt5 libraries
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QFileSystemModel, QTreeView, QMenu
)
from PyQt5.QtCore import Qt, QDir, pyqtSignal

# project files
from album_view import AlbumView
from music_icon_provider import MusicIconProvider

class FolderView(QWidget):
    """
    Widget that displays folders on filesystem that
    contain music.
    """
    album_changed = pyqtSignal(str)

    def __init__(self, album_view=None):
        super().__init__()
        self.album_view = album_view

        self.model = QFileSystemModel()

        self.model.setIconProvider(MusicIconProvider())

        root = '/Users/jlm/Downloads/music'
        self.model.setRootPath(root)
        self.model.setFilter(QDir.Dirs | QDir.NoDotAndDotDot )

        self.layout = QVBoxLayout()
        self.view = QTreeView()
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

        self.view.clicked.connect(self.toggle_expand)
        self.view.doubleClicked.connect(self.on_item_double_clicked)

        self.layout.addWidget(self.view)

        # load stylesheet
        try:
            with open("stylesheets/folder_view.qss", 'r') as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            print("stylesheet not found")

        self.setLayout(self.layout)

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