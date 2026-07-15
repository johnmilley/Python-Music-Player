# overlay_controls — ControlPanel is THE playback control surface for all
# three modes: floating over album art (shown on hover, auto-hidden) in
# mini and max mode, and embedded inline, always visible, below the art in
# the normal-mode player column. Built once per host, configured via
# show_back (mini/max only) and show_side_toggles (off for the normal-mode
# instance, which has no side panes of its own to toggle — those live in
# the toolbar there) so every mode presents the same control surface.
#
# Mini/max mode float the panel over album art, so it needs a translucent
# dark scrim to stay readable (see _panel_qss) — accent-aware, hover
# backgrounds and active/checked icon colors pick up the app's accent,
# recolored for the scrim instead of the app's own bg/fg tokens (see
# theme.py's build_qss for the app-wide equivalent). The normal-mode
# instance is embedded below the art on the app's own background, not
# floating over unpredictable art, so it skips the scrim entirely
# (scrim=False) and just uses the app's own theme colors like any other
# toolbar control. Squared-off/boxy rather than
# pill-shaped — the only round element is the favourite heart, which is
# also always accent-colored (not just when favourited) so it reads as a
# distinct, always-reachable action rather than a state toggle like
# tracklist/lyrics.

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QToolButton, QSizePolicy, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QIcon, QColor

from player import _render_svg
from progress_bar import ClickableProgressBar
import theme as theme_mod

# Hover controls fade after this long without mouse motion (like a video
# player), even while the cursor is still over the window.
IDLE_HIDE_MS = 2500

# Squared-off corner radii — deliberately small/zero, not the pill shapes
# used elsewhere. Only the heart button (HEART_RADIUS) stays round.
PANEL_RADIUS = 2
BUTTON_RADIUS = 3
HEART_RADIUS = 13

# Scrim opacity: user-adjustable (App.set_overlay_opacity, 0-100 "glassy" ..
# "solid"), but floored so the panel never gets so transparent that white
# text stops reading against busy album art. The range is deliberately
# wide — at the old 90..220 floor the low end was already fairly dark and
# the slider looked like it did nothing.
DEFAULT_OPACITY = 60
MIN_SCRIM_ALPHA = 45
MAX_SCRIM_ALPHA = 235


def scrim_alpha(opacity):
    opacity = DEFAULT_OPACITY if opacity is None else max(0, min(100, opacity))
    return round(MIN_SCRIM_ALPHA + (MAX_SCRIM_ALPHA - MIN_SCRIM_ALPHA) * opacity / 100)


