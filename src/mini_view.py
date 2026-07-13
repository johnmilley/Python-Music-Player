# MiniView — compact "mini mode": a small, always-on-top square window of
# just the album art, resizable from its invisible edge grips (the window
# stays square). The unified ControlPanel (title, favourite, progress/time,
# transport, tracklist/lyrics toggles, back) floats over the art and only
# appears on hover — it hides immediately on leave or whenever the window
# loses focus, and also auto-hides after a few seconds of no mouse movement
# even while still hovering (a QApplication-wide MouseMove filter, since
# child widgets — the art label, the panel's buttons — swallow mouse-move
# before it would ever reach this window's own event handlers).
# The album's art gallery scrolls here too (AlbumArtLabel's hover arrows).
#
# Lyrics can be toggled on alongside the art: like MaxView, this borrows
# the app's single LyricsWidget by reparenting it into lyrics_slot — the
# app attaches/detaches it (see App._toggle_mini_lyrics).
#
# Key handling is a map of Qt keys -> callables supplied by the app
# (set_key_handlers), so mini mode reuses the same shortcut behaviors
# (play/pause, seek, volume) without duplicating any logic.

from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QApplication, QLineEdit)
from PyQt5.QtCore import Qt, QEvent, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor

from art_label import AlbumArtLabel
from window_chrome import WindowGrips
import overlay_controls
import theme as theme_mod


