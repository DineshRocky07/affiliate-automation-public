"""Console helpers for Windows (cp1252) terminals."""
import sys


def enable_utf8() -> None:
    """Make stdout/stderr UTF-8 so emoji/rupee prints never crash on Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
