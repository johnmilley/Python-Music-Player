# PanelManager — single source of truth for panel visibility and sizes.
#
# Panels: 'library' (the left mode stack in the main splitter), 'tracklist'
# and 'lyrics' (album view / lyrics widget in the right vertical splitter).
# Hiding a panel remembers its extent; showing it restores that extent and
# shrinks the other panes proportionally, so toggles round-trip exactly.
# Splitter drags update the remembered sizes live, so a drag followed by a
# hide/show round-trips the dragged size too.

from PyQt5.QtCore import QObject, pyqtSignal


class PanelManager(QObject):
    visibility_changed = pyqtSignal(str, bool)  # 'library'|'tracklist'|'lyrics'

    RIGHT_COLUMN = '_right_column'  # remembered-size key for the whole right splitter
    PANELS = ('library', 'tracklist', 'lyrics')

    def __init__(self, main_splitter, right_splitter, left_stack,
                 album_view, lyrics_widget, parent=None):
        super().__init__(parent)
        self.main_splitter = main_splitter
        self.right_splitter = right_splitter
        self.left_stack = left_stack
        self.album_view = album_view
        self.lyrics_widget = lyrics_widget
        self.locked = False  # max mode suspends all panel changes
        self._visible = {name: True for name in self.PANELS}
        self._remembered = {}
        self._snapshots = {}
        main_splitter.splitterMoved.connect(self._record_sizes)
        right_splitter.splitterMoved.connect(self._record_sizes)

    # ── Queries ─────────────────────────────────────────────────────

    def is_visible(self, name):
        return self._visible[name]

    def _widget(self, name):
        return {'library': self.left_stack,
                'tracklist': self.album_view,
                'lyrics': self.lyrics_widget}[name]

    def _splitter(self, name):
        return self.main_splitter if name == 'library' else self.right_splitter

    # ── Toggling ────────────────────────────────────────────────────

    def toggle(self, name):
        self.set_visible(name, not self._visible[name])

    def set_visible(self, name, show, remember_size=True):
        """Show or hide a panel. remember_size=False skips recording the
        panel's extent on hide, so programmatic hides (mode switches) don't
        clobber the size the user last gave it."""
        if self.locked or show == self._visible[name]:
            return
        if show:
            self._show(name)
        else:
            self._hide(name, remember_size)
        self._visible[name] = show
        self.visibility_changed.emit(name, show)

    def _hide(self, name, remember_size):
        widget = self._widget(name)
        splitter = self._splitter(name)
        if remember_size:
            size = splitter.sizes()[splitter.indexOf(widget)]
            if size > 0:
                self._remembered[name] = size
        widget.setVisible(False)
        # Collapse the right column entirely when both its panes are hidden
        if name in ('tracklist', 'lyrics'):
            other = 'lyrics' if name == 'tracklist' else 'tracklist'
            if not self._visible[other]:
                if remember_size:
                    ridx = self.main_splitter.indexOf(self.right_splitter)
                    rsize = self.main_splitter.sizes()[ridx]
                    if rsize > 0:
                        self._remembered[self.RIGHT_COLUMN] = rsize
                self.right_splitter.setVisible(False)

    def _show(self, name):
        widget = self._widget(name)
        if name == 'library':
            widget.setVisible(True)
            self._set_pane_size(self.main_splitter, widget,
                                self._target_size('library'))
            return
        # Right-column panel: make sure the column itself is visible first
        # (it collapses when both tracklist and lyrics are hidden)
        if not (self._visible['tracklist'] or self._visible['lyrics']):
            self.right_splitter.setVisible(True)
            self._set_pane_size(self.main_splitter, self.right_splitter,
                                self._target_size(self.RIGHT_COLUMN))
        widget.setVisible(True)
        other = 'lyrics' if name == 'tracklist' else 'tracklist'
        if self._visible[other]:
            self._set_pane_size(self.right_splitter, widget,
                                self._target_size(name))
        # If the sibling is hidden, the shown panel takes the full column.

    def _target_size(self, name):
        if name in self._remembered:
            return self._remembered[name]
        # Defaults: library 25% of the window, right column 30%,
        # tracklist/lyrics half of the right column.
        if name == 'library':
            return sum(self.main_splitter.sizes()) // 4
        if name == self.RIGHT_COLUMN:
            return int(sum(self.main_splitter.sizes()) * 0.3)
        return sum(self.right_splitter.sizes()) // 2

    def _set_pane_size(self, splitter, widget, size):
        """Give one pane the requested extent, shrinking the other visible
        panes proportionally. Total stays constant, nothing else jumps."""
        idx = splitter.indexOf(widget)
        sizes = splitter.sizes()
        total = sum(sizes)
        if idx < 0 or total <= 0 or size <= 0:
            return
        size = min(size, int(total * 0.8))
        others = [i for i in range(len(sizes)) if i != idx and sizes[i] > 0]
        other_total = sum(sizes[i] for i in others)
        remaining = total - size
        if other_total > 0 and remaining > 0:
            for i in others:
                sizes[i] = max(1, int(sizes[i] * remaining / other_total))
        sizes[idx] = max(0, total - sum(sizes[i] for i in others))
        splitter.setSizes(sizes)

    def reapply_size(self, name):
        """Re-apply a visible panel's remembered size — used after the
        widget was reparented away and back (max mode borrows the lyrics)."""
        if not self._visible[name]:
            return
        if name != 'library':
            other = 'lyrics' if name == 'tracklist' else 'tracklist'
            if not self._visible[other]:
                return  # sole pane in the column already fills it
        self._set_pane_size(self._splitter(name), self._widget(name),
                            self._target_size(name))

    def _record_sizes(self, *_):
        """Track user drags so hide/show round-trips the dragged sizes."""
        if self.locked:
            return
        sizes = self.main_splitter.sizes()
        if self._visible['library']:
            idx = self.main_splitter.indexOf(self.left_stack)
            if sizes[idx] > 0:
                self._remembered['library'] = sizes[idx]
        if self._visible['tracklist'] or self._visible['lyrics']:
            ridx = self.main_splitter.indexOf(self.right_splitter)
            if sizes[ridx] > 0:
                self._remembered[self.RIGHT_COLUMN] = sizes[ridx]
            rsizes = self.right_splitter.sizes()
            if self._visible['tracklist'] and self._visible['lyrics']:
                self._remembered['tracklist'] = rsizes[0]
                self._remembered['lyrics'] = rsizes[1]

    # ── Per-mode panel memory ────────────────────────────────────────
    # Each app mode (music/podcast/radio) remembers which right-column
    # panels the user last had open there. First visit to a mode gets its
    # default: podcasts open the tracklist (episode list), radio opens
    # neither; music keeps whatever the session restored.

    MODE_DEFAULTS = {
        'podcast': {'tracklist': True, 'lyrics': False},
        'radio':   {'tracklist': False, 'lyrics': False},
    }

    def snapshot(self, key):
        self._snapshots[key] = {'tracklist': self._visible['tracklist'],
                                'lyrics': self._visible['lyrics']}

    def apply_mode(self, key):
        """Apply a mode's remembered panel visibility, or its default on
        the first visit. Music has no default — it keeps the current state
        until a snapshot exists."""
        snap = self._snapshots.get(key) or self.MODE_DEFAULTS.get(key)
        if not snap:
            return
        for name, vis in snap.items():
            self.set_visible(name, vis, remember_size=False)

    # ── Persistence ─────────────────────────────────────────────────

    def save(self, settings):
        settings.setValue('layout/main_splitter', self.main_splitter.saveState())
        settings.setValue('layout/right_splitter', self.right_splitter.saveState())
        settings.setValue('layout/panel_sizes',
                          {k: int(v) for k, v in self._remembered.items()})
        for name in self.PANELS:
            settings.setValue(f'{name}_visible',
                              'true' if self._visible[name] else 'false')
        settings.setValue('layout/mode_panels',
                          {mode: {k: 'true' if v else 'false'
                                  for k, v in snap.items()}
                           for mode, snap in self._snapshots.items()})

    def load(self, settings):
        mode_panels = settings.value('layout/mode_panels')
        if isinstance(mode_panels, dict):
            for mode, snap in mode_panels.items():
                if isinstance(snap, dict):
                    self._snapshots[mode] = {k: v != 'false'
                                             for k, v in snap.items()}
        remembered = settings.value('layout/panel_sizes')
        if isinstance(remembered, dict):
            for k, v in remembered.items():
                try:
                    self._remembered[k] = int(v)
                except (TypeError, ValueError):
                    pass
        if settings.contains('library_visible'):
            vis = {name: settings.value(f'{name}_visible') != 'false'
                   for name in self.PANELS}
        else:
            # First run: minimal layout — player + tracklist only
            vis = {'library': False, 'tracklist': True, 'lyrics': False}
        for name, v in vis.items():
            self._visible[name] = v
            self._widget(name).setVisible(v)
        self.right_splitter.setVisible(vis['tracklist'] or vis['lyrics'])
        state = settings.value('layout/main_splitter')
        if state:
            self.main_splitter.restoreState(state)
        state = settings.value('layout/right_splitter')
        if state:
            self.right_splitter.restoreState(state)
        for name, v in vis.items():
            self.visibility_changed.emit(name, v)
