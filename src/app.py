# App contains Player, Album View, and FolderView widgets

import sys
from pathlib import Path

# local
from folder_view import FolderView
from player import Player
from album_view import AlbumView
import theme

from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QHBoxLayout,
    QAction, QActionGroup, QSplitter, QColorDialog, QShortcut, QDialog,
    QVBoxLayout, QLabel, QLineEdit)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QColor, QPixmap, QIcon, QKeySequence


class App(QMainWindow):
    def __init__(self):
        super().__init__()

        self.app_widget = QWidget()
        self.app_widget.setObjectName('main-window')

        self.player = Player()
        self.album_view = AlbumView()
        self.folder_view = FolderView(self.album_view)

        # Player and AlbumView coupling
        self.player.album_view = self.album_view
        self.player.folder_view = self.folder_view
        self.album_view.player = self.player

        self.setWindowTitle("lp")
        icon_path = Path(__file__).parent.parent / 'icon.png'
        self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(800, 600)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName('main-splitter')
        self.splitter.addWidget(self.folder_view)
        self.splitter.addWidget(self.player)
        self.splitter.addWidget(self.album_view)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 2)
        self.splitter.setCollapsible(0, False)  # folder view
        self.splitter.setCollapsible(1, False)  # player
        self.splitter.setCollapsible(2, False)  # album view

        self.layout_app = QHBoxLayout()
        self.layout_app.setContentsMargins(0, 0, 0, 0)
        self.layout_app.addWidget(self.splitter)
        self.app_widget.setLayout(self.layout_app)

        self.setCentralWidget(self.app_widget)

        # Menu bar — Preferences
        self.prefs_menu = self.menuBar().addMenu('Preferences')

        self.dark_mode_action = QAction('Dark Mode', self)
        self.dark_mode_action.triggered.connect(self.toggle_theme)
        self.prefs_menu.addAction(self.dark_mode_action)

        # Font size submenu
        self.font_size_menu = self.prefs_menu.addMenu('Font Size')
        self.font_size_group = QActionGroup(self)
        self.font_size = theme.DEFAULT_FONT_SIZE
        for size in theme.FONT_SIZES:
            action = QAction(f'{size}pt', self)
            action.setCheckable(True)
            action.setData(size)
            if size == theme.DEFAULT_FONT_SIZE:
                action.setChecked(True)
            action.triggered.connect(lambda checked, s=size: self.set_font_size(s))
            self.font_size_group.addAction(action)
            self.font_size_menu.addAction(action)

        # Accent color submenu
        self.accent_menu = self.prefs_menu.addMenu('Accent Color')
        self.accent_group = QActionGroup(self)
        self.accent_color = theme.DEFAULT_ACCENT
        for name, color in theme.ACCENT_PRESETS.items():
            action = QAction(name, self)
            action.setCheckable(True)
            action.setData(color)
            action.setIcon(self._color_icon(color))
            if name == 'Orange':
                action.setChecked(True)
            action.triggered.connect(lambda checked, c=color: self.set_accent(c))
            self.accent_group.addAction(action)
            self.accent_menu.addAction(action)
        self.accent_menu.addSeparator()
        custom_action = QAction('Custom...', self)
        custom_action.triggered.connect(self.pick_custom_accent)
        self.accent_menu.addAction(custom_action)

        # Miniplayer state
        self.is_miniplayer = False
        self._pre_mini_geometry = None
        self._pre_mini_splitter = None

        # Theme setup
        self.current_theme = theme.LIGHT
        self.apply_theme(self.current_theme)

        self.album_view.album_changed.connect(self.setWindowTitle)

        # Restore saved state
        self.settings = QSettings('lp', 'music-player')
        self._restore_state()

        # Keyboard shortcuts
        self._setup_shortcuts()

    def apply_theme(self, t):
        self.current_theme = t
        # Update menu text to show available action
        if t is theme.DARK:
            self.dark_mode_action.setText('Light Mode')
        else:
            self.dark_mode_action.setText('Dark Mode')
        # Override accent/selection with user's chosen color
        t = dict(t)
        t['accent'] = self.accent_color
        t['selection'] = self.accent_color
        fs = self.font_size
        compact = self.is_miniplayer
        self.setStyleSheet(theme.app_qss(t))
        self.player.setStyleSheet(theme.player_qss(t, fs, compact))
        self.folder_view.setStyleSheet(theme.folder_view_qss(t, fs))
        self.album_view.setStyleSheet(theme.album_view_qss(t, fs))

    def toggle_theme(self):
        if self.current_theme is theme.LIGHT:
            self.apply_theme(theme.DARK)
        else:
            self.apply_theme(theme.LIGHT)

    def set_font_size(self, size):
        self.font_size = size
        self.apply_theme(self.current_theme)

    def set_accent(self, color):
        self.accent_color = color
        self.apply_theme(self.current_theme)

    def pick_custom_accent(self):
        color = QColorDialog.getColor(QColor(self.accent_color), self, 'Pick Accent Color')
        if color.isValid():
            # Uncheck any preset
            checked = self.accent_group.checkedAction()
            if checked:
                checked.setChecked(False)
            self.set_accent(color.name())

    def _color_icon(self, color, width=64, height=16):
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(color))
        return QIcon(pixmap)

    def _restore_state(self):
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
        splitter_state = self.settings.value('splitter')
        if splitter_state:
            self.splitter.restoreState(splitter_state)
        saved_fs = self.settings.value('font_size', type=int)
        if saved_fs and saved_fs in theme.FONT_SIZES:
            self.font_size = saved_fs
            for action in self.font_size_group.actions():
                if action.data() == saved_fs:
                    action.setChecked(True)
        saved_accent = self.settings.value('accent_color')
        if saved_accent:
            self.accent_color = saved_accent
            # Check matching preset, if any
            for action in self.accent_group.actions():
                action.setChecked(action.data() == saved_accent)
        if self.settings.value('dark_mode') == 'true':
            self.apply_theme(theme.DARK)
        else:
            self.apply_theme(self.current_theme)
        if self.settings.value('miniplayer') == 'true':
            self.enter_miniplayer()
        last_album = self.settings.value('last_album')
        if last_album:
            self.album_view.load_album_listing(last_album)
            track_pos = self.settings.value('last_track_pos', 0, type=int)
            seek_pos = self.settings.value('last_seek_pos', 0.0, type=float)
            if self.album_view.album and track_pos < len(self.album_view.album.tracklist):
                self.player.load_track(self.album_view.album, track_pos, seek_pos)

    def _setup_shortcuts(self):
        self.keybindings = [
            ('p',       'Play / Pause',       self.player.toggle_play_pause_button_text),
            ('>',       'Next track',          self.player.next_track),
            ('<',       'Previous track',      self.player.prev_track),
            ('f',       'Seek forward 5s',     lambda: self._seek_relative(5)),
            ('b',       'Seek back 5s',        lambda: self._seek_relative(-5)),
            ('.',       'Volume up',           lambda: self._adjust_volume(0.05)),
            (',',       'Volume down',         lambda: self._adjust_volume(-0.05)),
            ('1',       'Toggle library',      lambda: self.exit_miniplayer() if self.is_miniplayer else self.player.toggle_library()),
            ('2',       'Toggle tracklist',    lambda: self.exit_miniplayer() if self.is_miniplayer else self.player.toggle_tracklist()),
            ('m',       'Toggle miniplayer',   self.toggle_miniplayer),
            ('q',       'Quit',                self.close),
            ('?',       'Show shortcuts',      self.show_help),
        ]
        for key, _, callback in self.keybindings:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda cb=callback: cb() if not isinstance(self.focusWidget(), QLineEdit) else None)

    def _seek_relative(self, seconds):
        if self.player.current_track and self.player.playback.active:
            pos = self.player.playback.curr_pos + seconds
            pos = max(0, min(pos, self.player.current_track.length))
            self.player.playback.seek(pos)
            self.player.progress_bar.setValue(
                int((pos / self.player.current_track.length) * 1000))
            self.player.track_progress_label.setText(
                self.player.current_track.length_to_string(pos))

    def _adjust_volume(self, delta):
        if self.player.playback.active:
            vol = self.player.playback.volume + delta
            self.player.playback.set_volume(max(0, min(1, vol)))

    def show_help(self):
        t = self.current_theme
        dialog = QDialog(self)
        dialog.setWindowTitle('Keyboard Shortcuts')
        dialog.setStyleSheet(f"""
            QDialog {{ background-color: {t['bg']}; }}
            QLabel {{ color: {t['fg']}; font-family: {theme.FONT}; font-size: 12pt; }}
        """)
        layout = QVBoxLayout()
        nav_keys = [
            ('j / k',   'Navigate down / up'),
            ('h / l',   'Collapse / expand folder'),
            ('/',       'Search in list'),
            ('Esc',     'Close search'),
            ('Enter',   'Open selected'),
            ('G',       'Jump to bottom'),
        ]
        rows = ''.join(
            f'<tr><td style="padding: 4px 20px 4px 0;"><b>{key}</b></td>'
            f'<td style="padding: 4px 0;">{desc}</td></tr>'
            for key, desc, _ in self.keybindings
        )
        nav_rows = ''.join(
            f'<tr><td style="padding: 4px 20px 4px 0;"><b>{key}</b></td>'
            f'<td style="padding: 4px 0;">{desc}</td></tr>'
            for key, desc in nav_keys
        )
        label = QLabel(
            f'<table>{rows}</table>'
            f'<br><b>List Navigation</b>'
            f'<table>{nav_rows}</table>'
        )
        label.setTextFormat(Qt.RichText)
        layout.addWidget(label)
        dialog.setLayout(layout)
        dialog.exec_()

    def toggle_miniplayer(self):
        if self.is_miniplayer:
            self.exit_miniplayer()
        else:
            self.enter_miniplayer()

    def enter_miniplayer(self):
        if self.is_miniplayer:
            return
        self.is_miniplayer = True

        # Save current state for restoration
        self._pre_mini_geometry = self.saveGeometry()
        self._pre_mini_splitter = self.splitter.saveState()
        self._pre_mini_library = self.folder_view.isVisible()
        self._pre_mini_tracklist = self.album_view.isVisible()

        # Hide side panels and menu bar
        self.folder_view.setVisible(False)
        self.album_view.setVisible(False)
        self.menuBar().setVisible(False)

        # Hide non-essential player widgets
        self.player.toggle_library_btn.setVisible(False)
        self.player.toggle_folder_btn.setVisible(False)
        self.player.track_progress_label.setVisible(False)
        self.player.track_length_label.setVisible(False)
        self.player.progress_widget.setVisible(False)

        # Reduce minimum sizes
        self.player.setMinimumSize(200, 250)
        self.setMinimumSize(280, 320)

        # Restyle for compact mode
        self.apply_theme(self.current_theme)

        # Resize to compact
        self.resize(320, 400)

        # Stay on top
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.show()

    def exit_miniplayer(self):
        if not self.is_miniplayer:
            return
        self.is_miniplayer = False

        # Remove stay on top
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()

        # Restore minimum sizes
        self.setMinimumSize(800, 600)
        self.player.setMinimumSize(350, 500)

        # Show everything
        self.menuBar().setVisible(True)
        self.player.toggle_library_btn.setVisible(True)
        self.player.toggle_folder_btn.setVisible(True)
        self.player.track_progress_label.setVisible(True)
        self.player.track_length_label.setVisible(True)
        self.player.progress_widget.setVisible(True)

        # Restore side panels
        self.folder_view.setVisible(self._pre_mini_library)
        self.album_view.setVisible(self._pre_mini_tracklist)
        self.player.toggle_library_btn.setChecked(self._pre_mini_library)
        self.player.toggle_folder_btn.setChecked(self._pre_mini_tracklist)

        # Restyle for normal mode
        self.apply_theme(self.current_theme)

        # Restore geometry
        if self._pre_mini_geometry:
            self.restoreGeometry(self._pre_mini_geometry)
            self.splitter.restoreState(self._pre_mini_splitter)

    def closeEvent(self, event):
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('splitter', self.splitter.saveState())
        self.settings.setValue('dark_mode', 'true' if self.current_theme is theme.DARK else 'false')
        self.settings.setValue('font_size', self.font_size)
        self.settings.setValue('accent_color', self.accent_color)
        self.settings.setValue('miniplayer', 'true' if self.is_miniplayer else 'false')
        if self.album_view.album and self.album_view.album.path:
            self.settings.setValue('last_album', self.album_view.album.path)
        if self.player.current_track:
            self.settings.setValue('last_track_pos', self.player.track_pos)
            self.settings.setValue('last_seek_pos', self.player.playback.curr_pos)
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app_ui = App()
    app_ui.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
