# Theme definitions and stylesheet generation.
#
# Modern-minimal design language:
#   - flat, borderless panes separated by hairline splitter handles
#   - the now-playing column and toolbar sit on a subtly elevated background
#   - accent color carries meaning: selection, progress, active states, and a
#     light accent tint woven into hover states so it reads as the app's
#     personality color, not just an occasional flag
#   - accent is NEVER used as literal text color at face value — anywhere it
#     sits directly on a page background as foreground text (lyrics active
#     line, description timestamps), App.apply_theme computes a stricter
#     'accent_text' variant (WCAG ~4.5:1) so legibility always wins over
#     hue-matching, in both themes and for any user-picked or art-matched
#     accent color
#   - album art and the (preset or per-album) accent are the visual centerpiece
#
# One consolidated stylesheet (build_qss) is applied once to the main window;
# focused-pane highlighting is driven by a dynamic 'paneFocused' widget
# property instead of stylesheet regeneration.

from PyQt5.QtGui import QColor, QFontDatabase

LIGHT = {
    'bg':           '#fafafb',
    'bg_elevated':  '#eef0f4',
    'fg':           '#16161a',
    'fg_dim':       '#74747d',
    'hairline':     '#e1e3e8',
    'hover':        '#e6e9f0',
    'accent':       'orange',   # overridden at apply time
    'accent_fg':    'black',    # computed at apply time
}

DARK = {
    'bg':           '#131316',
    'bg_elevated':  '#1e1e24',
    'fg':           '#f2f2f5',
    'fg_dim':       '#9898a3',
    'hairline':     '#302f38',
    'hover':        '#28282f',
    'accent':       '#f2932c',
    'accent_fg':    'black',
}

# Legacy token aliases — external dialogs (artwork finder, radio search) and
# the lyrics HTML renderer still read these names.
for _t in (LIGHT, DARK):
    _t['bg_alt'] = _t['bg_elevated']
    _t['border'] = _t['hairline']
    _t['grip'] = _t['fg_dim']
    _t['btn_bg'] = _t['hover']
    _t['btn_hover'] = _t['hover']
    _t['selection'] = _t['accent']
    _t['selection_text'] = _t['accent_fg']
    _t['scrollbar_bg'] = _t['bg']

# One font for the entire application: Inter, bundled in src/fonts/ and
# registered at startup by resolve_fonts(). If the bundled files are ever
# missing, resolve_fonts falls back to the best available system sans.
FONT = "'Inter'"

# One size scale for the whole app — everything steps together.
SIZES = [8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20]
DEFAULT_SIZE = 10

_FALLBACK_FONTS = ['Noto Sans', 'Segoe UI', 'Helvetica Neue', 'Ubuntu', 'Arial']


def resolve_fonts():
    """Register the bundled Inter files with Qt; fall back to a system sans
    only if they're missing. Must run after QApplication exists."""
    global FONT
    import sys
    from pathlib import Path
    if getattr(sys, '_MEIPASS', None):
        fonts_dir = Path(sys._MEIPASS) / 'fonts'
    else:
        fonts_dir = Path(__file__).parent / 'fonts'
    if fonts_dir.is_dir():
        for f in sorted(fonts_dir.glob('*.ttf')):
            QFontDatabase.addApplicationFont(str(f))
    families = set(QFontDatabase().families())
    if 'Inter' in families:
        FONT = "'Inter'"
    else:
        fallback = next((f for f in _FALLBACK_FONTS if f in families), 'sans-serif')
        FONT = f"'{fallback}'"

DEFAULT_ACCENT = 'orange'
ACCENT_PRESETS = {
    'Orange':     'orange',
    'Coral':      '#ff6f61',
    'Rose':       '#e8557a',
    'Lavender':   '#9b7ed8',
    'Sky Blue':   '#5ba4cf',
    'Teal':       '#2bbbad',
    'Mint':       '#66cdaa',
    'Gold':       '#f0c040',
    'Slate':      '#708090',
}


def _alpha(color, alpha):
    """CSS rgba() string for a color name/hex at the given 0-255 alpha."""
    c = QColor(color)
    return f'rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})'


