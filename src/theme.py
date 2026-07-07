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

# Curated font options grouped by family (resolved at startup)
FONT_OPTIONS = [
    # Sans-serif
    'Segoe UI', 'Helvetica Neue', 'Arial', 'Roboto',
    'Noto Sans', 'Open Sans', 'Inter', 'Ubuntu',
    # Serif
    'Georgia', 'Palatino Linotype', 'Cambria', 'Times New Roman',
    'Noto Serif', 'DejaVu Serif', 'Liberation Serif', 'Merriweather',
    # Monospace
    'Consolas', 'Cascadia Mono', 'JetBrains Mono', 'Fira Code',
    'Source Code Pro', 'DejaVu Sans Mono', 'Courier New', 'Monaco',
    'Menlo', 'Ubuntu Mono',
]
AVAILABLE_FONTS = []  # populated by resolve_fonts()

# Three font categories: controls (toggles/menus), tracklist, lyrics
FONT_CONTROLS = "'Noto Sans'"
FONT_TRACKLIST = "'Noto Sans'"
FONT_LYRICS = "'Noto Sans'"

# Size options per category
SIZES_CONTROLS = [8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20]
SIZES_TRACKLIST = [8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20]
SIZES_LYRICS = [8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20]

DEFAULT_SIZE_CONTROLS = 10
DEFAULT_SIZE_TRACKLIST = 10
DEFAULT_SIZE_LYRICS = 10

# Legacy alias used by max mode and dialogs
FONT = "'Noto Sans'"

def resolve_fonts():
    """Find which curated fonts are available on this system."""
    global AVAILABLE_FONTS, FONT, FONT_CONTROLS, FONT_TRACKLIST, FONT_LYRICS
    available = set(QFontDatabase().families())
    AVAILABLE_FONTS = [f for f in FONT_OPTIONS if f in available]
    if not AVAILABLE_FONTS:
        AVAILABLE_FONTS = ['sans-serif']
    default = f"'{AVAILABLE_FONTS[0]}'"
    FONT = default
    FONT_CONTROLS = default
    FONT_TRACKLIST = default
    FONT_LYRICS = default

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


def build_qss(t, fs_controls=None, fs_tracklist=None, fs_lyrics=None):
    """The entire application stylesheet, applied once to the main window.

    Focus styling uses the dynamic 'paneFocused' property on the tree/list
    views — flipping the property repolishes only those widgets, so no
    stylesheet is ever rebuilt on focus changes.
    """
    fs_c = fs_controls or DEFAULT_SIZE_CONTROLS
    fs_t = fs_tracklist or DEFAULT_SIZE_TRACKLIST
    fs_l = fs_lyrics or DEFAULT_SIZE_LYRICS
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
            font-family: {FONT_CONTROLS};
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
            font-family: {FONT_CONTROLS};
            font-size: {fs_c + 1}pt;
            font-weight: 600;
            color: {t['fg']};
            background: transparent;
        }}
        #track-progress, #track-length {{
            font-family: {FONT_CONTROLS};
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
            font-family: {FONT_TRACKLIST};
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
        #track-list {{
            background-color: {t['bg']};
            font-size: {fs_t}pt;
            font-family: {FONT_TRACKLIST};
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
            font-family: {FONT_TRACKLIST};
            font-size: {fs_t}pt;
            padding: 5px 8px;
        }}
        #search-bar:focus {{
            border: 1px solid {accent};
        }}

        /* ── Lyrics pane ──────────────────────────────────────── */
        LyricsWidget {{
            background-color: {t['bg']};
            border: none;
        }}
        #lyrics-text {{
            background-color: {t['bg']};
            color: {t['fg']};
            font-family: {FONT_LYRICS};
            font-size: {fs_l}pt;
        }}

        /* ── Podcast / radio panels: same list language ─────────── */
        PodcastView, RadioView {{
            background-color: {t['bg']};
        }}
        PodcastView QListWidget, RadioView QListWidget {{
            font-size: {fs_t}pt;
            font-family: {FONT_TRACKLIST};
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
            font-family: {FONT_TRACKLIST};
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
            font-family: {FONT_TRACKLIST};
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
            font-family: {FONT_TRACKLIST};
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
            font-family: {FONT_CONTROLS};
            font-size: {fs_c + 12}pt;
            font-weight: 600;
            padding: 8px 20px 20px 0;
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
            font-family: {FONT_CONTROLS};
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
