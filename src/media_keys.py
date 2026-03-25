# Cross-platform media key support
#
# Layer 1: Qt.Key_Media* event filter (works when app has focus, all platforms)
# Layer 2: Native global hooks (works in background, platform-specific)
#   - Linux: MPRIS2 D-Bus via dbus-fast in a background thread
#   - macOS: NSEvent global monitor via PyObjC (optional dep)
#   - Windows: low-level keyboard hook via ctypes (no extra deps)

import sys
import threading
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, Qt


class MediaKeySignals(QObject):
    play_pause = pyqtSignal()
    next_track = pyqtSignal()
    prev_track = pyqtSignal()
    stop = pyqtSignal()


def start_native_backend():
    """Start the native media key backend BEFORE QApplication is created.
    On Linux, Qt's QApplication auto-connects to D-Bus and intercepts messages,
    so our dbus-fast service must register first.
    Returns a backend object or None.
    """
    signals = MediaKeySignals()
    backend = None
    if sys.platform == 'linux':
        backend = _try_linux(signals)
    elif sys.platform == 'darwin':
        backend = _try_macos(signals)
    elif sys.platform == 'win32':
        backend = _try_windows(signals)
    if backend:
        print(f'LOG: Global media keys active ({backend.__class__.__name__})')
    else:
        print('LOG: Media keys via Qt events only (focused window)')
    return signals, backend


class MediaKeyHandler:
    def __init__(self, window, signals=None, native_backend=None):
        self.window = window
        self.signals = signals or MediaKeySignals()
        self._native_backend = native_backend

        # Layer 1: Qt key event filter (focused window)
        self._filter = _QtMediaKeyFilter(self.signals)
        window.installEventFilter(self._filter)

        # If no pre-started backend, try now (non-Linux platforms)
        if not self._native_backend and not signals:
            self._start_native()

    def _start_native(self):
        if sys.platform == 'darwin':
            self._native_backend = _try_macos(self.signals)
        elif sys.platform == 'win32':
            self._native_backend = _try_windows(self.signals)
        if self._native_backend:
            print(f'LOG: Global media keys active ({self._native_backend.__class__.__name__})')

    def cleanup(self):
        if self._native_backend and hasattr(self._native_backend, 'cleanup'):
            self._native_backend.cleanup()


# ── Layer 1: Qt event filter ────────────────────────────────────

class _QtMediaKeyFilter(QObject):
    _KEY_MAP = {
        Qt.Key_MediaPlay: 'play_pause',
        Qt.Key_MediaPause: 'play_pause',
        Qt.Key_MediaTogglePlayPause: 'play_pause',
        Qt.Key_MediaNext: 'next_track',
        Qt.Key_MediaPrevious: 'prev_track',
        Qt.Key_MediaStop: 'stop',
    }

    def __init__(self, signals):
        super().__init__()
        self._signals = signals

    def eventFilter(self, obj, event):
        if event.type() == event.KeyPress:
            attr = self._KEY_MAP.get(event.key())
            if attr:
                getattr(self._signals, attr).emit()
                return True
        return False


# ── Layer 2: Platform backends ──────────────────────────────────

def _try_linux(signals):
    """MPRIS2 D-Bus player via dbus-fast in a background thread."""
    try:
        from dbus_fast.aio import MessageBus
        from dbus_fast.service import ServiceInterface, method, dbus_property, PropertyAccess
    except ImportError:
        print('LOG: dbus-fast not installed — pip install dbus-fast')
        return None

    try:
        backend = _LinuxMprisBackend(signals)
        return backend
    except Exception as e:
        print(f'LOG: MPRIS unavailable: {e}')
        return None


def _try_macos(signals):
    try:
        from AppKit import NSEvent
        return _MacMediaKeys(signals)
    except Exception as e:
        print(f'LOG: macOS media keys unavailable: {e}')
        return None


def _try_windows(signals):
    try:
        import ctypes
        import ctypes.wintypes
        return _WindowsMediaKeys(signals)
    except Exception as e:
        print(f'LOG: Windows media keys unavailable: {e}')
        return None


# ── Linux: MPRIS2 via dbus-fast ─────────────────────────────────

