# QuickSwitcher — Ctrl+K: a search box floating over the window that lists
# every album in the library; type a few letters of the artist and/or album
# ("big pi"), Enter opens it in the library pane's tracklist.
#
# The album list comes from media_server.LibraryCache — the same
# stale-while-revalidate folder walk the phone client uses (a folder is an
# album if it directly holds audio files). App warms it at startup on a
# background thread, so it's normally ready by the first Ctrl+K; if not,
# the box says so and fills in when the walk lands. Walking never happens
# on the UI thread — a big NAS library takes tens of seconds.

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem
from PyQt5.QtCore import Qt, QThread, QEvent, pyqtSignal

import bg_threads

MAX_ROWS = 200  # matches shown at once — typing narrows; keeps refilters instant


class _WalkThread(QThread):
    """Fetch the (possibly not yet walked) album list off the UI thread.
    Named albums_ready, not 'finished' — see bg_threads.retire()."""
    albums_ready = pyqtSignal(object)  # list of album dicts

    def __init__(self, cache, root):
        super().__init__()
        self._cache, self._root = cache, root

    def run(self):
        try:
            albums = self._cache.albums(self._root)
        except OSError:
            albums = []
        self.albums_ready.emit(albums)


def _score(query_words, haystack, words):
    """None if any query word is missing; otherwise higher = better.
    Word-start hits beat mid-word hits ('pi' → 'Pink' over 'Spiral')."""
    score = 0
    for q in query_words:
        if q not in haystack:
            return None
        score += 2 if any(w.startswith(q) for w in words) else 1
    return score


class QuickSwitcher(QFrame):
    album_chosen = pyqtSignal(str)  # album id (POSIX relpath under the root)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('quick-switcher')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._entries = []   # (display, haystack, words, id)
        self._loaded = False
        self._thread = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        self.input = QLineEdit()
        self.input.setObjectName('quick-switcher-input')
        self.input.setPlaceholderText('Jump to album…')
        self.input.textChanged.connect(self._refilter)
        self.input.installEventFilter(self)
        lay.addWidget(self.input)
        self.list = QListWidget()
        self.list.setObjectName('quick-switcher-list')
        self.list.setUniformItemSizes(True)
        self.list.setFocusPolicy(Qt.NoFocus)  # typing always stays in the box
        self.list.itemClicked.connect(self._choose)
        lay.addWidget(self.list, stretch=1)
        self.hide()

    # ── Data ────────────────────────────────────────────────────────

    def refresh(self, cache, root):
        """Fetch the album list in the background (warm-up at startup, and
        on every open — a cache hit returns at once and re-walks in the
        background when stale). One fetch at a time: a never-walked root
        would otherwise be walked twice in parallel."""
        if not root or (self._thread is not None and self._thread.isRunning()):
            return
        if self._thread is not None:
            bg_threads.retire(self._thread)
        self._thread = _WalkThread(cache, root)
        self._thread.albums_ready.connect(self.set_albums)
        self._thread.start()

    def set_albums(self, albums):
        """Album dicts from LibraryCache: 'name' (folder), 'parent' (path
        of the folder above — usually the artist), 'id'."""
        entries = []
        for a in albums:
            parent = a['parent'].rsplit('/', 1)[-1]
            display = f"{a['name']}  —  {parent}" if parent else a['name']
            haystack = f"{a['parent']} {a['name']}".lower()
            words = haystack.replace('/', ' ').replace('-', ' ').replace('_', ' ').split()
            entries.append((display, haystack, words, a['id']))
        self._entries = entries
        self._loaded = True
        if self.isVisible():
            self._refilter(self.input.text())

    # ── Show / hide ─────────────────────────────────────────────────

    def open(self):
        self.input.clear()
        self._refilter('')
        self.show()
        self.raise_()
        self.input.setFocus()

    def _reposition(self):
        """Centered near the top, as tall as its rows (capped)."""
        host = self.parentWidget().rect()
        w = min(host.width() - 24, 520)
        margins = self.layout().contentsMargins()
        rows_h = self.list.sizeHintForRow(0) * max(self.list.count(), 1) + 4
        h = (margins.top() + margins.bottom() + self.input.sizeHint().height()
             + self.layout().spacing() + rows_h)
        h = min(h, host.height() - 24, 380)
        self.setGeometry(host.x() + (host.width() - w) // 2, host.y() + 12, w, h)

    def contains_focus(self, widget):
        return widget is not None and (widget is self or self.isAncestorOf(widget))

    # ── Filtering / choosing ────────────────────────────────────────

    def _refilter(self, text):
        self.list.clear()
        if not self._loaded:
            self.list.addItem('Scanning library…')
            self._reposition()
            return
        query = text.lower().split()
        if not query:
            matches = self._entries[:MAX_ROWS]
        else:
            scored = []
            for entry in self._entries:
                s = _score(query, entry[1], entry[2])
                if s is not None:
                    scored.append((-s, entry[0].lower(), entry))
            scored.sort()
            matches = [e for _, _, e in scored[:MAX_ROWS]]
        if not matches:
            self.list.addItem('No matching albums')
            self._reposition()
            return
        for display, _, _, album_id in matches:
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, album_id)
            self.list.addItem(item)
        self.list.setCurrentRow(0)
        self._reposition()

    def _choose(self, item=None):
        item = item or self.list.currentItem()
        album_id = item.data(Qt.UserRole) if item else None
        if album_id is None:
            return
        self.hide()
        self.album_chosen.emit(album_id)

    def _move(self, delta):
        row = self.list.currentRow() + delta
        if 0 <= row < self.list.count():
            self.list.setCurrentRow(row)

    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.KeyPress:
            key, ctrl = event.key(), event.modifiers() & Qt.ControlModifier
            if key == Qt.Key_Escape:
                self.hide()
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._choose()
                return True
            if key == Qt.Key_Down or (ctrl and key in (Qt.Key_J, Qt.Key_N)):
                self._move(1)
                return True
            if key == Qt.Key_Up or (ctrl and key in (Qt.Key_K, Qt.Key_P)):
                self._move(-1)
                return True
            if key in (Qt.Key_PageDown, Qt.Key_PageUp):
                self._move(10 if key == Qt.Key_PageDown else -10)
                return True
        return super().eventFilter(obj, event)
