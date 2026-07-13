# Keep-alive registry for superseded background QThreads.
#
# Replacing (or dropping) the last Python reference to a *running* QThread
# destroys the underlying C++ object, which is a hard process abort
# ("QThread: Destroyed while thread is still running"). Anything that
# restarts background work on every user action (album loads, lyrics
# fetches, palette extractions) parks the superseded thread here instead of
# wait()ing on it — the UI never blocks, and the thread object stays
# referenced until it has actually finished.
#
# Callers disconnect their result signals before retiring, so a parked
# thread's late result is never delivered anywhere.

_parked = set()


def retire(thread):
    """Keep a (possibly running) QThread alive until it finishes.

    Returns immediately; never blocks the caller. Relies on the real
    QThread.finished signal, so subclasses must not shadow it with a
    custom signal of the same name.
    """
    if thread is None or not thread.isRunning():
        return
    _parked.add(thread)

    def _done():
        # finished has fired, so this returns (near-)immediately — it only
        # closes the microscopic gap between the signal emission and the
        # thread actually ending, after which destruction is safe.
        thread.wait()
        _parked.discard(thread)

    thread.finished.connect(_done)
    # finished may have fired between isRunning() and connect(); sweep.
    if thread.isFinished():
        _parked.discard(thread)


def wait_all(ms_each=5000):
    """Best-effort wait for every parked thread (app shutdown only).
    Threads that outlive their wait stay referenced — dropping them while
    running is exactly the abort this module exists to prevent."""
    for t in list(_parked):
        t.wait(ms_each)
        if t.isFinished():
            _parked.discard(t)


def any_running():
    """True if any parked thread is still running (shutdown fallback check)."""
    return any(t.isRunning() for t in _parked)