class _LinuxMprisBackend:
    """Runs dbus-fast MPRIS2 service in a background thread."""

    def __init__(self, signals):
        self.signals = signals
        self._loop = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def _run(self):
        import asyncio
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self):
        import asyncio
        from dbus_fast.aio import MessageBus
        from dbus_fast.service import ServiceInterface, method, dbus_property, PropertyAccess

        signals = self.signals

        class Player(ServiceInterface):
            def __init__(self):
                super().__init__('org.mpris.MediaPlayer2.Player')

            @method()
            def PlayPause(self):
                signals.play_pause.emit()

            @method()
            def Play(self):
                signals.play_pause.emit()

            @method()
            def Pause(self):
                signals.play_pause.emit()

            @method()
            def Stop(self):
                signals.stop.emit()

            @method()
            def Next(self):
                signals.next_track.emit()

            @method()
            def Previous(self):
                signals.prev_track.emit()

            @dbus_property(access=PropertyAccess.READ)
            def PlaybackStatus(self) -> 's':
                return 'Playing'

            @dbus_property(access=PropertyAccess.READ)
            def CanGoNext(self) -> 'b':
                return True

            @dbus_property(access=PropertyAccess.READ)
            def CanGoPrevious(self) -> 'b':
                return True

            @dbus_property(access=PropertyAccess.READ)
            def CanPlay(self) -> 'b':
                return True

            @dbus_property(access=PropertyAccess.READ)
            def CanPause(self) -> 'b':
                return True

            @dbus_property(access=PropertyAccess.READ)
            def CanControl(self) -> 'b':
                return True

        class Root(ServiceInterface):
            def __init__(self):
                super().__init__('org.mpris.MediaPlayer2')

            @method()
            def Raise(self):
                pass

            @method()
            def Quit(self):
                pass

            @dbus_property(access=PropertyAccess.READ)
            def Identity(self) -> 's':
                return 'lp Music Player'

            @dbus_property(access=PropertyAccess.READ)
            def CanQuit(self) -> 'b':
                return True

            @dbus_property(access=PropertyAccess.READ)
            def CanRaise(self) -> 'b':
                return True

            @dbus_property(access=PropertyAccess.READ)
            def HasTrackList(self) -> 'b':
                return False

            @dbus_property(access=PropertyAccess.READ)
            def DesktopEntry(self) -> 's':
                return 'lp'

        # Connect to a NEW bus connection (separate from PyQt5's)
        bus = await MessageBus().connect()
        bus.export('/org/mpris/MediaPlayer2', Player())
        bus.export('/org/mpris/MediaPlayer2', Root())
        await bus.request_name('org.mpris.MediaPlayer2.lp')
        self._ready.set()

        # Keep running until the thread is stopped
        self._stop = asyncio.Event()
        await self._stop.wait()

    def cleanup(self):
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._stop.set)


# ── macOS: NSEvent global monitor ───────────────────────────────

class _MacMediaKeys:
    NX_KEYTYPE_PLAY = 16
    NX_KEYTYPE_NEXT = 17
    NX_KEYTYPE_PREVIOUS = 18
    NX_KEYTYPE_FAST = 19
    NX_KEYTYPE_REWIND = 20

    def __init__(self, signals):
        self.signals = signals
        from AppKit import NSEvent
        mask = 1 << 14  # NSEventMaskSystemDefined
        # Global monitor: catches media keys when app is in background
        self._global_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            mask, self._handle_event)
        # Local monitor: catches media keys when app has focus
        self._local_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            mask, self._handle_local_event)

    def _handle_event(self, event):
        try:
            if event.subtype() != 8:
                return
            data = event.data1()
            key_code = (data & 0xFFFF0000) >> 16
            key_state = (data & 0xFF00) >> 8
            if key_state != 0x0A:
                return
            if key_code == self.NX_KEYTYPE_PLAY:
                self.signals.play_pause.emit()
            elif key_code in (self.NX_KEYTYPE_NEXT, self.NX_KEYTYPE_FAST):
                self.signals.next_track.emit()
            elif key_code in (self.NX_KEYTYPE_PREVIOUS, self.NX_KEYTYPE_REWIND):
                self.signals.prev_track.emit()
        except Exception:
            pass

    def _handle_local_event(self, event):
        """Local monitor handler — must return the event or None."""
        self._handle_event(event)
        return None  # consume the event so it doesn't also trigger other handlers

    def cleanup(self):
        from AppKit import NSEvent
        for monitor in (self._global_monitor, self._local_monitor):
            if monitor:
                try:
                    NSEvent.removeMonitor_(monitor)
                except Exception:
                    pass
        self._global_monitor = None
        self._local_monitor = None


# ── Windows: low-level keyboard hook ────────────────────────────

class _WindowsMediaKeys:
    VK_MEDIA_PLAY_PAUSE = 0xB3
    VK_MEDIA_NEXT_TRACK = 0xB0
    VK_MEDIA_PREV_TRACK = 0xB1
    VK_MEDIA_STOP = 0xB2
    WH_KEYBOARD_LL = 13
    WM_KEYDOWN = 0x0100

    def __init__(self, signals):
        self.signals = signals
        import ctypes
        import ctypes.wintypes
        from ctypes import CFUNCTYPE, c_int

        HOOKPROC = CFUNCTYPE(c_int, c_int, ctypes.wintypes.WPARAM,
                             ctypes.wintypes.LPARAM)
        self._hook_proc = HOOKPROC(self._ll_keyboard_proc)
        self._hook = ctypes.windll.user32.SetWindowsHookExW(
            self.WH_KEYBOARD_LL, self._hook_proc, None, 0)
        self._ctypes = ctypes

    def _ll_keyboard_proc(self, nCode, wParam, lParam):
        if nCode >= 0 and wParam == self.WM_KEYDOWN:
            vk = self._ctypes.cast(
                lParam,
                self._ctypes.POINTER(self._ctypes.wintypes.DWORD)
            ).contents.value
            if vk == self.VK_MEDIA_PLAY_PAUSE:
                self.signals.play_pause.emit()
            elif vk == self.VK_MEDIA_NEXT_TRACK:
                self.signals.next_track.emit()
            elif vk == self.VK_MEDIA_PREV_TRACK:
                self.signals.prev_track.emit()
            elif vk == self.VK_MEDIA_STOP:
                self.signals.stop.emit()
        return self._ctypes.windll.user32.CallNextHookEx(
            self._hook, nCode, wParam, lParam)

    def cleanup(self):
        if self._hook:
            try:
                self._ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
            self._hook = None
