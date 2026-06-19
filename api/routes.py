"""Sentinel Desktop — API route registry (v18).

A decorator-based registry that lets each handler declare its own HTTP method
and path, evolving the v17 imperative ``_register_*_routes`` methods into a
self-documenting route table. Handlers stay in ``api/server.py`` (no file
split); the decorator only *marks* them with metadata that
``SentinelServer._register_routes`` reads at app-build time.

Usage::

    class SentinelServer:
        @api_route("POST", "/goal")
        async def _handle_goal(self, request): ...

Future versions add routes by decorating — no editing of ``_register_*_routes``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Methods FastAPI supports on the app object for direct route registration.
_VALID_METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH", "WEBSOCKET"})


@dataclass(frozen=True)
class RouteSpec:
    """Metadata recorded for a decorated route handler."""

    method: str
    path: str


def api_route(method: str, path: str) -> Callable[[Callable], Callable]:
    """Mark a handler method with its HTTP method and path.

    The decorator records ``method``/``path`` on the function under the
    ``__route_spec__`` attribute and returns the function unchanged. The bound
    method is still a normal coroutine; registration happens later when
    ``SentinelServer._register_routes`` reads the spec.

    Args:
        method: HTTP verb (``"GET"``, ``"POST"``, …) or ``"WEBSOCKET"``.
        path: The URL path, e.g. ``"/goal"`` or ``"/jobs/{job_id}"``.

    Raises:
        ValueError: if *method* is not a recognised verb.
    """

    method_upper = method.upper()
    if method_upper not in _VALID_METHODS:
        raise ValueError(f"unknown HTTP method {method!r} for route {path!r}")

    def decorator(func: Callable) -> Callable:
        func.__route_spec__ = RouteSpec(method_upper, path)
        return func

    return decorator


def collect_routes(instance: Any) -> list[tuple[str, str, Callable]]:
    """Return ``[(method, path, bound_handler), ...]`` for every ``@api_route``
    method found on *instance*.

    Iterates the instance's class (and bases) for attributes carrying a
    ``__route_spec__`` marker, binding each to *instance*.
    """
    seen: set[tuple[str, str]] = set()
    routes: list[tuple[str, str, Callable]] = []

    # Walk the MRO so decorated handlers on base classes are included.
    for klass in type(instance).__mro__:
        for name, value in klass.__dict__.items():
            spec = getattr(value, "__route_spec__", None)
            if spec is None:
                continue
            key = (spec.method, spec.path)
            if key in seen:
                continue
            seen.add(key)
            routes.append((spec.method, spec.path, getattr(instance, name)))

    return routes


# ---------------------------------------------------------------------------
# RouteRegistry — the collected route table
# ---------------------------------------------------------------------------


class RouteRegistry:
    """Collects ``(method, path, handler)`` triples as routes are wired.

    ``SentinelServer._register_*`` methods record each route here as they wire
    it onto the FastAPI app, making the full route table queryable for parity
    checks and documentation. Future handlers decorated with ``@api_route``
    are added automatically via :func:`collect_routes`.
    """

    def __init__(self) -> None:
        self._routes: list[tuple[str, str, Callable]] = []
        self._seen: set[tuple[str, str]] = set()

    def add(self, method: str, path: str, handler: Callable) -> None:
        """Record a route. Duplicate (method, path) pairs are ignored."""
        key = (method.upper(), path)
        if key in self._seen:
            return
        self._seen.add(key)
        self._routes.append((method.upper(), path, handler))

    def add_decorated(self, instance: Any) -> None:
        """Pull in every ``@api_route``-decorated handler on *instance*."""
        for method, path, handler in collect_routes(instance):
            self.add(method, path, handler)

    @property
    def routes(self) -> list[tuple[str, str, Callable]]:
        """The collected ``[(method, path, handler), ...]`` list."""
        return list(self._routes)

    def method_path_pairs(self) -> set[tuple[str, str]]:
        """Return the set of ``(METHOD, path)`` pairs (for parity checks)."""
        return set(self._seen)

    def __len__(self) -> int:
        return len(self._routes)

    def __contains__(self, method_path: tuple[str, str]) -> bool:
        return (method_path[0].upper(), method_path[1]) in self._seen
