# overlay_controls — ControlPanel is THE playback control surface: it
# floats over the album art (shown on hover, auto-hidden when idle) on the
# main window's stage and in max mode. Built once per host, configured via
# show_back (max mode: exit) and show_more (stage: the ⋯ menu).
#
# Floating over unpredictable art, it sits on a translucent dark scrim
# (see _panel_qss) with white text/icons; hover backgrounds pick up the
# app's accent. Squared-off/boxy rather than pill-shaped — the only round
# element is the favourite heart, which is also always accent-colored (not
# just when favourited) so it reads as a distinct, always-reachable action
# rather than a state toggle like tracklist/lyrics.

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QToolButton, QSizePolicy, QGraphicsDropShadowEffect, QFrame, QSlider)
from PyQt5.QtCore import Qt, QSize, QPoint, QTimer, pyqtSignal
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

# Toggles on the scrim are white when on, grey when off — NOT accent-when-
# on like the app's own toolbar-style controls: the accent is usually
# extracted from the very album art the scrim floats over, so an accent
# icon on a translucent scrim over that art all but disappears.
SCRIM_TOGGLE_OFF = '#8c8c8c'
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


def volume_icon_name(volume, muted):
    """volume 0..1 -> the speaker icon for it."""
    if muted or volume <= 0:
        return 'volume_off'
    return 'volume_down' if volume < 0.5 else 'volume_up'


def volume_text(volume, muted):
    return 'Muted' if muted else f'Volume {round(volume * 100)}%'


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


