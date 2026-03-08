# Vim-style navigation for QTreeView and QListWidget
# Overrides keyPressEvent to disable default type-to-search
# and add h/j/k/l navigation with / search

from PyQt5.QtWidgets import QTreeView, QListWidget, QLineEdit
from PyQt5.QtCore import Qt, QSortFilterProxyModel


class VimTreeView(QTreeView):
    """QTreeView with vim-style h/j/k/l navigation and / search."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_bar = None

    def set_search_bar(self, search_bar):
        self._search_bar = search_bar

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_J:
            nxt = self.indexBelow(self.currentIndex())
            if nxt.isValid():
                self.setCurrentIndex(nxt)
        elif key == Qt.Key_K:
            prev = self.indexAbove(self.currentIndex())
            if prev.isValid():
                self.setCurrentIndex(prev)
        elif key == Qt.Key_L:
            idx = self.currentIndex()
            if idx.isValid():
                if not self.isExpanded(idx):
                    self.expand(idx)
                else:
                    # move into first child
                    child = self.model().index(0, 0, idx)
                    if child.isValid():
                        self.setCurrentIndex(child)
        elif key == Qt.Key_H:
            idx = self.currentIndex()
            if idx.isValid():
                if self.isExpanded(idx):
                    self.collapse(idx)
                else:
                    # move to parent
                    parent = idx.parent()
                    if parent.isValid() and parent != self.rootIndex():
                        self.setCurrentIndex(parent)
        elif key == Qt.Key_G and event.modifiers() == Qt.NoModifier:
            # gg handled via _pending_g in a simple way: just go to top
            last = self.model().index(self.model().rowCount(self.rootIndex()) - 1, 0, self.rootIndex())
            if last.isValid():
                self.setCurrentIndex(last)
                self.scrollTo(last)
        elif key == Qt.Key_Slash:
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
            # Ignore all other letter keys to prevent type-to-search
            if event.text() and event.text().isalpha():
                return
            super().keyPressEvent(event)


class VimListWidget(QListWidget):
    """QListWidget with vim-style j/k navigation and / search."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_bar = None
        self._all_items = []  # (text, data) for filtering

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
        elif key == Qt.Key_G:
            # G = jump to bottom
            if self.count() > 0:
                self.setCurrentRow(self.count() - 1)
                self.scrollToItem(self.item(self.count() - 1))
        elif key == Qt.Key_Slash:
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
            # Ignore letter keys to prevent type-to-search
            if event.text() and event.text().isalpha():
                return
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
