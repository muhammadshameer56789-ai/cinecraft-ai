"""Caps simultaneous full-size renders (each needs ~150 MB per megapixel)."""
import contextlib
import threading

from app import config

_sem = threading.BoundedSemaphore(max(1, config.HEAVY_CONCURRENCY))


class Busy(Exception):
    pass


@contextlib.contextmanager
def heavy(timeout: float = 60.0):
    if not _sem.acquire(timeout=timeout):
        raise Busy()
    try:
        yield
    finally:
        _sem.release()
