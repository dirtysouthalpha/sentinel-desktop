"""Sentinel Desktop v22.0 "Aria" — GUI tabs package.

Importing the submodules here binds them as attributes of this package on
every Python version. This matters for unittest.mock.patch("gui.tabs.<sub>")
on Python 3.10, whose dotted-target resolver does getattr(gui.tabs, <sub>)
and fails if the submodule was only imported via 'from gui.tabs.<sub> import X'.
3.11+ is more lenient and binds implicitly.
"""

from . import (  # noqa: F401  (imported for side effect: package-attribute binding)
    brain_tab,
    history_tab,
    memory_tab,
    scripts_tab,
    settings_tab,
    workflows_tab,
)
