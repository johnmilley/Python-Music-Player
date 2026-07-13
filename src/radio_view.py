# RadioView — left panel for radio mode
# Shows saved radio stations; selecting one starts streaming

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QLineEdit, QLabel, QMenu, QInputDialog
)
from PyQt5.QtCore import Qt, QSettings, pyqtSignal

from radio_station import RadioStation


class RadioView(QWidget):
    """Left panel showing saved radio stations."""

    station_selected = pyqtSignal(object)  # emits RadioStation
    art_requested = pyqtSignal(object)    # emits RadioStation — user wants to pick art

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(150)
        self._stations = []  # list of RadioStation
        self._loaded = False

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)

        # Add station input — paste URL or type a name to search
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText('Search or paste stream URL...')
        self.url_input.setFocusPolicy(Qt.ClickFocus)
        self.url_input.returnPressed.connect(self._on_input_submitted)
        layout.addWidget(self.url_input)

        # Station list
        self.station_list = QListWidget()
        self.station_list.setObjectName('radio-station-list')
        self.station_list.itemClicked.connect(self._on_station_clicked)
        self.station_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.station_list.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.station_list)

        # Status
        self.status_label = QLabel('')
        self.status_label.setObjectName('radio-status')
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def load_saved_stations(self):
        """Load saved stations from QSettings (once)."""
        if self._loaded:
            return
        self._loaded = True
        settings = QSettings('lp', 'music-player')
        names = settings.value('radio/station_names', [])
        urls = settings.value('radio/station_urls', [])
        if isinstance(names, str):
            names = [names] if names else []
        if isinstance(urls, str):
            urls = [urls] if urls else []
        for name, url in zip(names, urls):
            station = RadioStation(name, url)
            self._stations.append(station)
            item = QListWidgetItem(station.name)
            item.setData(Qt.UserRole, len(self._stations) - 1)
            self.station_list.addItem(item)

    def _save_stations(self):
        settings = QSettings('lp', 'music-player')
        settings.setValue('radio/station_names', [s.name for s in self._stations])
        settings.setValue('radio/station_urls', [s.stream_url for s in self._stations])

    def _on_input_submitted(self):
        text = self.url_input.text().strip()
        if not text:
            return
        if text.startswith('http'):
            self._add_station_url(text)
        else:
            self._open_search(text)

    def _add_station_url(self, url):
        """Add a station by URL, prompting for a name."""
        name, ok = QInputDialog.getText(self, 'Station Name', 'Name:', text=url)
        if not ok or not name.strip():
            return
        name = name.strip()
        self.url_input.clear()
        self._insert_station(name, url)

    def _open_search(self, query):
        from radio_search import RadioSearchDialog
        import theme as theme_mod
        app = self.window()
        t = dict(getattr(app, 'current_theme', theme_mod.LIGHT))
        t['accent'] = getattr(app, 'accent_color', theme_mod.DEFAULT_ACCENT)
        t['selection'] = t['accent']
        dialog = RadioSearchDialog(query, t, parent=self,
                                   fs=getattr(app, 'font_size', None))
        dialog.station_added.connect(self.add_station_external)
        dialog.exec_()

    def add_station_external(self, name, url):
        """Public method to add a station (used by search dialog)."""
        self.url_input.clear()
        self._insert_station(name, url)

    def _insert_station(self, name, url):
        """Add a station to the list and save."""
        station = RadioStation(name, url)
        self._stations.append(station)
        item = QListWidgetItem(station.name)
        item.setData(Qt.UserRole, len(self._stations) - 1)
        self.station_list.addItem(item)
        self._save_stations()

    def _on_station_clicked(self, item):
        idx = item.data(Qt.UserRole)
        if idx is not None and idx < len(self._stations):
            self.station_selected.emit(self._stations[idx])

    def _context_menu(self, pos):
        item = self.station_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self.station_list)
        find_art = menu.addAction('Find Station Art...')
        menu.addSeparator()
        remove = menu.addAction('Remove')
        action = menu.exec_(self.station_list.mapToGlobal(pos))
        if action == find_art:
            idx = item.data(Qt.UserRole)
            if idx is not None and idx < len(self._stations):
                self.art_requested.emit(self._stations[idx])
        elif action == remove:
            idx = item.data(Qt.UserRole)
            row = self.station_list.row(item)
            self.station_list.takeItem(row)
            if idx is not None and idx < len(self._stations):
                self._stations.pop(idx)
            # Re-index remaining items
            for i in range(self.station_list.count()):
                self.station_list.item(i).setData(Qt.UserRole, i)
            self._save_stations()

    def get_station_by_url(self, url):
        for s in self._stations:
            if s.stream_url == url:
                return s
        return None