def track_list_qss(t, fs=None):
    """QSS for the tracklist (#track-list) and its search bar (#search-bar).

    Factored out of build_qss() so it can also be applied directly to
    AlbumView when it's borrowed into MiniView — a separate top-level window
    that the main stylesheet never reaches (see App._attach_mini_tracklist).
    """
    fs_t = fs or DEFAULT_SIZE
    accent = t['accent']
    accent_fg = t['accent_fg']
    accent_hover = _alpha(accent, 22)
    item_pad = max(3, (fs_t - 10) // 2 + 3)
    return f"""
        #track-list {{
            background-color: {t['bg']};
            font-size: {fs_t}pt;
            font-family: {FONT};
            border: none;
            color: {t['fg']};
            outline: none;
        }}
        #track-list::item {{
            padding: {item_pad}px 4px;
        }}
        #track-list::item:hover {{ background-color: {accent_hover}; }}
        #track-list::item:selected {{
            background-color: {t['hover']};
            color: {t['fg']};
        }}
        #track-list[paneFocused="true"]::item:selected {{
            background-color: {accent};
            color: {accent_fg};
        }}
        #search-bar {{
            background-color: {t['bg_elevated']};
            color: {t['fg']};
            border: 1px solid {t['hairline']};
            font-family: {FONT};
            font-size: {fs_t}pt;
            padding: 5px 8px;
        }}
        #search-bar:focus {{
            border: 1px solid {accent};
        }}
    """


def minimal_scrollbar_qss(t, selector='#lyrics-text'):
    """A thin scrollbar that fades into the background — a faint handle with
    no visible track, just enough to hint at scroll position. Scoped to a
    selector rather than applied globally (the base stylesheet hides
    scrollbars everywhere else — see 'QScrollBar:vertical { width: 0; }' in
    build_qss); used for the lyrics pane in max/mini mode, where the pane is
    short enough that scrolling isn't otherwise obvious.
    """
    handle = _alpha(t['fg'], 40)
    handle_hover = _alpha(t['fg'], 90)
    return f"""
        {selector} QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 2px;
        }}
        {selector} QScrollBar::handle:vertical {{
            background: {handle};
            border-radius: 4px;
            min-height: 24px;
        }}
        {selector} QScrollBar::handle:vertical:hover {{
            background: {handle_hover};
        }}
        {selector} QScrollBar::add-line:vertical,
        {selector} QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        {selector} QScrollBar::add-page:vertical,
        {selector} QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
    """


def build_qss(t, fs=None):
    """The entire application stylesheet, applied once to the main window.

    Focus styling uses the dynamic 'paneFocused' property on the tree/list
    views — flipping the property repolishes only those widgets, so no
    stylesheet is ever rebuilt on focus changes.
    """
    fs_c = fs_t = fs_l = fs or DEFAULT_SIZE
    accent = t['accent']
    accent_fg = t['accent_fg']
    accent_soft = _alpha(accent, 38)     # pill/selection tint
    accent_press = _alpha(accent, 70)
    accent_hover = _alpha(accent, 22)    # faint accent tint for hover states
    item_pad = max(3, (fs_t - 10) // 2 + 3)

    return f"""
        /* ── Base ─────────────────────────────────────────────── */
        QMainWindow, #main-window, #left-stack {{
            background-color: {t['bg']};
        }}
        /* Frameless window: root_stack fills the window edge to edge and
           draws the window's own 1px hairline outline (no OS border).
           Hidden while maximized/fullscreen, like a normal window's border
           merging with the screen edge. Resizing is invisible overlay
           grips (window_chrome.py), not a padded margin. */
        #root-stack {{
            background-color: {t['bg']};
            border: 1px solid {t['hairline']};
        }}
        #root-stack[maximized="true"] {{
            border: none;
        }}
        QMenuBar {{
            background-color: {t['bg']};
            border: none; padding: 0; margin: 0; max-height: 0;
        }}
        QScrollBar:vertical {{ width: 0; }}
        QScrollBar:horizontal {{ height: 0; }}
        QToolTip {{
            background-color: {t['bg_elevated']};
            color: {t['fg']};
            border: 1px solid {t['hairline']};
            padding: 4px 8px;
        }}

        /* ── Splitters: handles are custom-painted (grip_splitter.py) ── */
        QSplitter::handle {{ background: transparent; }}

        /* ── Titlebar: custom frameless-window chrome, sits directly on
           top of the toolbar with the same background so the two read as
           one continuous strip (mirrors the titlebar+tabbar stack in the
           sibling 'text' app) ── */
        #titlebar {{
            background-color: {t['bg_elevated']};
            border-bottom: 1px solid {t['hairline']};
        }}
        #titlebar-title {{
            color: {t['fg_dim']};
            font-family: {FONT};
            font-size: {fs_c}pt;
        }}
        #titlebar-buttons QToolButton {{
            background: transparent;
            border: none;
            color: {t['fg_dim']};
        }}
        #titlebar-buttons QToolButton:hover {{
            background-color: {accent_hover};
            color: {t['fg']};
        }}
        #tb-close:hover {{
            background-color: #c0392b;
            color: white;
        }}

        /* ── Toolbar: accent strip, elevated strip, square toggles ── */
        #accent-bar {{
            background-color: {accent};
        }}
        #toolbar {{
            background-color: {t['bg_elevated']};
        }}
        #mode-toggle, #panel-toggle, #icon-button {{
            background: transparent;
            border: none;
            padding: 1px 9px;
        }}
        #mode-toggle:hover, #panel-toggle:hover, #icon-button:hover {{
            background-color: {accent_hover};
        }}
        #icon-button::menu-indicator {{ image: none; width: 0; }}

        /* ── Menus ────────────────────────────────────────────── */
        QMenu {{
            background-color: {t['bg_elevated']};
            color: {t['fg']};
            font-family: {FONT};
            font-size: {fs_c}pt;
            border: 1px solid {t['hairline']};
            padding: 4px;
        }}
        QMenu::item {{
            padding: 5px 22px;
        }}
        QMenu::item:selected {{
            background-color: {accent_soft};
            color: {t['fg']};
        }}
        QMenu::separator {{
            height: 1px;
            background: {t['hairline']};
            margin: 4px 8px;
        }}
        QMenu::indicator:checked {{
            image: none;
            background-color: {accent};
            border: none;
            width: 10px; height: 10px;
            margin-left: 6px;
        }}
        QMenu::indicator:unchecked {{
            background-color: {t['hover']};
            border: none;
            width: 10px; height: 10px;
            margin-left: 6px;
        }}

        /* ── Player column: now-playing card ─────────────────── */
        #player {{
            background-color: {t['bg']};
        }}
        #track-info {{
            font-family: {FONT};
            font-size: {fs_c + 1}pt;
            color: {t['fg']};
            background: transparent;
        }}
        #track-progress, #track-length {{
            font-family: {FONT};
            font-size: {max(fs_c - 1, 7)}pt;
            color: {t['fg_dim']};
            background: transparent;
        }}
        QProgressBar {{
            border: none;
            background: {t['hover']};
        }}
        QProgressBar::chunk {{
            background-color: {accent};
        }}
        #prev-button, #play-button, #next-button {{
            background: transparent;
            border: none;
            padding: 2px 8px;
        }}
        #prev-button:hover, #play-button:hover, #next-button:hover {{
            background: {accent};
        }}
        #prev-button:pressed, #play-button:pressed, #next-button:pressed {{
            background: {accent_press};
        }}

        /* ── Library tree / tracklist: flat, accent selection ──── */
        FolderView, AlbumView {{
            background-color: {t['bg']};
        }}
        QTreeView {{
            font-size: {fs_t}pt;
            font-family: {FONT};
            border: none;
            background-color: {t['bg']};
            color: {t['fg']};
            outline: none;
        }}
        QTreeView::item {{
            padding: {item_pad}px 2px;
        }}
        QTreeView::branch {{ image: none; background: {t['bg']}; }}
        QTreeView::item:hover {{ background-color: {accent_hover}; }}
        QTreeView::item:selected {{
            background-color: {t['hover']};
            color: {t['fg']};
        }}
        QTreeView[paneFocused="true"]::item:selected {{
            background-color: {accent};
            color: {accent_fg};
        }}
        {track_list_qss(t, fs_t)}

        /* ── Lyrics pane ──────────────────────────────────────── */
        LyricsWidget {{
            background-color: {t['bg']};
            border: none;
        }}
        #lyrics-text {{
            background-color: {t['bg']};
            color: {t['fg']};
            font-family: {FONT};
            font-size: {fs_l}pt;
        }}

        /* ── Podcast / radio panels: same list language ─────────── */
        PodcastView, RadioView {{
            background-color: {t['bg']};
        }}
        PodcastView QListWidget, RadioView QListWidget {{
            font-size: {fs_t}pt;
            font-family: {FONT};
            color: {t['fg']};
            background-color: {t['bg']};
            border: none;
            outline: none;
        }}
        PodcastView QListWidget::item, RadioView QListWidget::item {{
            padding: {item_pad}px 4px;
        }}
        PodcastView QListWidget::item:hover, RadioView QListWidget::item:hover {{
            background-color: {accent_hover};
        }}
        PodcastView QListWidget::item:selected, RadioView QListWidget::item:selected {{
            background-color: {accent};
            color: {accent_fg};
        }}
        PodcastView QLineEdit, RadioView QLineEdit {{
            font-size: {fs_t}pt;
            font-family: {FONT};
            color: {t['fg']};
            background-color: {t['bg_elevated']};
            border: 1px solid {t['hairline']};
            padding: 5px 8px;
        }}
        PodcastView QLineEdit:focus, RadioView QLineEdit:focus {{
            border: 1px solid {accent};
        }}
        PodcastView QPushButton, RadioView QPushButton {{
            font-size: {fs_t}pt;
            font-family: {FONT};
            color: {t['fg']};
            background-color: {t['hover']};
            border: none;
            padding: 5px 10px;
        }}
        PodcastView QPushButton:hover, RadioView QPushButton:hover {{
            background-color: {accent_soft};
            color: {t['fg']};
        }}
        #podcast-status, #radio-status {{
            font-size: {max(fs_t - 1, 7)}pt;
            font-family: {FONT};
            color: {t['fg_dim']};
            padding: 2px;
        }}

        /* ── Max mode ─────────────────────────────────────────── */
        MaxView, #max-lyrics-column {{
            background-color: {t['bg']};
        }}
        #max-divider {{
            background-color: {accent};
        }}
        #max-track-label {{
            color: {t['fg']};
            background: transparent;
            font-family: {FONT};
            font-size: {fs_c + 12}pt;
            padding: 8px 20px 20px 0;
        }}
        #max-close-btn {{
            background: transparent;
            border: none;
            border-radius: 14px;
        }}
        #max-close-btn:hover {{
            background-color: {accent_hover};
        }}
    """


def dialog_qss(t, fs=None):
    """Shared styling for the app's dialogs (help, about, fonts)."""
    fs = fs or 11
    accent = t.get('accent', DEFAULT_ACCENT)
    return f"""
        QDialog {{
            background-color: {t['bg']};
        }}
        QLabel {{
            color: {t['fg']};
            font-family: {FONT};
            font-size: {fs}pt;
        }}
        QComboBox {{
            background-color: {t['bg_elevated']};
            color: {t['fg']};
            border: 1px solid {t['hairline']};
            padding: 4px 8px;
            font-size: {fs}pt;
            min-width: 140px;
        }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background-color: {t['bg_elevated']};
            color: {t['fg']};
            selection-background-color: {accent};
            border: 1px solid {t['hairline']};
        }}
        QDialogButtonBox QPushButton {{
            background-color: {t['hover']};
            color: {t['fg']};
            border: none;
            padding: 5px 16px;
        }}
        QDialogButtonBox QPushButton:hover {{
            background-color: {_alpha(accent, 38)};
        }}
    """
