# ServerDialog — the Preferences > Remote Access... dialog.
#
# Thin UI over App's _start_media_server()/_stop_media_server(): the dialog
# never owns the server, it just reflects and edits its settings
# (server/enabled, server/port, server/token) and shows the URLs to type on
# the phone. Port changes while running restart the server; token changes
# apply live (handlers read it per-request).

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QSpinBox, QPushButton)
from PyQt5.QtCore import Qt

import theme
from media_server import DEFAULT_PORT, generate_token, local_addresses


class ServerDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent or app)
        self.app = app
        self.setWindowTitle('Remote Access')
        self.setMinimumWidth(420)
        self.setStyleSheet(theme.dialog_qss(app.effective_theme))
        t = app.effective_theme

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        blurb = QLabel(
            'Stream this library to your phone over your home network or '
            'Tailscale. Open one of the URLs below in the phone’s browser.')
        blurb.setWordWrap(True)
        blurb.setStyleSheet(f'color: {t["fg_dim"]};')
        layout.addWidget(blurb)

        self.enable_box = QCheckBox('Enable remote access')
        self.enable_box.setChecked(
            app.settings.value('server/enabled', 'false') == 'true')
        self.enable_box.toggled.connect(self._on_toggle)
        layout.addWidget(self.enable_box)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel('Port:'))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(
            int(app.settings.value('server/port', DEFAULT_PORT)))
        self.port_spin.editingFinished.connect(self._on_port_changed)
        port_row.addWidget(self.port_spin)
        port_row.addStretch()
        layout.addLayout(port_row)

        token_row = QHBoxLayout()
        token_row.addWidget(QLabel('Token:'))
        self.token_label = QLabel(app.settings.value('server/token', ''))
        self.token_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        token_row.addWidget(self.token_label)
        token_row.addStretch()
        regen = QPushButton('Regenerate')
        regen.clicked.connect(self._regen_token)
        token_row.addWidget(regen)
        layout.addLayout(token_row)

        self.urls_label = QLabel()
        self.urls_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.urls_label.setWordWrap(True)
        layout.addWidget(self.urls_label)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f'color: {t["fg_dim"]};')
        layout.addWidget(self.status_label)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self._refresh()

    # ── handlers ────────────────────────────────────────────────────

    def _on_toggle(self, checked):
        self.app.settings.setValue('server/enabled',
                                   'true' if checked else 'false')
        if checked:
            self.app._start_media_server()
        else:
            self.app._stop_media_server()
        self._refresh()

    def _on_port_changed(self):
        port = self.port_spin.value()
        if str(port) == str(self.app.settings.value('server/port',
                                                    DEFAULT_PORT)):
            return
        self.app.settings.setValue('server/port', port)
        if self.enable_box.isChecked():
            self.app._stop_media_server()
            self.app._start_media_server()
        self._refresh()

    def _regen_token(self):
        token = generate_token()
        self.app.settings.setValue('server/token', token)
        self.token_label.setText(token)
        if self.app._media_server:
            self.app._media_server.set_token(token)
        self._refresh()

    # ── display ─────────────────────────────────────────────────────

    def _refresh(self):
        running = (self.app._media_server is not None
                   and self.app._media_server.running)
        token = self.app.settings.value('server/token', '')
        port = self.port_spin.value()
        if running:
            lines = [f'{label}:  http://{ip}:{port}/?token={token}'
                     for label, ip in local_addresses()]
            self.urls_label.setText(
                '\n'.join(lines) or f'http://<this-machine>:{port}/?token={token}')
            self.status_label.setText(
                'Running. The token is remembered by the phone after the '
                'first visit.')
        else:
            self.urls_label.setText('')
            err = getattr(self.app, '_media_server_error', '')
            self.status_label.setText(
                f'Could not start: {err}' if err else 'Not running.')