def _panel_qss(t, fs, opacity):
    accent = t.get('accent', theme_mod.DEFAULT_ACCENT)
    alpha = scrim_alpha(opacity)
    fg = 'white'
    fg_dim = 'rgba(255, 255, 255, 180)'
    track_bg = 'rgba(255, 255, 255, 40)'
    panel_bg = f'rgba(20, 20, 20, {alpha})'
    hover_alpha = 90
    return f"""
        #control-panel {{
            background-color: {panel_bg};
            border-radius: {PANEL_RADIUS}px;
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
    (Player/MaxView via position_control_panel, plus their own
    hover/idle-hide timers); this widget doesn't show/hide or position
    itself.
    """
    prev_clicked = pyqtSignal()
    play_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    tracklist_clicked = pyqtSignal()
    lyrics_clicked = pyqtSignal()
    heart_clicked = pyqtSignal()
    back_clicked = pyqtSignal()
    more_clicked = pyqtSignal()
    shuffle_clicked = pyqtSignal()
    repeat_clicked = pyqtSignal()
    # Volume popup (speaker button): slider moved (0-100) / mute toggled
    volume_changed = pyqtSignal(int)
    mute_clicked = pyqtSignal()

    def __init__(self, parent=None, show_back=False, show_side_toggles=True,
                 show_more=False):
        super().__init__(parent)
        self.setObjectName('control-panel')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._accent = theme_mod.DEFAULT_ACCENT
        self._opacity = DEFAULT_OPACITY
        self._icon_fg = 'white'
        # Toggle (tracklist/lyrics/shuffle/repeat) on/off icon colors
        self._on_fg = 'white'
        self._off_fg = SCRIM_TOGGLE_OFF
        self._title_text = ''
        self._playing = False
        self._favorited = False
        self._tracklist_on = False
        self._lyrics_on = False
        self._shuffle_on = False
        self._repeat_mode = 'off'
        self._volume = 1.0
        self._muted = False
        self._seek_mode = False  # podcasts: prev/next are -30s/+30s
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
        # Speaker: opens a slider popup (volume also follows the mouse
        # wheel over the art and the . / , keys — App owns the value)
        self.volume_btn = self._make_button('volume_up', 'Volume (scroll over the art · . / ,)',
                                            size=26, icon_size=17)
        self.volume_btn.clicked.connect(self._open_volume_popup)
        row1.addWidget(self.volume_btn)
        self.volume_popup = VolumePopup(self)
        self.volume_popup.volume_changed.connect(self.volume_changed.emit)
        self.volume_popup.mute_clicked.connect(self.mute_clicked.emit)
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

        # Row 3: [tracklist toggle] | shuffle | transport | repeat | [⋯] | [back] | [lyrics toggle]
        # Bracketed buttons are optional; omitted ones reserve no space.
        # The two pane toggles sit at the outer edges, on the side their
        # pane opens (library left, lyrics right).
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
        # ⋯ menu (main window only): theme, preferences, max mode, pin...
        # — everything the old toolbar's gear button held
        self.more_btn = None
        if show_more:
            self.more_btn = self._make_button('more_horiz', 'Menu')
            self.more_btn.clicked.connect(self.more_clicked.emit)
            row3.addWidget(self.more_btn)
        self.back_btn = None
        if show_back:
            self.back_btn = self._make_button('close', 'Back')
            self.back_btn.clicked.connect(self.back_clicked.emit)
            row3.addWidget(self.back_btn)
        self.lyrics_btn = None
        if show_side_toggles:
            self.lyrics_btn = self._make_button('lyrics', 'Toggle lyrics / show info (5)')
            self.lyrics_btn.clicked.connect(self.lyrics_clicked.emit)
            row3.addWidget(self.lyrics_btn)
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
        theme/accent/text-size changes, same as everything else. Opacity
        is remembered across calls that omit it (t may be a partial dict)."""
        self._accent = t.get('accent', theme_mod.DEFAULT_ACCENT)
        if 'overlay_opacity' in t:
            self._opacity = t['overlay_opacity']
        self.setStyleSheet(_panel_qss(
            t, fs or theme_mod.DEFAULT_SIZE, self._opacity))
        self.volume_popup.set_theme(self._accent, fs or theme_mod.DEFAULT_SIZE)
        self._refresh_icons()
        self._apply_title_elide()

    def _refresh_icons(self):
        fg = self._icon_fg
        if self.tracklist_btn:
            self.tracklist_btn.setIcon(_toggle_icon(
                'tracklist', self._tracklist_on, self._on_fg, self._off_fg, self.tracklist_btn._icon_size))
        if self.lyrics_btn:
            self.lyrics_btn.setIcon(_toggle_icon(
                'lyrics', self._lyrics_on, self._on_fg, self._off_fg, self.lyrics_btn._icon_size))
        self.shuffle_btn.setIcon(_toggle_icon(
            'shuffle', self._shuffle_on, self._on_fg, self._off_fg, self.shuffle_btn._icon_size))
        self.repeat_btn.setIcon(_repeat_icon(
            self._repeat_mode, self._on_fg, self._off_fg, self.repeat_btn._icon_size))
        self._refresh_skip_icons()
        self.play_btn.setIcon(_icon_for(
            'pause' if self._playing else 'play_arrow', fg, self.play_btn._icon_size))
        self.heart_btn.setIcon(_heart_icon(self._favorited, self._accent, self.heart_btn._icon_size))
        self.volume_btn.setIcon(_icon_for(volume_icon_name(self._volume, self._muted),
                                          fg, self.volume_btn._icon_size))
        if self.back_btn:
            self.back_btn.setIcon(_icon_for('close', fg, self.back_btn._icon_size))
        if self.more_btn:
            self.more_btn.setIcon(_icon_for('more_horiz', fg, self.more_btn._icon_size))

    def _refresh_skip_icons(self):
        prev_name, next_name = (('fast_rewind', 'fast_forward') if self._seek_mode
                                else ('skip_previous', 'skip_next'))
        self.prev_btn.setIcon(_icon_for(prev_name, self._icon_fg, self.prev_btn._icon_size))
        self.next_btn.setIcon(_icon_for(next_name, self._icon_fg, self.next_btn._icon_size))

    # ── Volume ──────────────────────────────────────────────────────

    def _open_volume_popup(self):
        self.volume_popup.open_below(self.volume_btn)

    def volume_popup_open(self):
        return self.volume_popup.isVisible()

    def set_volume_state(self, volume, muted):
        self._volume = volume
        self._muted = muted
        self.volume_btn.setIcon(_icon_for(volume_icon_name(volume, muted),
                                          self._icon_fg, self.volume_btn._icon_size))
        self.volume_btn.setToolTip(f'{volume_text(volume, muted)} — scroll over the art · . / ,')
        self.volume_popup.set_state(volume, muted)

    # ── State (called by the host view) ──────────────────────────────

    def set_seek_mode(self, on):
        """Podcasts swap previous/next for -30s/+30s seeks."""
        self._seek_mode = on
        self.prev_btn.setToolTip('Back 30s (<)' if on else 'Previous (<)')
        self.next_btn.setToolTip('Forward 30s (>)' if on else 'Next (>)')
        self._refresh_skip_icons()

    def set_seek_visible(self, visible):
        """Radio streams have no position: hide skip buttons and the
        progress row entirely."""
        for w in (self.prev_btn, self.next_btn, self.progress_bar,
                  self.pos_label, self.len_label):
            w.setVisible(visible)

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
                'tracklist', tracklist_on, self._on_fg, self._off_fg, self.tracklist_btn._icon_size))
        if self.lyrics_btn:
            self.lyrics_btn.setIcon(_toggle_icon(
                'lyrics', lyrics_on, self._on_fg, self._off_fg, self.lyrics_btn._icon_size))

    def set_shuffle_state(self, on):
        self._shuffle_on = on
        self.shuffle_btn.setIcon(_toggle_icon(
            'shuffle', on, self._on_fg, self._off_fg, self.shuffle_btn._icon_size))

    def set_repeat_state(self, mode):
        self._repeat_mode = mode
        self.repeat_btn.setIcon(_repeat_icon(
            mode, self._on_fg, self._off_fg, self.repeat_btn._icon_size))


def position_control_panel(panel, art_x, art_y, art_w, art_h):
    """Center the panel along the art's bottom edge, capped to 420px so the
    progress bar/title don't stretch absurdly wide over large art."""
    w = min(art_w - 32, 420)
    if w <= 0:
        return
    panel.setFixedWidth(w)
    h = panel.sizeHint().height()
    x = art_x + (art_w - w) // 2
    y = art_y + art_h - h - 16
    panel.setGeometry(x, y, w, h)


