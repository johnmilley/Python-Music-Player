# Custom views with / search and Enter-to-open
# Overrides keyPressEvent to disable default type-to-search

from PyQt5.QtWidgets import QTreeView, QListWidget, QLineEdit
from PyQt5.QtCore import Qt


class VimTreeView(QTreeView):
    """QTreeView with / search and Enter-to-open."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_bar = None

    def set_search_bar(self, search_bar):
        self._search_bar = search_bar

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Slash:
            if self._search_bar:
                self._search_bar.setVisible(True)
                self._search_bar.setFocus()
                self._search_bar.clear()
        elif key == Qt.Key_Escape:
            if self._search_bar and self._search_bar.isVisible():
                self._search_bar.setVisible(False)
                self.setFocus()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            idx = self.currentIndex()
            if idx.isValid():
                self.doubleClicked.emit(idx)
        else:
            super().keyPressEvent(event)


class VimListWidget(QListWidget):
    """QListWidget with / search and Enter-to-open."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_bar = None

    def set_search_bar(self, search_bar):
        self._search_bar = search_bar

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Slash:
            if self._search_bar:
                self._search_bar.setVisible(True)
                self._search_bar.setFocus()
                self._search_bar.clear()
        elif key == Qt.Key_Escape:
            if self._search_bar and self._search_bar.isVisible():
                self._search_bar.setVisible(False)
                self.setFocus()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            item = self.currentItem()
            if item:
                self.itemDoubleClicked.emit(item)
        else:
            super().keyPressEvent(event)


class SearchBar(QLineEdit):
    """Search bar that filters a list/tree and returns focus on Escape."""

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.setPlaceholderText('Search...')
        self.setVisible(False)
        self.setObjectName('search-bar')

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.setVisible(False)
            self.view.setFocus()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.setVisible(False)
            self.view.setFocus()
        else:
            super().keyPressEvent(event)