def _apply_boxy_shadow(widget):
    """A subtle drop shadow so the squared-off overlay reads as a slightly
    raised box rather than a flat cutout. QSS has no box-shadow property,
    so this has to be a QGraphicsEffect."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(16)
    shadow.setOffset(0, 3)
    shadow.setColor(QColor(0, 0, 0, 130))
    widget.setGraphicsEffect(shadow)


def _icon_for(name, color, size):
    return QIcon(_render_svg(name, color, size))


def _heart_icon(favorited, accent, size):
    """The heart is always accent-colored (hollow outline or filled),
    never the dim/accent-when-active pattern the other toggles use — it's
    a standalone action, not a panel-state indicator."""
    return _icon_for('heart' if favorited else 'heart_outline', accent, size)


def _toggle_icon(name, active, accent, dim, size):
    return _icon_for(name, accent if active else dim, size)


def _repeat_icon(mode, accent, dim, size):
    name = 'repeat_one' if mode == 'one' else 'repeat'
    return _icon_for(name, dim if mode == 'off' else accent, size)


def _shared_button_qss(selector_prefix, accent, hover_alpha=90):
    accent_hover = theme_mod._alpha(accent, hover_alpha)
    return f"""
        {selector_prefix} QToolButton {{
            background: transparent;
            border: none;
            border-radius: {BUTTON_RADIUS}px;
        }}
        {selector_prefix} QToolButton:hover {{ background-color: {accent_hover}; }}
        {selector_prefix} #heart-btn {{ border-radius: {HEART_RADIUS}px; }}
    """


def _panel_qss(t, fs, opacity, scrim=True):
    accent = t.get('accent', theme_mod.DEFAULT_ACCENT)
    if not scrim:
        # Embedded (normal-mode) form: no background box, no scrim —
        # it sits on the app's own elevated background, so it just uses
        # the app's own theme colors like any other toolbar control.
        fg = t.get('fg', 'white')
        fg_dim = t.get('fg_dim', 'rgba(255, 255, 255, 180)')
        panel_bg = 'transparent'
        track_bg = t.get('hover', 'rgba(255, 255, 255, 40)')
        hover_alpha = 22
    else:
        alpha = scrim_alpha(opacity)
        fg = 'white'
        fg_dim = 'rgba(255, 255, 255, 180)'
        track_bg = 'rgba(255, 255, 255, 40)'
        panel_bg = f'rgba(20, 20, 20, {alpha})'
        hover_alpha = 90
    return f"""
        #control-panel {{
            background-color: {panel_bg};
            border-radius: {PANEL_RADIUS if scrim else 0}px;
        }}
        #control-panel QLabel {{
            color: {fg};
            background: transparent;
            font-family: {theme_mod.FONT};
        }}
        #panel-title {{
            font-size: {fs}pt;
            font-weight: bold;
        }}
        #panel-time {{
            font-size: {max(fs - 2, 7)}pt;
            color: {fg_dim};
        }}
        {_shared_button_qss('#control-panel', accent, hover_alpha)}
        #control-panel QProgressBar {{
            background: {track_bg};
            border: none;
            border-radius: 0px;
        }}
        #control-panel QProgressBar::chunk {{
            background-color: {accent};
            border-radius: 0px;
        }}
    """


class ControlPanel(QWidget):
    """Title+heart row, progress+time row, transport+toggles(+back) row.

    Content only — geometry (position, width) is set by the host view
    (MaxView/MiniView position_control_panel + their own hover/idle-hide
    timers); this widget doesn't show/hide or position itself.
    """
    prev_clicked = pyqtSignal()
    play_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    tracklist_clicked = pyqtSignal()
    lyrics_clicked = pyqtSignal()
    heart_clicked = pyqtSignal()
    back_clicked = pyqtSignal()
    shuffle_clicked = pyqtSignal()
    repeat_clicked = pyqtSignal()

    def __init__(self, parent=None, show_back=False, show_side_toggles=True, scrim=True):
        super().__init__(parent)
        self.setObjectName('control-panel')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._scrim = scrim
        self._accent = theme_mod.DEFAULT_ACCENT
        self._opacity = DEFAULT_OPACITY
        self._icon_fg = 'white'
        self._title_text = ''
        self._playing = False
        self._favorited = False
        self._tracklist_on = False
        self._lyrics_on = False
        self._shuffle_on = False
        self._repeat_mode = 'off'
        self._show_side_toggles = show_side_toggles

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 8)
        outer.setSpacing(4)

        # Row 1: title (elided to fit) + favourite toggle
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.title_label = QLabel('')
        self.title_label.setObjectName('panel-title')
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row1.addWidget(self.title_label, stretch=1)
        self.heart_btn = self._make_button('heart_outline', 'Favourite (Shift+H)',
                                           size=26, icon_size=17, heart=True)
        self.heart_btn.clicked.connect(self.heart_clicked.emit)
        row1.addWidget(self.heart_btn)
        outer.addLayout(row1)

        # Row 2: elapsed time, progress bar, total time
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.pos_label = QLabel('0:00')
        self.pos_label.setObjectName('panel-time')
        self.len_label = QLabel('0:00')
        self.len_label.setObjectName('panel-time')
        self.progress_bar = ClickableProgressBar(self)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        row2.addWidget(self.pos_label)
        row2.addWidget(self.progress_bar, stretch=1)
        row2.addWidget(self.len_label)
        outer.addLayout(row2)

        # Row 3: [tracklist toggle] | shuffle | transport | repeat | [lyrics toggle] | [back]
        # Tracklist/lyrics toggles are omitted entirely (not just hidden)
        # when show_side_toggles=False — main mode's always-visible panel
        # has no side panes of its own to toggle (those live in the
        # toolbar there), so it shouldn't reserve space for buttons that
        # do nothing.
        row3 = QHBoxLayout()
        row3.setSpacing(2)
        self.tracklist_btn = None
        if show_side_toggles:
            self.tracklist_btn = self._make_button('tracklist', 'Toggle tracklist (4)')
            self.tracklist_btn.clicked.connect(self.tracklist_clicked.emit)
            row3.addWidget(self.tracklist_btn)
        row3.addStretch(1)
        self.shuffle_btn = self._make_button('shuffle', 'Toggle shuffle (s)')
        self.shuffle_btn.clicked.connect(self.shuffle_clicked.emit)
        row3.addWidget(self.shuffle_btn)
        self.prev_btn = self._make_button('skip_previous', 'Previous')
        self.prev_btn.clicked.connect(self.prev_clicked.emit)
        self.play_btn = self._make_button('play_arrow', 'Play / Pause (p)', size=36, icon_size=22)
        self.play_btn.clicked.connect(self.play_clicked.emit)
        self.next_btn = self._make_button('skip_next', 'Next')
        self.next_btn.clicked.connect(self.next_clicked.emit)
        row3.addWidget(self.prev_btn)
        row3.addWidget(self.play_btn)
        row3.addWidget(self.next_btn)
        self.repeat_btn = self._make_button('repeat', 'Toggle repeat')
        self.repeat_btn.clicked.connect(self.repeat_clicked.emit)
        row3.addWidget(self.repeat_btn)
        row3.addStretch(1)
        self.lyrics_btn = None
        if show_side_toggles:
            self.lyrics_btn = self._make_button('lyrics', 'Toggle lyrics (5)')
            self.lyrics_btn.clicked.connect(self.lyrics_clicked.emit)
            row3.addWidget(self.lyrics_btn)
        self.back_btn = None
        if show_back:
            self.back_btn = self._make_button('close', 'Back')
            self.back_btn.clicked.connect(self.back_clicked.emit)
            row3.addWidget(self.back_btn)
        outer.addLayout(row3)

        self.set_theme(theme_mod.LIGHT, theme_mod.DEFAULT_SIZE)
        if self._scrim:
            _apply_boxy_shadow(self)
        self.hide()

    def _make_button(self, icon_name, tooltip, size=30, icon_size=20, heart=False):
        btn = QToolButton(self)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setFixedSize(size, size)
        btn.setIconSize(QSize(icon_size, icon_size))
        btn._icon_name = icon_name
        btn._icon_size = icon_size
        if heart:
            btn.setObjectName('heart-btn')
        return btn

    # ── Theme ──────────────────────────────────────────────────────

    def set_theme(self, t, fs):
        """Accent + font-size aware restyle — called whenever the app's
        theme/accent/text-size changes, same as everything else. Opacity
        is remembered across calls that omit it (t may be a partial dict).
        The embedded (scrim=False) form ignores opacity entirely — it has
        no scrim to darken — and just follows the app's own fg/fg_dim
        tokens."""
        self._accent = t.get('accent', theme_mod.DEFAULT_ACCENT)
        if self._scrim:
            if 'overlay_opacity' in t:
                self._opacity = t['overlay_opacity']
            self._icon_fg = 'white'
        else:
            self._icon_fg = t.get('fg', 'white')
        self.setStyleSheet(_panel_qss(
            t, fs or theme_mod.DEFAULT_SIZE, self._opacity, self._scrim))
        self._refresh_icons()
        self._apply_title_elide()

    def _refresh_icons(self):
        fg = self._icon_fg
        if self.tracklist_btn:
            self.tracklist_btn.setIcon(_toggle_icon(
                'tracklist', self._tracklist_on, self._accent, fg, self.tracklist_btn._icon_size))
        if self.lyrics_btn:
            self.lyrics_btn.setIcon(_toggle_icon(
                'lyrics', self._lyrics_on, self._accent, fg, self.lyrics_btn._icon_size))
        self.shuffle_btn.setIcon(_toggle_icon(
            'shuffle', self._shuffle_on, self._accent, fg, self.shuffle_btn._icon_size))
        self.repeat_btn.setIcon(_repeat_icon(
            self._repeat_mode, self._accent, fg, self.repeat_btn._icon_size))
        self.prev_btn.setIcon(_icon_for('skip_previous', fg, self.prev_btn._icon_size))
        self.next_btn.setIcon(_icon_for('skip_next', fg, self.next_btn._icon_size))
        self.play_btn.setIcon(_icon_for(
            'pause' if self._playing else 'play_arrow', fg, self.play_btn._icon_size))
        self.heart_btn.setIcon(_heart_icon(self._favorited, self._accent, self.heart_btn._icon_size))
        if self.back_btn:
            self.back_btn.setIcon(_icon_for('close', fg, self.back_btn._icon_size))

    # ── State (called by the host view) ──────────────────────────────

    def set_title(self, text):
        self._title_text = text or ''
        self._apply_title_elide()

    def _apply_title_elide(self):
        avail = self.title_label.width()
        if avail <= 0:
            self.title_label.setText(self._title_text)
        else:
            metrics = self.title_label.fontMetrics()
            self.title_label.setText(
                metrics.elidedText(self._title_text, Qt.ElideRight, avail))
        self.title_label.setToolTip(self._title_text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_title_elide()

    def set_playing(self, playing):
        self._playing = playing
        self.play_btn.setIcon(_icon_for(
            'pause' if playing else 'play_arrow', self._icon_fg, self.play_btn._icon_size))

    def set_favorited(self, on):
        self._favorited = on
        self.heart_btn.setIcon(_heart_icon(on, self._accent, self.heart_btn._icon_size))

    def set_heart_visible(self, visible):
        self.heart_btn.setVisible(visible)

    def set_toggle_states(self, tracklist_on, lyrics_on):
        self._tracklist_on = tracklist_on
        self._lyrics_on = lyrics_on
        if self.tracklist_btn:
            self.tracklist_btn.setIcon(_toggle_icon(
                'tracklist', tracklist_on, self._accent, self._icon_fg, self.tracklist_btn._icon_size))
        if self.lyrics_btn:
            self.lyrics_btn.setIcon(_toggle_icon(
                'lyrics', lyrics_on, self._accent, self._icon_fg, self.lyrics_btn._icon_size))

    def set_shuffle_state(self, on):
        self._shuffle_on = on
        self.shuffle_btn.setIcon(_toggle_icon(
            'shuffle', on, self._accent, self._icon_fg, self.shuffle_btn._icon_size))

    def set_repeat_state(self, mode):
        self._repeat_mode = mode
        self.repeat_btn.setIcon(_repeat_icon(
            mode, self._accent, self._icon_fg, self.repeat_btn._icon_size))


def position_control_panel(panel, art_x, art_y, art_w, art_h):
    """Center the panel along the art's bottom edge, capped to a sane width
    (mirrors player.py's own embedded panel's 420px cap) so the progress
    bar/title don't stretch absurdly wide over large art."""
    w = min(art_w - 32, 420)
    if w <= 0:
        return
    panel.setFixedWidth(w)
    h = panel.sizeHint().height()
    x = art_x + (art_w - w) // 2
    y = art_y + art_h - h - 16
    panel.setGeometry(x, y, w, h)
