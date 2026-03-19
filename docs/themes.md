# Theme System

lp has a light and dark theme defined as Python dictionaries of color tokens. These tokens are fed into QSS (Qt Style Sheet) generator functions to produce the actual stylesheets.

## Theme dictionaries

Each theme is a dict with these keys:

| Token | Light | Dark | Purpose |
|-------|-------|------|---------|
| `bg` | `white` | `#1e1e1e` | Main background |
| `bg_alt` | `#f5f5f5` | `#2a2a2a` | Alternate background (panels) |
| `fg` | `black` | `#e0e0e0` | Text color |
| `border` | `black` | `#555555` | Border color |
| `grip` | `#d0d0d0` | `#3a3a3a` | Splitter grip color |
| `accent` | `orange` | `#e8871e` | Accent / highlight color |
| `selection` | `orange` | `#e8871e` | Selection background |
| `selection_text` | `black` | `black` | Selected item text |
| `scrollbar_bg` | `white` | `#2a2a2a` | Scrollbar track |
| `btn_bg` | — | — | Button background |
| `btn_hover` | — | — | Button hover background |

## Accent color override

When applying a theme, `app.py` copies the theme dict and replaces `accent`, `selection`, and `selection_text` with the current accent color. This allows the accent to be user-chosen or album-derived without modifying the base theme.

## Album-aware accents

When an album is loaded, `color_extract.py` extracts a palette from the album art:

1. The cover image is scaled to 120x120 and every pixel is binned by hue/saturation/value
2. Near-grey and very dark pixels are filtered out
3. Bins are scored by area coverage and visual prominence
4. The most WCAG-readable color (against both light and dark backgrounds) is selected as the accent

Per-album accent choices are cached in `QSettings` under `album_accents` so they persist across sessions.

## Accent presets

The Theme menu offers named presets: Orange, Coral, Rose, Lavender, Sky Blue, Teal, Mint, Gold, and Slate. There's also a custom color picker via `QColorDialog`.

## QSS generators

`theme.py` provides per-widget QSS functions:

| Function | Scope |
|----------|-------|
| `app_qss()` | Main window, splitter handles |
| `player_qss()` | Player controls, buttons, progress bar |
| `folder_view_qss(focused)` | TreeView styling, search bar (focus-aware selection) |
| `album_view_qss(focused)` | Track list styling (focus-aware selection) |
| `lyrics_qss()` | Scroll area + text label |
| `podcast_view_qss()` | Podcast list, input, status label |
| `radio_view_qss()` | Radio station list, input, status label |
| `hover_menu_qss()` | Toolbar, menu buttons, dropdown menus |

Focus-aware styling: when folder/album view loses focus, selection background becomes transparent to maintain cursor position without visual highlighting.

## Font system

The app prefers monospace fonts, resolving in order: Consolas, Cascadia Mono, DejaVu Sans Mono, Courier New, Monaco. The font and size are adjustable from the menu and persisted in settings.
