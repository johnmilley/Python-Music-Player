# overlay_controls — the unified playback control panel shown over album
# art in mini mode and max mode (ControlPanel), plus the lighter 3-icon
# hover row shown over album art in the normal-mode player column
# (ArtHoverRow). Built once, reused identically by their respective host
# views so each mode presents the same control surface.
#
# Styled as a translucent dark scrim over album art (readable on any cover,
# light or dark) but accent-aware: hover backgrounds and active/checked icon
# colors pick up the app's accent, recolored for a dark background instead
# of the app's own bg/fg tokens (see theme.py's build_qss for the app-wide
# equivalent). Squared-off/boxy rather than pill-shaped — the only round
# element is the favourite heart, which is also always accent-colored
# (not just when favourited) so it reads as a distinct, always-reachable
# action rather than a state toggle like tracklist/lyrics.

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


def _shared_button_qss(selector_prefix, accent):
    accent_hover = theme_mod._alpha(accent, 90)
    return f"""
        {selector_prefix} QToolButton {{
            background: transparent;
            border: none;
            border-radius: {BUTTON_RADIUS}px;
        }}
        {selector_prefix} QToolButton:hover {{ background-color: {accent_hover}; }}
        {selector_prefix} #heart-btn {{ border-radius: {HEART_RADIUS}px; }}
    """


def _panel_qss(t, fs, opacity):
    accent = t.get('accent', theme_mod.DEFAULT_ACCENT)
    alpha = scrim_alpha(opacity)
    return f"""
        #control-panel {{
            background-color: rgba(20, 20, 20, {alpha});
            border-radius: {PANEL_RADIUS}px;
        }}
        #control-panel QLabel {{
            color: white;
            background: transparent;
            font-family: {theme_mod.FONT};
        }}
        #panel-title {{
            font-size: {fs}pt;
            font-weight: bold;
        }}
        #panel-time {{
            font-size: {max(fs - 2, 7)}pt;
            color: rgba(255, 255, 255, 180);
        }}
        {_shared_button_qss('#control-panel', accent)}
        #control-panel QProgressBar {{
            background: rgba(255, 255, 255, 40);
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

    def __init__(self, parent=None, show_back=False):
        super().__init__(parent)
        self.setObjectName('control-panel')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._accent = theme_mod.DEFAULT_ACCENT
        self._opacity = DEFAULT_OPACITY
        self._title_text = ''
        self._playing = False
        self._favorited = False
        self._tracklist_on = False
        self._lyrics_on = False

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

        # Row 3: tracklist toggle | transport | lyrics toggle | back
        row3 = QHBoxLayout()
        row3.setSpacing(2)
        self.tracklist_btn = self._make_button('tracklist', 'Toggle tracklist (4)')
        self.tracklist_btn.clicked.connect(self.tracklist_clicked.emit)
        self.prev_btn = self._make_button('skip_previous', 'Previous')
        self.prev_btn.clicked.connect(self.prev_clicked.emit)
        self.play_btn = self._make_button('play_arrow', 'Play / Pause (p)', size=36, icon_size=22)
        self.play_btn.clicked.connect(self.play_clicked.emit)
        self.next_btn = self._make_button('skip_next', 'Next')
        self.next_btn.clicked.connect(self.next_clicked.emit)
        self.lyrics_btn = self._make_button('lyrics', 'Toggle lyrics (5)')
        self.lyrics_btn.clicked.connect(self.lyrics_clicked.emit)
        row3.addWidget(self.tracklist_btn)
        row3.addStretch(1)
        row3.addWidget(self.prev_btn)
        row3.addWidget(self.play_btn)
        row3.addWidget(self.next_btn)
        row3.addStretch(1)
        row3.addWidget(self.lyrics_btn)
        self.back_btn = None
        if show_back:
            self.back_btn = self._make_button('close', 'Back')
            self.back_btn.clicked.connect(self.back_clicked.emit)
            row3.addWidget(self.back_btn)
        outer.addLayout(row3)

        self.set_theme(theme_mod.LIGHT, theme_mod.DEFAULT_SIZE)
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
        theme/accent/text-size changes, same as everything else. Opacity is
        remembered across calls that omit it (t may be a partial dict)."""
        self._accent = t.get('accent', theme_mod.DEFAULT_ACCENT)
        if 'overlay_opacity' in t:
            self._opacity = t['overlay_opacity']
        self.setStyleSheet(_panel_qss(t, fs or theme_mod.DEFAULT_SIZE, self._opacity))
        self._refresh_icons()
        self._apply_title_elide()

    def _refresh_icons(self):
        self.tracklist_btn.setIcon(_toggle_icon(
            'tracklist', self._tracklist_on, self._accent, 'white', self.tracklist_btn._icon_size))
        self.lyrics_btn.setIcon(_toggle_icon(
            'lyrics', self._lyrics_on, self._accent, 'white', self.lyrics_btn._icon_size))
        self.prev_btn.setIcon(_icon_for('skip_previous', 'white', self.prev_btn._icon_size))
        self.next_btn.setIcon(_icon_for('skip_next', 'white', self.next_btn._icon_size))
        self.play_btn.setIcon(_icon_for(
            'pause' if self._playing else 'play_arrow', 'white', self.play_btn._icon_size))
        self.heart_btn.setIcon(_heart_icon(self._favorited, self._accent, self.heart_btn._icon_size))
        if self.back_btn:
            self.back_btn.setIcon(_icon_for('close', 'white', self.back_btn._icon_size))

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
            'pause' if playing else 'play_arrow', 'white', self.play_btn._icon_size))

    def set_favorited(self, on):
        self._favorited = on
        self.heart_btn.setIcon(_heart_icon(on, self._accent, self.heart_btn._icon_size))

    def set_heart_visible(self, visible):
        self.heart_btn.setVisible(visible)

    def set_toggle_states(self, tracklist_on, lyrics_on):
        self._tracklist_on = tracklist_on
        self._lyrics_on = lyrics_on
        self.tracklist_btn.setIcon(_toggle_icon(
            'tracklist', tracklist_on, self._accent, 'white', self.tracklist_btn._icon_size))
        self.lyrics_btn.setIcon(_toggle_icon(
            'lyrics', lyrics_on, self._accent, 'white', self.lyrics_btn._icon_size))


