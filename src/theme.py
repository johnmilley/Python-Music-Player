# Theme definitions for light and dark modes
# Each theme is a dict of color tokens used to generate QSS stylesheets

LIGHT = {
    'bg':             'white',
    'bg_alt':         '#f5f5f5',
    'fg':             'black',
    'border':         'black',
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
    'accent':         '#e8871e',
    'selection':      '#e8871e',
    'selection_text':  'black',
    'scrollbar_bg':   '#2a2a2a',
}

FONT = "'Consolas', 'Courier New', 'Monaco', monospace"

def app_qss(t):
    return f"""
        #main-window {{
            background-color: {t['bg']};
        }}
        QSplitter::handle {{
            background-color: {t['border']};
            width: 3px;
        }}
        QMenuBar {{
            background-color: {t['bg']};
            color: {t['fg']};
            font-family: {FONT};
            font-size: 11pt;
            border-bottom: 1px solid {t['border']};
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

def player_qss(t):
    return f"""
        #player {{
            background-color: {t['bg']};
        }}
        #album-art {{
            padding: 0;
            margin-top: 10px;
        }}
        #track-info {{
            font-family: {FONT};
            font-size: 15pt;
            color: {t['fg']};
        }}
        #track-progress-widget {{
            margin-left: 20;
        }}
        #track-progress {{
            font-family: {FONT};
            font-size: 15pt;
            color: {t['fg']};
        }}
        #track-length {{
            font-family: {FONT};
            font-size: 15pt;
            color: {t['fg']};
        }}
        QProgressBar {{
            border: 1px solid {t['border']};
            background: {t['bg']};
        }}
        QProgressBar::chunk {{
            background-color: {t['accent']};
        }}
        .QPushButton {{
            background-color: {t['bg']};
            border: 1px solid {t['border']};
            color: {t['fg']};
            min-width: 50px;
            height: 50px;
            padding: 0;
            font-family: {FONT};
            font-size: 18pt;
        }}
        #play-button {{
            background-color: {t['accent']};
            color: {t['selection_text']};
        }}
        #toggle-library-btn, #toggle-folder-btn {{
            min-width: 40px;
            max-width: 40px;
            height: 50px;
            font-size: 22pt;
        }}
        #toggle-library-btn:checked, #toggle-folder-btn:checked {{
            background-color: {t['accent']};
            color: {t['selection_text']};
        }}
    """

def folder_view_qss(t):
    return f"""
        QTreeView {{
            font-size: 13pt;
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
    """

def album_view_qss(t):
    return f"""
        #track-list {{
            background-color: {t['bg']};
            font-size: 13pt;
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
    """
