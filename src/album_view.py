# AlbumView widget displays the tracks of an album.

import sys
from pathlib import Path

# pyqt5
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QListWidgetItem,
    QStyledItemDelegate, QStyle
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QRect
from PyQt5.QtGui import QColor, QFontMetrics, QTextOption

# local
from album import Album
from vim_views import VimListWidget, SearchBar


class WrapIndentDelegate(QStyledItemDelegate):
    """Wraps track text to a second indented line when it doesn't fit."""

    INDENT = 20  # pixels for continuation indent

    def _split_text(self, text, fm, width):
        """Return (first_line, remainder) splitting at the last word that fits."""
        if fm.horizontalAdvance(text) <= width:
            return text, ''
        # Find the last space that fits on the first line
        last_space = -1
        for i, ch in enumerate(text):
            if ch == ' ':
                if fm.horizontalAdvance(text[:i]) <= width:
                    last_space = i
                else:
                    break
        if last_space > 0:
            return text[:last_space], text[last_space + 1:]
        # No good break point — hard break
        for i in range(len(text)):
            if fm.horizontalAdvance(text[:i + 1]) > width:
                return text[:i], text[i:]
        return text, ''

    def paint(self, painter, option, index):
        self.initStyleOption(option, index)
        text = option.text
        fm = QFontMetrics(option.font)
        padding = 4
        avail = option.rect.width() - 2 * padding

        # Draw background / selection
        option.text = ''
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, option, painter, option.widget)

        # Use the selection text color stored on the widget when focused+selected,
        # otherwise use normal text color
        if option.state & QStyle.State_Selected and option.widget and option.widget.hasFocus():
            sel_color = getattr(option.widget, '_selection_text_color', None)
            pen_color = QColor(sel_color) if sel_color else option.palette.color(option.palette.HighlightedText)
        else:
            pen_color = option.palette.color(option.palette.Text)

        if fm.horizontalAdvance(text) <= avail:
            # Single line — draw normally
            text_rect = option.rect.adjusted(padding, 0, -padding, 0)
            painter.setPen(pen_color)
            painter.setFont(option.font)
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        else:
            # Two lines with indent on continuation
            first, rest = self._split_text(text, fm, avail)
            line_h = fm.height()
            painter.setPen(pen_color)
            painter.setFont(option.font)
            r1 = QRect(option.rect.x() + padding, option.rect.y() + 1,
                        avail, line_h)
            painter.drawText(r1, Qt.AlignVCenter | Qt.AlignLeft, first)
            if rest:
                r2 = QRect(option.rect.x() + padding + self.INDENT,
                           option.rect.y() + 1 + line_h,
                           avail - self.INDENT, line_h)
                painter.drawText(r2, Qt.AlignVCenter | Qt.AlignLeft, rest)

    def sizeHint(self, option, index):
        self.initStyleOption(option, index)
        text = option.text
        fm = QFontMetrics(option.font)
        padding = 4
        avail = option.rect.width() - 2 * padding if option.rect.width() > 0 else 200
        line_h = fm.height()
        vpad = 4

        if avail > 0 and fm.horizontalAdvance(text) > avail:
            return QSize(option.rect.width(), line_h * 2 + vpad)
        return QSize(option.rect.width(), line_h + vpad)


class AlbumView(QWidget):
    album_changed = pyqtSignal(str)

    def __init__(self, player=None):
        super().__init__()
        self.setWindowTitle("Tracklist")
        self.setMinimumWidth(150)
        self.current_track = None
        self.album = None
        self.init_gui()
        self.player = player

    def init_gui(self):
        """
            builds the GUI and connects events
        """
        layout_main = QVBoxLayout()

        self.track_list_widget = VimListWidget()
        self.track_list_widget.addItem("No album loaded")
        self.track_list_widget.setObjectName('track-list')
        self._wrap_delegate = WrapIndentDelegate(self.track_list_widget)
        self.track_list_widget.setItemDelegate(self._wrap_delegate)
        self.track_list_widget.itemDoubleClicked.connect(self.set_current_track)

        # Search bar
        self.search_bar = SearchBar(self.track_list_widget)
        self.track_list_widget.set_search_bar(self.search_bar)
        self.search_bar.textChanged.connect(self._on_search)

        layout_main.addWidget(self.search_bar)
        layout_main.addWidget(self.track_list_widget)

        self.setLayout(layout_main)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Recalculate item sizes when width changes so wrapping updates
        for row in range(self.track_list_widget.count()):
            item = self.track_list_widget.item(row)
            hint = self.track_list_widget.itemDelegate().sizeHint(
                self.track_list_widget.viewOptions(), self.track_list_widget.indexFromItem(item))
            item.setSizeHint(hint)

    def _on_search(self, text):
        """Jump to first track matching the search text."""
        if not text:
            return
        for row in range(self.track_list_widget.count()):
            item = self.track_list_widget.item(row)
            if text.lower() in item.text().lower():
                self.track_list_widget.setCurrentRow(row)
                self.track_list_widget.scrollToItem(item)
                break

    def load_album_listing(self, directory_path):
        """
            builds an Album object from any dir that contains music files (mp3, flac)
        """
        self.track_list_widget.clear()

        self.album = Album(Path(directory_path))

        if self.album.tracklist:
            for i, track in enumerate(self.album.tracklist):
                item = QListWidgetItem(str(track))
                item.setData(Qt.UserRole, i)
                self.track_list_widget.addItem(item)
            # LOAD DATA into PLAYER
            if self.player:
                self.player.album = self.album
                self.player.load_album_art(self.player.album)
                self.player.track_pos = 0
            # Emit after player has the album so listeners can read album art
            if self.album.title and self.album.artist:
                self.album_changed.emit(f"{self.album.title} - {self.album.artist}")
        else:
            self.track_list_widget.addItem("No music files found.")
            self.setWindowTitle(f"Tracklist")

    def set_current_track(self, selected):
        track_pos = selected.data(Qt.UserRole)
        self.current_track = self.album.tracklist[track_pos]
        print(f"Current track: {self.current_track}")

        # Send Album to Player
        if self.player:
            self.player.play(self.album, track_pos)

    def get_current_track(self):
        if self.current_track:
            return self.current_track

def main():
    app = QApplication(sys.argv)
    album_view = AlbumView()

    album_view.base_directory = '/Users/jlm/Downloads/music/Carly Rae Jepsen - Emotion (10th Anniversary Edition) - (2025)'
    album_view.load_album_listing(album_view.base_directory)

    album_view.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