class MiniView(QWidget):
    exit_requested = pyqtSignal()

    IDLE_HIDE_MS = overlay_controls.IDLE_HIDE_MS

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
        # Qt.Key -> callable maps that only fire with the modifier held
        # (Shift+H favourite, Shift+D dark mode, Ctrl+=/- text size) —
        # kept apart from _keymap, which doesn't check modifiers
        self._shift_keymap = {}
        self._ctrl_keymap = {}
        self._resizing_self = False  # guard for programmatic resizes
        self.lyrics_on = False
        self.tracklist_on = False

        layout = QHBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)  # keep the hairline border visible
        layout.setSpacing(0)

        # Tracklist pane — LEFT of the art, album name at its top.
        self.tracklist_wrap = QWidget()
        self.tracklist_wrap.setObjectName('mini-tracklist-wrap')
        self.tracklist_wrap.setMinimumWidth(160)
        tl_lay = QVBoxLayout(self.tracklist_wrap)
        tl_lay.setContentsMargins(8, 8, 8, 8)
        tl_lay.setSpacing(6)
        self.tracklist_title = QLabel()
        self.tracklist_title.setObjectName('mini-tracklist-title')
        self.tracklist_title.setWordWrap(True)
        tl_lay.addWidget(self.tracklist_title)
        self.tracklist_slot = QVBoxLayout()
        self.tracklist_slot.setContentsMargins(0, 0, 0, 0)
        tl_lay.addLayout(self.tracklist_slot, stretch=1)
        self.tracklist_wrap.hide()
        layout.addWidget(self.tracklist_wrap, stretch=1)

        self.art = AlbumArtLabel(square=True)
        self.art.setMinimumSize(120, 120)
        self.art.setCursor(Qt.ArrowCursor)
        self.art.installEventFilter(self)  # drag-to-move / double-click exit
        layout.addWidget(self.art)

        # Lyrics pane — RIGHT of the art, track name at its top. The app's
        # AlbumView / LyricsWidget are reparented into the two *_slot
        # layouts while toggled on (same borrowing pattern as MaxView); the
        # title labels are permanent children of the wraps, not part of the
        # borrowed widgets. The hover ControlPanel below has its own title
        # too — both are kept, by design.
        self.lyrics_wrap = QWidget()
        self.lyrics_wrap.setObjectName('mini-lyrics-wrap')
        self.lyrics_wrap.setMinimumWidth(160)
        ly_lay = QVBoxLayout(self.lyrics_wrap)
        ly_lay.setContentsMargins(8, 8, 8, 8)
        ly_lay.setSpacing(6)
        self.lyrics_title = QLabel()
        self.lyrics_title.setObjectName('mini-lyrics-title')
        self.lyrics_title.setWordWrap(True)
        ly_lay.addWidget(self.lyrics_title)
        self.lyrics_slot = QVBoxLayout()
        self.lyrics_slot.setContentsMargins(0, 0, 0, 0)
        ly_lay.addLayout(self.lyrics_slot, stretch=1)
        self.lyrics_wrap.hide()
        layout.addWidget(self.lyrics_wrap, stretch=1)

        self.setLayout(layout)

        # Hover control panel: same widget max mode uses, floating over the
        # art's bottom edge.
        self.panel = overlay_controls.ControlPanel(self, show_back=True)
        self.panel.back_btn.setToolTip('Back to full window (m)')
        self.panel.back_clicked.connect(self.exit_requested.emit)

        # Invisible edge/corner grips handle resizing (frameless window)
        self._grips = WindowGrips(self)

        # Auto-hide timer: restarted on every mouse move while this window
        # is the active one; firing hides the controls + art nav arrows
        # even though the cursor never left
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(self.IDLE_HIDE_MS)
        self._idle_timer.timeout.connect(self._hide_hover_controls)
        # The app-wide filter (mouse-move + key routing for borrowed
        # widgets) is installed only while the mini window is showing —
        # see showEvent/hideEvent. A permanently-installed app-wide filter
        # would tax every event in the whole application even while mini
        # mode is closed.

        player.art_changed.connect(self.art.set_source)
        player.play_state_changed.connect(self.set_playing)
        player.track_changed.connect(self._on_track_changed)
        player.register_art_label(self.art)
        # Progress bar / time labels mirror the player column's own
        player.register_progress_display(
            self.panel.progress_bar, self.panel.pos_label, self.panel.len_label)

    def _on_track_changed(self, track):
        title = str(getattr(track, 'title', '') or '')
        self.panel.set_title(title)
        self.lyrics_title.setText(title)
        self.tracklist_title.setText(str(getattr(track, 'album', '') or ''))

    def set_playing(self, playing):
        self.panel.set_playing(playing)

    def set_favorited(self, on):
        self.panel.set_favorited(on)

    def set_heart_visible(self, visible):
        self.panel.set_heart_visible(visible)

    # ── Theme ───────────────────────────────────────────────────────

    def set_theme(self, t, fs=None):
        """Mini mode is its own top-level window, so the main window's
        stylesheet doesn't reach it — style the shell directly."""
        fs = fs or theme_mod.DEFAULT_SIZE
        self.setStyleSheet(f"""
            #mini-view {{
                background-color: {t['bg']};
                border: 1px solid {t['hairline']};
            }}
            #mini-tracklist-wrap, #mini-lyrics-wrap {{
                background-color: {t['bg']};
            }}
            #mini-tracklist-title, #mini-lyrics-title {{
                color: {t['fg']};
                background: transparent;
                font-family: {theme_mod.FONT};
                font-weight: bold;
                font-size: {fs + 1}pt;
            }}
        """)
        self.panel.set_theme(t, fs)

    # ── Side column (tracklist / lyrics) ────────────────────────────

    def _any_side_visible(self):
        return self.lyrics_on or self.tracklist_on

    def set_lyrics_visible(self, on):
        """Show/hide the lyrics pane in the side column."""
        self.lyrics_on = on
        self.lyrics_wrap.setVisible(on)
        self._apply_side_layout()
        self.panel.set_toggle_states(self.tracklist_on, self.lyrics_on)

    def set_tracklist_visible(self, on):
        """Show/hide the tracklist pane in the side column."""
        self.tracklist_on = on
        self.tracklist_wrap.setVisible(on)
        self._apply_side_layout()
        self.panel.set_toggle_states(self.tracklist_on, self.lyrics_on)

    def _apply_side_layout(self):
        """Resize the window for the tracklist (left) / lyrics (right)
        panes' current visibility — the window widens on whichever side(s)
        are open rather than stealing width from the square art. Shared by
        both since either, neither, or both can be open at once."""
        side = self.height()
        self._resizing_self = True
        if self._any_side_visible():
            self.art.setFixedWidth(side - 2)
            pane_w = max(180, side // 2)
            extra = (pane_w if self.tracklist_on else 0) + (pane_w if self.lyrics_on else 0)
            self.resize(side + extra, side)
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
        if self._any_side_visible():
            # Art column pinned square; the side column takes the rest
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
        overlay_controls.position_control_panel(
            self.panel, self.art.x(), self.art.y(),
            self.art.width(), self.art.height())

    # ── Hover / focus behavior for the controls ─────────────────────
    #
    # Two independent paths hide the controls: an immediate one (cursor
    # actually left the window, or the window lost focus) and a delayed one
    # (no mouse motion for IDLE_HIDE_MS, even though the cursor is still
    # inside and the window is still active — like video-player controls).

    def _cursor_inside(self):
        return self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    def _show_hover_controls(self):
        # Runs on every app-wide MouseMove while the mini window is up —
        # only do the layout/stacking work on the hidden -> shown transition
        if not self.panel.isVisible():
            self._position_controls()
            self.panel.show()
            self.panel.raise_()
            self.art._show_nav()  # no-op if the gallery has only one image
        self._idle_timer.start()

    def _hide_hover_controls(self):
        self._idle_timer.stop()
        self.panel.hide()
        self.art._hide_nav()

    def enterEvent(self, event):
        self._show_hover_controls()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._cursor_inside():
            self._hide_hover_controls()
        super().leaveEvent(event)

    def showEvent(self, event):
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        super().showEvent(event)

    def hideEvent(self, event):
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
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

    def set_shift_key_handlers(self, keymap):
        """Qt key -> callable, only dispatched when Shift is held (e.g.
        Shift+H favourite, Shift+D dark mode)."""
        self._shift_keymap = keymap

    def set_ctrl_key_handlers(self, keymap):
        """Qt key -> callable, only dispatched when Ctrl is held (e.g.
        Ctrl+= / Ctrl+- text size)."""
        self._ctrl_keymap = keymap

    def _modified_handler(self, event):
        if event.modifiers() & Qt.ControlModifier:
            return self._ctrl_keymap.get(event.key())
        if event.modifiers() & Qt.ShiftModifier:
            return self._shift_keymap.get(event.key())
        return None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.exit_requested.emit()
            return
        handler = self._modified_handler(event)
        if handler:
            handler()
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
        # Shortcut routing: when a borrowed child widget (the tracklist,
        # the lyrics pane) has keyboard focus, key presses go to it — and
        # VimListWidget swallows printable keys — so 'm'/'p'/'4'/'5' would
        # never reach this window's own keyPressEvent. Intercept keymap
        # keys here, before delivery, for anything focused inside mini mode.
        if (event.type() == QEvent.KeyPress and self.isVisible()
                and isinstance(obj, QWidget)
                and (obj is self or self.isAncestorOf(obj))
                and not isinstance(obj, QLineEdit)):
            handler = self._modified_handler(event)
            if handler:
                handler()
                return True
            handler = self._keymap.get(event.key())
            if handler:
                handler()
                return True
            if event.key() == Qt.Key_Escape:
                # Let an open search bar consume Escape; otherwise exit
                sb = getattr(obj, '_search_bar', None)
                if not (sb and sb.isVisible()):
                    self.exit_requested.emit()
                    return True
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
