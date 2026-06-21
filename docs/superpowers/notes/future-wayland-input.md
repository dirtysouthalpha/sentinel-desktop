# Future Work — Wayland-Native Input

**Status:** Capture doc (not designed in detail). Last updated 2026-06-21.

## Context

The v23 cross-platform wiring routes `DesktopController` input through
`core.platform.get_backend().input`, which on Linux is `LinuxStealthInput`.
That class uses **xdotool**, which is X11-only. On **Wayland** sessions
(`XDG_SESSION_TYPE=wayland`), `LinuxStealthInput.is_available()` returns `False`
and input degrades to no-op.

Most Linux desktops still run Xwayland (an X11 compatibility layer) for legacy
apps, and xdotool *can* drive those — but native Wayland apps (GNOME/Mutter,
KDE/KWin) are immune to xdotool because the Wayland protocol deliberately
isolates input for security. So headless/headless-Wayland and pure-Wayland-app
automation need a different tool.

## The candidate tools (ordered by promise)

### 1. `ydotool` — the direct Wayland equivalent of xdotool
- Works on **both** X11 and Wayland via the kernel `uinput` module.
- Requires `/dev/uinput` access (add user to `input` group, or run a
  `ydotoold` daemon with elevated perms).
- API mirrors xdotool closely (`ydotool mousemove`, `ydotool click`, etc.).
- **Best near-term choice.** A `YdotoolLinuxStealthInput` subclass or a probe
  in `LinuxStealthInput.__init__` (prefer ydotool when
  `XDG_SESSION_TYPE=wayland`, else xdotool) is the natural implementation.

### 2. `wtype` — Wayland-native text input
- Wayland's `virtual-keyboard` protocol; works on wlroots-based compositors
  (Sway, Hyprland) but NOT on GNOME Mutter (Mutter blocks virtual keyboards
  without a portal).
- Only does keyboard (`wtype`), not mouse. Pair with ydotool for mouse.
- Useful as a fast keyboard path on wlroots.

### 3. libei / libeis — the modern, portal-based path
- Emphasis Integration Interface — the freedesktop.org standard for input
  emulation via an Input Capture portal. GNOME and KDE are adopting it.
- Python bindings: `libei` via gobject-introspection, or the `libei-python`
  package if it matures. As of 2026 still maturing; portal UX requires a
  per-session user consent dialog.
- **Best long-term choice** (portal-based = no root, works on GNOME), but the
  consent-dialog UX makes it awkward for a background automation agent.

## Recommended approach (when this becomes Phase 13+)

1. Add a probe `_probe_ydotool()` in `linux_backend.py` (mirror the existing
   `_probe_xdotool()`).
2. In `LinuxStealthInput.__init__`, pick the toolchain:
   - Wayland session + ydotool available → `ydotool` mode.
   - X11 + xdotool available → current behavior.
   - Neither → degrade (NoOp), as today.
3. Add a `_run_input(*args)` dispatcher that prefixes `ydotool` vs `xdotool`
   so the method bodies don't fork.
4. Document the `/dev/uinput` setup (or `ydotoold` daemon) in RELEASING.md /
   README — it's an OS package + a one-time permission grant, not pip.

## Non-goals / out of scope for the first Wayland pass

- GNOME Mutter native (blocked on libei maturity + portal consent UX).
- macOS input is already routed via pyautogui+Quartz; not touched here.
- Windows is unaffected (WindowsBackend uses pyautogui directly).

## Dependencies on prior work

- The v23 `DesktopController` → `backend.input` routing (Phase A/B of the
  cross-platform wiring) is the prerequisite — without it, Wayland input in
  `LinuxStealthInput` would never be reached. That's done (commits in this phase).
