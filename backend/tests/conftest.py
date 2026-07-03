"""
conftest.py – Pytest configuration for Global-Position tests.

Sets UTF-8 as the default I/O encoding on Windows (needed for emoji in
print() calls captured by pytest under cp1252 consoles).
"""

import io
import sys


def pytest_configure(config):
    # Force UTF-8 stdout/stderr so emoji in production code doesn't crash
    # tests running under Windows cp1252 consoles.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