def position_control_panel(panel, art_x, art_y, art_w, art_h):
    """Center the panel along the art's bottom edge, capped to a sane width
    (mirrors player.py's own controls_container 420px cap) so the progress
    bar/title don't stretch absurdly wide over large art."""
    w = min(art_w - 32, 420)
    if w <= 0:
        return
    panel.setFixedWidth(w)
    h = panel.sizeHint().height()
    x = art_x + (art_w - w) // 2
    y = art_y + art_h - h - 16
    panel.setGeometry(x, y, w, h)


class HeartOverlay(QWidget):
    """One big accent-colored heart shown over album art on hover in the
    normal-mode player column — favourite/unfavourite the playing track.
    No scrim box, no other buttons (tracklist/lyrics toggles live in the
    toolbar); just the heart with the shared drop shadow so it reads over
    any artwork."""
    heart_clicked = pyqtSignal()

    ICON_SIZE = 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('heart-overlay')
        self._accent = theme_mod.DEFAULT_ACCENT
        self._favorited = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.heart_btn = QToolButton(self)
        self.heart_btn.setObjectName('heart-btn')
        self.heart_btn.setToolTip('Favourite (Shift+H)')
        self.heart_btn.setCursor(Qt.PointingHandCursor)
        self.heart_btn.setFocusPolicy(Qt.NoFocus)
        self.heart_btn.setFixedSize(self.ICON_SIZE + 16, self.ICON_SIZE + 16)
        self.heart_btn.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        self.heart_btn.clicked.connect(self.heart_clicked.emit)
        lay.addWidget(self.heart_btn)

        self.set_theme(theme_mod.LIGHT)
        _apply_boxy_shadow(self)
        self.hide()

    def set_theme(self, t):
        self._accent = t.get('accent', theme_mod.DEFAULT_ACCENT)
        accent_hover = theme_mod._alpha(self._accent, 60)
        self.setStyleSheet(f"""
            #heart-overlay {{ background: transparent; }}
            #heart-btn {{
                background: transparent;
                border: none;
                border-radius: {(self.ICON_SIZE + 16) // 2}px;
            }}
            #heart-btn:hover {{ background-color: {accent_hover}; }}
        """)
        self.heart_btn.setIcon(
            _heart_icon(self._favorited, self._accent, self.ICON_SIZE))

    def set_favorited(self, on):
        self._favorited = on
        self.heart_btn.setIcon(_heart_icon(on, self._accent, self.ICON_SIZE))

    def set_heart_visible(self, visible):
        self.heart_btn.setVisible(visible)
