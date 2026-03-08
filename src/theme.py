# Theme definitions for light and dark modes
# Each theme is a dict of color tokens used to generate QSS stylesheets

LIGHT = {
    'bg':             'white',
    'bg_alt':         '#f5f5f5',
    'fg':             'black',
    'border':         'black',
    'grip':           '#d0d0d0',
    'accent':         'orange',
    'selection':      'orange',
    'selection_text':  'black',
    'scrollbar_bg':   'white',
}

DARK = {
    'bg':             '#1e1e1e',
    'bg_alt':         '#2a2a2a',
    'fg':             '#e0e0e0',
    'border':         '#555555',
    'grip':           '#3a3a3a',
    'accent':         '#e8871e',
    'selection':      '#e8871e',
    'selection_text':  'black',
    'scrollbar_bg':   '#2a2a2a',
}

FONT = "'Consolas', 'Courier New', 'Monaco', monospace"

DEFAULT_FONT_SIZE = 13
FONT_SIZES = [10, 11, 12, 13, 14, 16, 18, 20]

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

def app_qss(t):
    return f"""
        #main-window {{
            background-color: {t['bg']};
        }}
        QSplitter::handle {{
            background-color: {t['bg']};
            border-left: 1px solid {t['grip']};
            border-right: 1px solid {t['grip']};
            border-top: 2px solid {t['accent']};
            border-bottom: 2px solid {t['accent']};
            width: 7px;
            height: 7px;
        }}
        QSplitter::handle:horizontal {{
            width: 7px;
        }}
        QSplitter::handle:vertical {{
            height: 7px;
            border-left: 2px solid {t['accent']};
            border-right: 2px solid {t['accent']};
            border-top: 1px solid {t['grip']};
            border-bottom: 1px solid {t['grip']};
        }}
        QMenuBar {{
            background-color: {t['bg']};
            color: {t['fg']};
            font-family: {FONT};
            font-size: 11pt;
            border-bottom: 2px solid {t['accent']};
        }}
        QMenuBar::item:selected {{
            background-color: {t['accent']};
            color: {t['selection_text']};
        }}
        QMenu {{
            background-color: {t['bg']};
            color: {t['fg']};
            font-family: {FONT};
            font-size: 11pt;
            border: 1px solid {t['border']};
        }}
        QMenu::item:selected {{
            background-color: {t['accent']};
            color: {t['selection_text']};
        }}
        QMenu::indicator:checked {{
            image: none;
            background-color: {t['accent']};
            border: 1px solid {t['border']};
            width: 10px;
            height: 10px;
            margin-left: 6px;
        }}
        QMenu::indicator:unchecked {{
            background-color: {t['bg']};
            border: 1px solid {t['border']};
            width: 10px;
            height: 10px;
            margin-left: 6px;
        }}
    """

def player_qss(t, fs=DEFAULT_FONT_SIZE, compact=False):
    btn_h = 35 if compact else 50
    art_margin = '2px' if compact else '10px'
    info_fs = fs if compact else fs + 2
    btn_fs = fs + 2 if compact else fs + 5
    return f"""
        #player {{
            background-color: {t['bg']};
        }}
        #album-art {{
            padding: 0;
            margin-top: {art_margin};
        }}
        #track-info {{
            font-family: {FONT};
            font-size: {info_fs}pt;
            color: {t['fg']};
        }}
        #track-progress-widget {{
            margin-left: 20;
        }}
        #track-progress {{
            font-family: {FONT};
            font-size: {info_fs}pt;
            color: {t['fg']};
        }}
        #track-length {{
            font-family: {FONT};
            font-size: {info_fs}pt;
            color: {t['fg']};
        }}
        QProgressBar {{
            border: 1px solid {t['accent']};
            background: {t['bg']};
        }}
        QProgressBar::chunk {{
            background-color: {t['accent']};
        }}
        .QPushButton {{
            background-color: {t['bg']};
            border: 1px solid {t['border']};
            color: {t['fg']};
            min-width: {'35px' if compact else '50px'};
            height: {btn_h}px;
            padding: 0;
            font-family: {FONT};
            font-size: {btn_fs}pt;
        }}
        #toggle-library-btn, #toggle-folder-btn {{
            min-width: 40px;
            max-width: 40px;
            height: 50px;
            font-size: {fs + 9}pt;
        }}
        #toggle-library-btn:checked, #toggle-folder-btn:checked {{
            background-color: {t['accent']};
            color: {t['selection_text']};
        }}
    """

def folder_view_qss(t, fs=DEFAULT_FONT_SIZE):
    return f"""
        QTreeView {{
            font-size: {fs}pt;
            font-family: {FONT};
            border: 1pt solid {t['border']};
            background-color: {t['bg']};
            color: {t['fg']};
        }}
        QTreeView::item {{
            height: 25;
        }}
        QTreeView::item:selected {{
            background-color: {t['selection']};
            color: {t['selection_text']};
        }}
        QTreeView::branch {{
            image: none;
        }}
        QTreeView::branch:selected {{
            background-color: {t['bg']};
        }}
        QScrollBar:vertical {{
            border: none;
            background: {t['scrollbar_bg']};
            width: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {t['accent']};
            min-height: 0px;
        }}
        QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {{
            border: none;
            background: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}
        #search-bar {{
            background-color: {t['bg']};
            color: {t['fg']};
            border: 1px solid {t['accent']};
            font-family: {FONT};
            font-size: {fs}pt;
            padding: 4px;
        }}
    """

def album_view_qss(t, fs=DEFAULT_FONT_SIZE):
    return f"""
        #track-list {{
            background-color: {t['bg']};
            font-size: {fs}pt;
            font-family: {FONT};
            border: none;
            color: {t['fg']};
        }}
        #track-list::item {{
            height: 25;
        }}
        #track-list::item:selected {{
            background-color: {t['selection']};
            color: {t['selection_text']};
        }}
        #search-bar {{
            background-color: {t['bg']};
            color: {t['fg']};
            border: 1px solid {t['accent']};
            font-family: {FONT};
            font-size: {fs}pt;
            padding: 4px;
        }}
    """

def lyrics_qss(t, fs=DEFAULT_FONT_SIZE):
    return f"""
        #lyrics-widget {{
            background-color: {t['bg']};
        }}
        #lyrics-scroll {{
            background-color: {t['bg']};
            border: none;
        }}
        #lyrics-text {{
            background-color: {t['bg']};
            color: {t['fg']};
            font-family: {FONT};
            font-size: {fs}pt;
        }}
        #lyrics-toggle-btn {{
            background-color: {t['bg']};
            border: 1px solid {t['border']};
            color: {t['fg']};
            font-family: {FONT};
            font-size: {fs + 2}pt;
            min-width: 40px;
            max-width: 40px;
            height: 50px;
        }}
        #lyrics-toggle-btn:checked {{
            background-color: {t['accent']};
            color: {t['selection_text']};
        }}
    """