class VolumePopup(QFrame):
    """The speaker button's popup: mute toggle, slider, percentage. A
    Qt.Popup window, so it closes on any click outside and takes the mouse
    wheel while open. Always the dark scrim look, like the panel."""
    volume_changed = pyqtSignal(int)   # 0-100, as the slider moves
    mute_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName('volume-popup')
        self._muted = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 10, 6)
        lay.setSpacing(6)
        self.mute_btn = QToolButton(self)
        self.mute_btn.setToolTip('Mute')
        self.mute_btn.setCursor(Qt.PointingHandCursor)
        self.mute_btn.setFocusPolicy(Qt.NoFocus)
        self.mute_btn.setFixedSize(26, 26)
        self.mute_btn.setIconSize(QSize(17, 17))
        self.mute_btn.clicked.connect(self.mute_clicked.emit)
        lay.addWidget(self.mute_btn)
        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(0, 100)
        self.slider.setSingleStep(5)
        self.slider.setPageStep(10)
        self.slider.setFixedWidth(140)
        self.slider.valueChanged.connect(self._on_slider)
        lay.addWidget(self.slider)
        self.value_label = QLabel(self)
        self.value_label.setMinimumWidth(36)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.value_label)
        self._syncing = False
        self.set_theme(theme_mod.DEFAULT_ACCENT, theme_mod.DEFAULT_SIZE)

    def set_theme(self, accent, fs):
        self.setStyleSheet(f"""
            #volume-popup {{
                background-color: rgba(20, 20, 20, 235);
                border: 1px solid rgba(255, 255, 255, 30);
            }}
            #volume-popup QLabel {{
                color: white;
                font-family: {theme_mod.FONT};
                font-size: {max(fs - 2, 7)}pt;
                background: transparent;
            }}
            {_shared_button_qss('#volume-popup', accent)}
            #volume-popup QSlider::groove:horizontal {{
                height: 4px;
                background: rgba(255, 255, 255, 50);
            }}
            #volume-popup QSlider::sub-page:horizontal {{
                background: {accent};
            }}
            #volume-popup QSlider::handle:horizontal {{
                background: white;
                width: 10px;
                margin: -5px 0;
                border-radius: 0px;
            }}
        """)

    def set_state(self, volume, muted):
        self._muted = muted
        self._syncing = True
        self.slider.setValue(round(volume * 100))
        self._syncing = False
        self.value_label.setText('Muted' if muted else f'{round(volume * 100)}%')
        self.mute_btn.setIcon(_icon_for(volume_icon_name(volume, muted), 'white', 17))
        self.mute_btn.setToolTip('Unmute' if muted else 'Mute')

    def _on_slider(self, value):
        if not self._syncing:
            self.volume_changed.emit(value)

    def open_below(self, button):
        """Pop up just above the speaker button (the panel sits at the
        art's bottom edge, so above is where the room is)."""
        self.adjustSize()
        g = button.mapToGlobal(QPoint(button.width() // 2, 0))
        self.move(g.x() - self.width() + button.width() // 2 + 8, g.y() - self.height() - 6)
        self.show()
        self.slider.setFocus()


class VolumeOSD(QLabel):
    """Brief 'Volume 65%' readout over the art for wheel / key changes —
    the panel may be hidden, and the keys give no other feedback."""

    SHOW_MS = 1200

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('volume-osd')
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f"""
            #volume-osd {{
                background-color: rgba(20, 20, 20, 200);
                color: white;
                font-family: {theme_mod.FONT};
                font-weight: bold;
                padding: 6px 14px;
                border-radius: {PANEL_RADIUS}px;
            }}
        """)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.SHOW_MS)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def flash(self, volume, muted, art_rect):
        """Show the value centered near the top of art_rect (parent coords)."""
        self.setText(volume_text(volume, muted))
        self.adjustSize()
        self.move(art_rect.x() + (art_rect.width() - self.width()) // 2,
                  art_rect.y() + 16)
        self.show()
        self.raise_()
        self._timer.start()
