"""Sentinel Desktop — action registry (v18).

A decorator-based registry that replaces the v17 monolithic ``_dispatch_table``
dict literal in ``core/action_executor.py``. Handlers register themselves with
``@register_action`` at class-definition time; the dispatch table is then
*derived* from the registry rather than hand-maintained.

Design notes
------------
* Handlers are stored as **unbound functions**. ``ActionExecutor`` passes
  ``self`` explicitly at call time (``handler(self, **params)``), so the
  registry keeps functions unbound — identical to the v17 dict semantics.
* ``aliases`` let one handler serve multiple action names (e.g. ``click`` /
  ``double_click`` / ``right_click`` all map to ``_click``).
* Duplicate registration is a **loud failure at import time** — the registry
  raises :class:`ActionAlreadyRegistered` rather than silently overwriting.
* The resolved action-name set is stable and queryable via
  :func:`registered_names`, which the parity test checks against the known
  v17 baseline.

Future versions (v19+) add actions by decorating a handler — no editing of a
central table required.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# A registered action handler: an unbound method of ActionExecutor that takes
# ``self`` plus keyword params and returns a result dict.
ActionHandler = Callable[..., dict[str, Any]]


class ActionAlreadyRegistered(ValueError):
    """Raised when an action name is registered more than once."""


# Module-level registry: action name → unbound handler function.
_REGISTRY: dict[str, ActionHandler] = {}


def register_action(
    name: str,
    *,
    aliases: tuple[str, ...] = (),
) -> Callable[[ActionHandler], ActionHandler]:
    """Register an action handler under *name* (and any *aliases*).

    Usage (inside the ``ActionExecutor`` class body)::

        @register_action("click", aliases=("double_click", "right_click"))
        def _click(self, *, x=0, y=0, **_): ...

    The decorator returns the function unchanged so it can also be assigned
    as a normal method. Registration is a side effect.
    """

    def decorator(func: ActionHandler) -> ActionHandler:
        for n in (name, *aliases):
            if n in _REGISTRY and _REGISTRY[n] is not func:
                raise ActionAlreadyRegistered(
                    f"action {n!r} is already registered "
                    f"(by {_REGISTRY[n].__qualname__}); cannot also register "
                    f"{func.__qualname__}",
                )
            _REGISTRY[n] = func
        return func

    return decorator


def registered_names() -> list[str]:
    """Return the sorted list of all registered action names (incl. aliases)."""
    return sorted(_REGISTRY)


def resolve(action_name: str) -> ActionHandler | None:
    """Return the unbound handler for *action_name*, or ``None`` if unknown."""
    return _REGISTRY.get(action_name)


def snapshot() -> dict[str, ActionHandler]:
    """Return a shallow copy of the full registry (name → handler)."""
    return dict(_REGISTRY)


def clear() -> None:
    """Clear the registry. Intended for tests that reload the executor module."""
    _REGISTRY.clear()
