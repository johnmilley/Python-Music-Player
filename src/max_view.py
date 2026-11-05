# MaxView — fullscreen "max mode" page: large album art beside a side column
# with independently toggleable tracklist/lyrics panes, and the unified
# ControlPanel (title, favourite, progress/time, transport, tracklist/lyrics
# toggles, back, ⋯ menu) floating over the art on hover — same panel the
# main window's stage uses.
#
# Lives permanently as a page on the app's root QStackedWidget. It reuses
# the player's art pipeline (via the art_changed signal) and borrows the
# app's single AlbumView/LyricsWidget while active — nothing is duplicated
# or rebuilt per entry, so there is no copy-over bookkeeping and no settle
# timers.

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QToolButton, QApplication)
from PyQt5.QtCore import Qt, QSize, QEvent, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon

from art_label import AlbumArtLabel
from player import _render_svg
import overlay_controls


class MaxView(QWidget):
    exit_requested = pyqtSignal()
    volume_wheel = pyqtSignal(int)  # wheel over the art/panel (see Player)

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.setObjectName('max-mode')
        self.setFocusPolicy(Qt.StrongFocus)
        # Required for QSS background painting on QWidget subclasses
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Accent divider along the top edge
        self.divider = QWidget()
        self.divider.setObjectName('max-divider')
        self.divider.setFixedHeight(2)
        layout.addWidget(self.divider)

        content = QHBoxLayout()
        content.setContentsMargins(24, 24, 24, 24)
        content.setSpacing(24)

        self.art = AlbumArtLabel()
        self.art.setMinimumSize(300, 300)
        content.addWidget(self.art, stretch=2)

        # Side column: a tracklist slot and a lyrics slot, each independently
        # toggleable and each a reparenting slot for the app's one true
        # AlbumView / LyricsWidget. The whole column hides itself when both
        # slots are empty of content. The track title lives in the hover
        # ControlPanel below, not here — same configuration in every mode.
        self.side_column = QWidget()
        self.side_column.setObjectName('max-lyrics-column')
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)

        self.tracklist_on = False
        self.lyrics_on = True
        self.tracklist_wrap = QWidget()
        self.tracklist_slot = QVBoxLayout(self.tracklist_wrap)
        self.tracklist_slot.setContentsMargins(0, 0, 0, 0)
        self.tracklist_wrap.hide()  # off by default each time max mode opens
        col.addWidget(self.tracklist_wrap, stretch=1)

        self.lyrics_wrap = QWidget()
        self.lyrics_slot = QVBoxLayout(self.lyrics_wrap)
        self.lyrics_slot.setContentsMargins(0, 0, 0, 0)
        self.lyrics_slot.setSpacing(4)
        self.lyrics_title = QLabel()
        self.lyrics_title.setObjectName('max-lyrics-title')
        self.lyrics_title.setWordWrap(True)
        self.lyrics_slot.addWidget(self.lyrics_title)
        col.addWidget(self.lyrics_wrap, stretch=1)

        self.side_column.setLayout(col)
        content.addWidget(self.side_column, stretch=1)

        layout.addLayout(content, stretch=1)
        self.setLayout(layout)

        # Corner close button — overlaid top-right, since there's no toolbar
        # visible in fullscreen max mode to hold an exit control. Redundant
        # with the panel's own back button, but stays reachable even while
        # the hover panel is idle-hidden.
        self.close_btn = QToolButton(self)
        self.close_btn.setObjectName('max-close-btn')
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setIconSize(QSize(14, 14))
        self.close_btn.setToolTip('Back to normal window (Esc)')
        self.close_btn.clicked.connect(self.exit_requested.emit)
        self.close_btn.raise_()

        # Hover control panel: title/favourite, progress/time, transport +
        # pane toggles + back — shown on mouse motion and auto-hidden after
        # a few idle seconds (there is no toolbar in fullscreen, so this is
        # the pointer's way in). Same widget as the stage's; ⋯ opens the
        # app menu (also on right-click of the art).
        self.panel = overlay_controls.ControlPanel(self, show_back=True, show_more=True)
        self.panel.back_btn.setToolTip('Back to normal window (Esc)')
        self.panel.back_clicked.connect(self.exit_requested.emit)
        self.panel.set_toggle_states(self.tracklist_on, self.lyrics_on)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(overlay_controls.IDLE_HIDE_MS)
        self._idle_timer.timeout.connect(self._hide_hover_controls)
        self.controls_pinned = False  # see set_controls_pinned
        self._wheel_acc = 0
        self.volume_osd = overlay_controls.VolumeOSD(self)
        # Mouse-move never reaches this widget's own handlers while the
        # cursor is over a child (the art, the borrowed panes) — watch
        # application-wide. Installed only while
        # max mode is actually showing (see showEvent/hideEvent): an
        # app-wide filter sees every event in the entire application, so
        # leaving it installed permanently taxes normal-mode use for a
        # mode that isn't on screen.

        player.art_changed.connect(self.art.set_source)
        player.track_changed.connect(self._on_track_changed)
        player.play_state_changed.connect(self.set_playing)
        # Hover arrows scroll the album's art gallery here too
        player.register_art_label(self.art)
        # Progress bar / time labels mirror the player column's own
        player.register_progress_display(
            self.panel.progress_bar, self.panel.pos_label, self.panel.len_label)

    def set_playing(self, playing):
        self.panel.set_playing(playing)

    # ── Hover controls show/hide ────────────────────────────────────

    def _position_controls(self):
        overlay_controls.position_control_panel(
            self.panel, self.art.x(), self.art.y(),
            self.art.width(), self.art.height())

    def _show_hover_controls(self):
        # Runs on every app-wide MouseMove while max mode is up — only do
        # the layout/stacking work on the hidden -> shown transition
        if not self.panel.isVisible():
            self._position_controls()
            self.panel.show()
            self.panel.raise_()
        self._idle_timer.start()

    def _hide_hover_controls(self):
        self._idle_timer.stop()
        if not self.controls_pinned and not self.panel.volume_popup_open():
            self.panel.hide()

    def set_controls_pinned(self, on):
        """Same as Player.set_controls_pinned: a pinned panel stays up."""
        self.controls_pinned = on
        if on:
            if self.isVisible():
                self._show_hover_controls()
        else:
            self._idle_timer.start()

    def flash_volume(self, volume, muted):
        self.volume_osd.flash(volume, muted, self.art.geometry())

    def _over_art_or_panel(self, obj):
        w = obj if isinstance(obj, QWidget) else None
        while w is not None:
            if w is self.art or w is self.panel:
                return True
            w = w.parentWidget()
        return False

    def eventFilter(self, obj, event):
        t = event.type()
        if (t == QEvent.Wheel and self.isVisible()
                and self._over_art_or_panel(obj)):
            # Volume over the art/panel only — the borrowed tracklist and
            # lyrics panes keep scrolling normally
            self._wheel_acc += event.angleDelta().y()
            steps = int(self._wheel_acc / 120)
            if steps:
                self._wheel_acc -= steps * 120
                self.volume_wheel.emit(steps)
            return True
        if (t == QEvent.MouseMove and self.isVisible()
                and self.window().isActiveWindow()):
            self._show_hover_controls()
        elif t == QEvent.Resize and obj is self.art and not self.panel.isHidden():
            # Toggling the side panes resizes the art, not this view
            self._position_controls()
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        super().showEvent(event)
        if self.controls_pinned:
            # After layout settles, so the panel lands on the final art rect
            QTimer.singleShot(0, self._show_hover_controls)

    def hideEvent(self, event):
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._hide_hover_controls()
        super().hideEvent(event)

    def leaveEvent(self, event):
        self._hide_hover_controls()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.close_btn.move(self.width() - self.close_btn.width() - 12, 12)
        if self.panel.isVisible():
            self._position_controls()

    def set_close_icon_color(self, color):
        self.close_btn.setIcon(QIcon(_render_svg('close', color, 14)))

    def _on_track_changed(self, track):
        self.set_title(str(getattr(track, 'title', '') or ''))

    def set_title(self, title):
        self.panel.set_title(title)
        self.lyrics_title.setText(title)

    def set_favorited(self, on):
        self.panel.set_favorited(on)

    def set_heart_visible(self, visible):
        self.panel.set_heart_visible(visible)

    def attach_lyrics(self, lyrics_widget):
        """Borrow the app's lyrics widget (reparents it into this view)."""
        self.lyrics_slot.addWidget(lyrics_widget)
        lyrics_widget.setVisible(True)

    def attach_tracklist(self, album_view):
        """Borrow the app's AlbumView/tracklist (reparents it into this view)."""
        self.tracklist_slot.addWidget(album_view)
        album_view.setVisible(True)

    def set_lyrics_visible(self, on):
        self.lyrics_on = on
        self.lyrics_wrap.setVisible(on)
        self._update_side_column()
        self.panel.set_toggle_states(self.tracklist_on, self.lyrics_on)

    def set_tracklist_visible(self, on):
        self.tracklist_on = on
        self.tracklist_wrap.setVisible(on)
        self._update_side_column()
        self.panel.set_toggle_states(self.tracklist_on, self.lyrics_on)

    def _update_side_column(self):
        """Collapse the whole side column when neither pane is showing, so
        the art gets the full width (mirrors PanelManager's right-column
        collapse in normal mode). Tracked with explicit flags rather than
        isVisible(), since a wrap's own visible-flag is unreliable to read
        back the instant its ancestor (this column) is hidden/shown too."""
        self.side_column.setVisible(self.tracklist_on or self.lyrics_on)
