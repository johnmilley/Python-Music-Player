# Custom views with vim-style navigation
# j/k for up/down, h/l for tree expand/collapse, / for search, Enter to open
# Consumes letter keys to prevent default type-to-search

from PyQt5.QtWidgets import QTreeView, QListWidget, QLineEdit
from PyQt5.QtCore import Qt


class VimTreeView(QTreeView):
    """QTreeView with vim-style j/k/h/l navigation and / search."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_bar = None

    def set_search_bar(self, search_bar):
        self._search_bar = search_bar

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_J:
            idx = self.moveCursor(self.MoveDown, Qt.NoModifier)
            self.setCurrentIndex(idx)
        elif key == Qt.Key_K:
            idx = self.moveCursor(self.MoveUp, Qt.NoModifier)
            self.setCurrentIndex(idx)
        elif key == Qt.Key_L:
            # Expand, or move to first child if already expanded
            idx = self.currentIndex()
            if idx.isValid():
                if not self.isExpanded(idx):
                    self.expand(idx)
                else:
                    child = self.model().index(0, 0, idx)
                    if child.isValid():
                        self.setCurrentIndex(child)
        elif key == Qt.Key_H:
            # Collapse, or move to parent if already collapsed
            idx = self.currentIndex()
            if idx.isValid():
                if self.isExpanded(idx):
                    self.collapse(idx)
                else:
                    parent = idx.parent()
                    if parent.isValid():
                        self.setCurrentIndex(parent)
        elif key == Qt.Key_Escape:
            if self._search_bar and self._search_bar.isVisible():
                self._search_bar.setVisible(False)
                self.setFocus()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            idx = self.currentIndex()
            if idx.isValid():
                self.doubleClicked.emit(idx)
        elif event.text() and event.text().isprintable() and len(event.text()) == 1:
            # Consume printable keys to prevent type-to-search
            return
        else:
            super().keyPressEvent(event)


class VimListWidget(QListWidget):
    """QListWidget with vim-style j/k navigation and / search."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_bar = None

    def set_search_bar(self, search_bar):
        self._search_bar = search_bar

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_J:
            row = self.currentRow()
            if row < self.count() - 1:
                self.setCurrentRow(row + 1)
        elif key == Qt.Key_K:
            row = self.currentRow()
            if row > 0:
                self.setCurrentRow(row - 1)
        elif key == Qt.Key_Escape:
            if self._search_bar and self._search_bar.isVisible():
                self._search_bar.setVisible(False)
                self.setFocus()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            item = self.currentItem()
            if item:
                self.itemDoubleClicked.emit(item)
        elif event.text() and event.text().isprintable() and len(event.text()) == 1:
            # Consume printable keys to prevent type-to-search
            # (h/l are intercepted by App's eventFilter before reaching here)
            return
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
