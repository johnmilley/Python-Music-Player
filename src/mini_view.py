# MiniView — compact "mini mode": a small, always-on-top square window of
# just the album art, resizable from its invisible edge grips (the window
# stays square). Playback controls float over the art and only appear on
# hover — they hide immediately on leave or whenever the window loses focus,
# and also auto-hide after a few seconds of no mouse movement even while
# still hovering (a QApplication-wide MouseMove filter, since child widgets
# — the art label, the control buttons — swallow mouse-move before it would
# ever reach this window's own event handlers).
# The album's art gallery scrolls here too (AlbumArtLabel's hover arrows).
#
# Lyrics can be toggled on alongside the art: like MaxView, this borrows
# the app's single LyricsWidget by reparenting it into lyrics_slot — the
# app attaches/detaches it (see App._toggle_mini_lyrics).
#
# Key handling is a map of Qt keys -> callables supplied by the app
# (set_key_handlers), so mini mode reuses the same shortcut behaviors
# (play/pause, seek, volume) without duplicating any logic.

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QToolButton, QApplication
from PyQt5.QtCore import Qt, QEvent, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QCursor

from art_label import AlbumArtLabel
from window_chrome import WindowGrips
from player import _render_svg


class MiniView(QWidget):
    exit_requested = pyqtSignal()

    IDLE_HIDE_MS = 2500  # hover controls fade after this long without motion

    def __init__(self, player, parent=None):
        super().__init__(None)
        self.setObjectName('mini-view')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle('lp')
        self.setMinimumSize(180, 180)
        self.resize(320, 320)
        self._player = player
        self._keymap = {}
        self._resizing_self = False  # guard for programmatic resizes
        self.lyrics_on = False

        layout = QHBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)  # keep the hairline border visible
        layout.setSpacing(0)

        self.art = AlbumArtLabel(square=True)
        self.art.setMinimumSize(120, 120)
        self.art.setCursor(Qt.ArrowCursor)
        self.art.installEventFilter(self)  # drag-to-move / double-click exit
        layout.addWidget(self.art)

        # Lyrics column — the app's lyrics widget is reparented in here
        # while lyrics are toggled on
        self.lyrics_column = QWidget()
        self.lyrics_column.setObjectName('mini-lyrics-column')
        self.lyrics_column.setMinimumWidth(160)
        self.lyrics_slot = QVBoxLayout()
        self.lyrics_slot.setContentsMargins(8, 8, 8, 8)
        self.lyrics_column.setLayout(self.lyrics_slot)
        self.lyrics_column.hide()
        layout.addWidget(self.lyrics_column, stretch=1)

        self.setLayout(layout)

        # Hover controls: one translucent bar floating over the art's bottom
        # edge. Independent of the app theme — a dark scrim reads well on
        # any artwork.
        self.controls = QWidget(self)
        self.controls.setObjectName('mini-controls')
        self.controls.setAttribute(Qt.WA_StyledBackground, True)
        self.controls.setStyleSheet("""
            #mini-controls {
                background-color: rgba(20, 20, 20, 150);
                border-radius: 17px;
            }
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 13px;
                color: white;
                font-size: 11pt;
            }
            QToolButton:hover { background-color: rgba(255, 255, 255, 40); }
        """)
        bar = QHBoxLayout()
        bar.setContentsMargins(10, 4, 10, 4)
        bar.setSpacing(2)
        self.prev_btn = self._make_button('skip_previous', 'Previous')
        self.play_btn = self._make_button('play_arrow', 'Play / Pause (p)')
        self.next_btn = self._make_button('skip_next', 'Next')
        self.lyrics_btn = self._make_button('lyrics', 'Toggle lyrics (5)')
        self.exit_btn = self._make_button(None, 'Back to full window (m)',
                                          glyph='⤢')
        self.exit_btn.clicked.connect(self.exit_requested.emit)
        for btn in (self.prev_btn, self.play_btn, self.next_btn,
                    self.lyrics_btn, self.exit_btn):
            bar.addWidget(btn)
        self.controls.setLayout(bar)
        self.controls.hide()

        # Invisible edge/corner grips handle resizing (frameless window)
        self._grips = WindowGrips(self)

        # Auto-hide timer: restarted on every mouse move while this window
        # is the active one; firing hides the controls + art nav arrows
        # even though the cursor never left
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(self.IDLE_HIDE_MS)
        self._idle_timer.timeout.connect(self._hide_hover_controls)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        player.art_changed.connect(self.art.set_source)
        player.play_state_changed.connect(self.set_playing)
        player.register_art_label(self.art)

    # ── Buttons ─────────────────────────────────────────────────────

    def _make_button(self, icon_name, tooltip, glyph=None):
        btn = QToolButton(self.controls)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setFixedSize(26, 26)
        if icon_name:
            btn.setIcon(QIcon(_render_svg(icon_name, 'white', 20)))
            btn.setIconSize(QSize(20, 20))
        elif glyph:
            btn.setText(glyph)
        return btn

    def set_playing(self, playing):
        name = 'pause' if playing else 'play_arrow'
        self.play_btn.setIcon(QIcon(_render_svg(name, 'white', 20)))

    # ── Theme ───────────────────────────────────────────────────────

    def set_theme(self, t):
        """Mini mode is its own top-level window, so the main window's
        stylesheet doesn't reach it — style the shell directly."""
        self.setStyleSheet(f"""
            #mini-view {{
                background-color: {t['bg']};
                border: 1px solid {t['hairline']};
            }}
            #mini-lyrics-column {{
                background-color: {t['bg']};
            }}
        """)

    # ── Lyrics column ───────────────────────────────────────────────

    def set_lyrics_visible(self, on):
        """Show/hide the lyrics column; the window widens beside the square
        art rather than stealing width from it."""
        self.lyrics_on = on
        self.lyrics_column.setVisible(on)
        side = self.height()
        self._resizing_self = True
        if on:
            self.art.setFixedWidth(side - 2)
            self.resize(side + max(220, side // 2), side)
        else:
            self.art.setMinimumWidth(120)
            self.art.setMaximumWidth(16777215)
            self.resize(side, side)
        self._resizing_self = False
        self._position_controls()

    # ── Geometry: keep it square (art-only) / art column square ─────

    def restore_geometry(self, geometry):
        """Like restoreGeometry(), but suppresses the square-follow logic
        below — a restored geometry is trusted as-is, never reinterpreted
        by picking whichever edge moved most."""
        self._resizing_self = True
        self.restoreGeometry(geometry)
        self._resizing_self = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._grips.relayout()
        if self.lyrics_on:
            # Art column pinned square; the lyrics column takes the rest
            self.art.setFixedWidth(self.height() - 2)
        elif not self._resizing_self and self.width() != self.height():
            # Square window: follow whichever edge the user is dragging
            old = event.oldSize()
            if old.isValid() and abs(self.width() - old.width()) < \
                    abs(self.height() - old.height()):
                side = self.height()
            else:
                side = self.width()
            self._resizing_self = True
            self.resize(side, side)
            self._resizing_self = False
        self._position_controls()

    def _position_controls(self):
        hint = self.controls.sizeHint()
        x = self.art.x() + (self.art.width() - hint.width()) // 2
        y = self.height() - hint.height() - 12
        self.controls.setGeometry(x, y, hint.width(), hint.height())

    # ── Hover / focus behavior for the controls ─────────────────────
    #
    # Two independent paths hide the controls: an immediate one (cursor
    # actually left the window, or the window lost focus) and a delayed one
    # (no mouse motion for IDLE_HIDE_MS, even though the cursor is still
    # inside and the window is still active — like video-player controls).

    def _cursor_inside(self):
        return self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    def _show_hover_controls(self):
        self._position_controls()
        self.controls.show()
        self.controls.raise_()
        self.art._show_nav()  # no-op if the gallery has only one image
        self._idle_timer.start()

    def _hide_hover_controls(self):
        self._idle_timer.stop()
        self.controls.hide()
        self.art._hide_nav()

    def enterEvent(self, event):
        self._show_hover_controls()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._cursor_inside():
            self._hide_hover_controls()
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._idle_timer.stop()
        super().hideEvent(event)

    def event(self, event):
        # Hide the hover controls whenever the mini window loses focus
        if event.type() == QEvent.WindowDeactivate:
            self._hide_hover_controls()
        return super().event(event)

    # ── Input ───────────────────────────────────────────────────────

    def set_key_handlers(self, keymap):
        """Qt key -> callable, supplied by the app (reuses its shortcuts)."""
        self._keymap = keymap

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.exit_requested.emit()
            return
        handler = self._keymap.get(event.key())
        if handler:
            handler()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        """App-wide filter: drag/double-click on the art (obj is self.art),
        plus mouse-move detection for the idle-hide timer. Mouse-move never
        reaches this window's own event handlers when the cursor is over a
        child widget (the art label, a button) — Qt delivers it to that
        child, not the parent — so this has to watch every widget's events
        and check the cursor position itself."""
        if event.type() == QEvent.MouseMove and self.isVisible() \
                and self.isActiveWindow() and self._cursor_inside():
            self._show_hover_controls()
        if obj is self.art:
            if event.type() == QEvent.MouseButtonDblClick:
                self.exit_requested.emit()
                return True
            if (event.type() == QEvent.MouseButtonPress
                    and event.button() == Qt.LeftButton):
                handle = self.windowHandle()
                if handle is not None:
                    handle.startSystemMove()
                return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        # Closing the mini window returns to the full app, not quit —
        # the app hides this window first when it really is quitting
        if self.isVisible():
            event.ignore()
            self.exit_requested.emit()
        else:
            event.accept()
