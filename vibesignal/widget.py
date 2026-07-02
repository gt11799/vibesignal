"""Always-on-top floating panel (Tkinter, standard library) over the store.

A small borderless window that stays on top and shows one row per active
session, blocked first, refreshed about once a second. It is the desktop-GUI
sibling of panel.py (the terminal table) and the future physical light: all
three read the same store through resolve_per_session(), so this adds a
renderer without touching the hook layer.

Run with:
  Windows:        pythonw -m vibesignal widget    (no console window)
  macOS / Linux:  vibesignal widget &        (background the GUI)

Drag by the header; right-click to quit. On macOS, Control-click works too
because some Tk builds report the right mouse button as Button-2 rather than
Button-3, and Control-click is the historical single-button right-click chord.
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
import tkinter.font as tkfont

from . import resolve
from .panel import _fmt_age

# --- Codex rate-limit footer (managed by vibesignal-restyle) ---
import json
import os
import threading
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

_CODEX_USAGE_URL = "https://chatgpt.com/backend-api/codex/usage"


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or "~/.codex").expanduser()


def _codex_access_token() -> str | None:
    try:
        data = json.loads((_codex_home() / "auth.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    token = ((data.get("tokens") or {}).get("access_token")
             if isinstance(data, dict) else None)
    return token if isinstance(token, str) and token else None


def _codex_usage_json():
    token = _codex_access_token()
    if not token:
        return None
    req = urllib.request.Request(
        _CODEX_USAGE_URL,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": "vibesignal",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _codex_session_usage_json():
    sessions = _codex_home() / "sessions"
    try:
        paths = sorted(
            sessions.glob("**/*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:12]
    except Exception:
        return None
    for path in paths:
        try:
            with path.open(encoding="utf-8", errors="replace") as fh:
                lines = deque(fh, maxlen=2000)
        except Exception:
            continue
        for line in reversed(lines):
            try:
                event = json.loads(line)
            except Exception:
                continue
            payload = event.get("payload") if isinstance(event, dict) else None
            rate = event.get("rate_limits") or (
                payload.get("rate_limits") if isinstance(payload, dict) else None
            )
            if isinstance(rate, dict):
                return {"rate_limit": rate}
    return None


def _num(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(data: dict, *keys: str):
    for key in keys:
        if key in data:
            return data[key]
    return None


def _reset_seconds(window: dict) -> float | None:
    direct = _num(_first_present(window, "reset_after_seconds", "resetAfterSeconds"))
    if direct is not None:
        return direct
    reset_at = _first_present(window, "reset_at", "resets_at", "resetsAt")
    epoch = _num(reset_at)
    if epoch is not None:
        return epoch - time.time()
    if isinstance(reset_at, str):
        try:
            reset_at = reset_at.replace("Z", "+00:00")
            return (datetime.fromisoformat(reset_at) - datetime.now(timezone.utc)).total_seconds()
        except ValueError:
            return None
    return None


def _fmt_reset_seconds(secs):
    secs = _num(secs)
    if secs is None or secs <= 0:
        return ""
    m = int(secs // 60)
    if m >= 2880:
        return f" ({m // 1440}d{(m % 1440) // 60:02d}h)"
    return f" ({m // 60}h{m % 60:02d}m)"


def _remaining_percent(window: dict) -> float | None:
    remaining = _num(_first_present(window, "remaining_percent", "remainingPercent"))
    if remaining is not None:
        return max(0, min(100, remaining))
    used = _num(_first_present(window, "used_percent", "usedPercent"))
    if used is None:
        return None
    return max(0, min(100, 100 - used))


def _format_codex_window(label: str, window: dict) -> str | None:
    if not isinstance(window, dict):
        return None
    remaining = _remaining_percent(window)
    if remaining is None:
        return None
    reset = _fmt_reset_seconds(_reset_seconds(window))
    return f"{label} {remaining:.0f}%{reset}"


def _format_codex_usage(data: dict | None) -> str:
    if not isinstance(data, dict):
        return ""
    rate = data.get("rate_limit") or data.get("rateLimit") or {}
    if not isinstance(rate, dict):
        return ""
    parts = []
    for key, camel, direct, label in (("primary_window", "primaryWindow", "primary", "5h"),
                                      ("secondary_window", "secondaryWindow", "secondary", "wk")):
        window = _first_present(rate, key, camel, direct)
        part = _format_codex_window(label, window)
        if part:
            parts.append(part)
    return " · ".join(parts)


def _fetch_usage():
    try:
        text = _format_codex_usage(_codex_usage_json())
        if text:
            return text
    except Exception:
        pass
    try:
        return _format_codex_usage(_codex_session_usage_json())
    except Exception:
        return ""


def _font_family() -> str:
    """Per-platform UI font family.

    Tk silently substitutes when a family is missing, but the substitute is
    often a poor visual match (Times on macOS, Courier on bare X). Naming the
    platform-native family up front keeps the panel legible without forcing a
    runtime font-list scan.
    """
    if sys.platform == "darwin":
        return "Helvetica Neue"  # ships with every macOS; SF Pro is unreliable via Tk
    if sys.platform == "win32":
        return "Segoe UI"
    return "DejaVu Sans"

# Soft light theme. A left accent bar per row carries the state color.
HEX = {
    "blocked": "#ef4444",  # red (needs you now)
    "done": "#60a5fa",     # blue
    "working": "#34d399",  # green
    "error": "#c084fc",    # violet (manual failure)
    "idle": "#6b7280",     # grey
}
_BORDER = "#020617"
_BG = "#111827"      # high-contrast dark card
_FG = "#ffffff"
_DIM = "#d1d5db"
_DIMMER = "#c3cad5"
_RULE = "#4b5563"
_HEADER = "#ffffff"
_USAGE = "#f8fafc"

# When a session needs you, the whole panel goes red (violet for a manual error),
# not just one row, so a blocked session is unmissable across several windows. Other
# states keep the calm grey chrome.
_CALM = {"frame": _BORDER, "header_bg": _BG, "header_fg": _HEADER, "wash": _BG, "alarm": False}


def _palette(agg: str) -> dict:
    if agg == "blocked":
        return {"frame": "#ef4444", "header_bg": "#b91c1c", "header_fg": "#ffffff",
                "wash": "#2a1518", "alarm": True}
    if agg == "error":
        return {"frame": "#c084fc", "header_bg": "#7e22ce", "header_fg": "#ffffff",
                "wash": "#241631", "alarm": True}
    return _CALM


def glyph(state: str) -> str:
    """Filled dot for live states, hollow for idle (used in the header)."""
    return "○" if state == "idle" else "●"


def row_fields(row: dict, now: float):
    """Pure helper: (glyph, project, agent, state, age) display strings."""
    state = row.get("state", "idle")
    age = "—" if state == "working" else _fmt_age(now - row.get("ts", now))
    project = str(row.get("project") or "?")[:18]
    agent = str(row.get("agent") or "?")[:7]
    return glyph(state), project, agent, state, age


class Widget:
    def __init__(self, interval_ms: int = 1000):
        self.interval_ms = interval_ms
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        if sys.platform == "darwin":
            try:  # Tk 9 aqua ignores overrideredirect; force a borderless window
                self.root.tk.call("::tk::unsupported::MacWindowStyle",
                                  "style", self.root._w, "plain", "none")
            except tk.TclError:
                pass
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.95)
        except tk.TclError:
            pass
        try:  # custom Dock icon (managed by vibesignal-restyle)
            import os as _os
            from AppKit import NSApplication, NSImage
            _img = NSImage.alloc().initWithContentsOfFile_(
                _os.path.expanduser("~/.local/share/vibesignal/dock-icon.png"))
            if _img:
                NSApplication.sharedApplication().setApplicationIconImage_(_img)
        except Exception:
            pass
        # The root acts as a 1px border so the panel reads on a light desktop.
        self.root.configure(bg=_BORDER)
        self.card = tk.Frame(self.root, bg=_BG)
        self.card.pack(fill="both", expand=True, padx=1, pady=1)

        fam = _font_family()
        self._f_title = tkfont.Font(family=fam, size=11, weight="bold")
        self._f_proj = tkfont.Font(family=fam, size=11, weight="bold")
        self._f_dim = tkfont.Font(family=fam, size=10, weight="bold")
        self._f_usage = tkfont.Font(family=fam, size=10, weight="bold")
        self._f_dot = tkfont.Font(family=fam, size=12, weight="bold")

        self.header = tk.Frame(self.card, bg=_BG)
        self.header.pack(fill="x", padx=11, pady=(5, 4))
        self._agg_dot = tk.Label(self.header, text="●", bg=_BG, fg=_DIMMER, font=self._f_dot)
        self._agg_dot.pack(side="left")
        self._title = tk.Label(self.header, text=" vibesignal", bg=_BG, fg=_HEADER,
                               font=self._f_title)
        self._title.pack(side="left")
        self._count = tk.Label(self.header, text="", bg=_BG, fg=_DIMMER, font=self._f_dim)
        self._count.pack(side="right")

        self._rule = tk.Frame(self.card, bg=_RULE, height=1)
        self._rule.pack(fill="x", padx=11)

        self.body = tk.Frame(self.card, bg=_BG)
        self.body.pack(fill="both", expand=True, padx=(8, 12), pady=(6, 8))
        self.body.grid_columnconfigure(0, minsize=4)              # accent bar
        self.body.grid_columnconfigure(1, minsize=128, weight=1)  # project
        self.body.grid_columnconfigure(2, minsize=52)             # agent
        self.body.grid_columnconfigure(3, minsize=62)             # state
        self.body.grid_columnconfigure(4, minsize=46)             # age

        self._usage_text = ""
        self._footer_rule = tk.Frame(self.card, bg=_RULE, height=1)
        self._footer_rule.pack(fill="x", padx=11, pady=(0, 4))
        self.footer = tk.Frame(self.card, bg=_BG)
        self.footer.pack(fill="x", padx=11, pady=(0, 7))
        self._usage_lbl = tk.Label(self.footer, text="", bg=_BG, fg=_USAGE,
                                   font=self._f_usage, anchor="w")
        self._usage_lbl.pack(side="left")
        threading.Thread(target=self._usage_loop, daemon=True).start()

        for w in (
            self.root, self.card, self.header, self._agg_dot, self._title, self._count,
            self.footer, self._footer_rule, self._usage_lbl,
        ):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<Button-3>", self._menu)
            if sys.platform == "darwin":
                # Some macOS Tk builds report the right mouse button as Button-2,
                # and Control-click is the historical single-button right-click.
                # Binding both keeps the Quit menu reachable on every Mac setup.
                w.bind("<Button-2>", self._menu)
                w.bind("<Control-Button-1>", self._menu)

        self._cells: list[tk.Widget] = []
        self._drag = (0, 0)
        self._tick()
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.after(60, self._reposition)

    def _menu(self, event):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Quit panel", command=self.root.destroy)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _start_drag(self, event):
        self._drag = (event.x, event.y)

    def _on_drag(self, event):
        x = self.root.winfo_x() + (event.x - self._drag[0])
        y = self.root.winfo_y() + (event.y - self._drag[1])
        self.root.geometry(f"+{x}+{y}")

    def _usage_loop(self):
        while True:
            txt = _fetch_usage()
            if txt:
                self._usage_text = txt
            time.sleep(300)

    def _screen_workarea(self):
        """(left, top, right, bottom) of the desktop work area.

        Per-platform: Windows uses SystemParametersInfoW SPI_GETWORKAREA so the
        taskbar is excluded; macOS uses NSScreen.visibleFrame (via pyobjc, if
        installed) so the menu bar and Dock are excluded, falling back to a
        28/80 px heuristic when pyobjc is absent; other systems fall back to
        the full screen.
        """
        if sys.platform == "darwin":
            try:
                from AppKit import NSScreen  # pyobjc; best-effort
                screen = NSScreen.mainScreen()
                if screen is not None:
                    visible = screen.visibleFrame()
                    full = screen.frame()
                    # NSScreen uses bottom-left origin; Tk uses top-left. Flip Y
                    # against the screen's OWN top edge, not against full.size.height
                    # alone, so the math stays correct when mainScreen() resolves
                    # to a non-primary display (origin.y != 0 in a vertical
                    # multi-display layout).
                    screen_top = full.origin.y + full.size.height
                    left = int(visible.origin.x)
                    right = int(visible.origin.x + visible.size.width)
                    top = int(screen_top - (visible.origin.y + visible.size.height))
                    bottom = int(screen_top - visible.origin.y)
                    return left, top, right, bottom
            except Exception:
                pass
            # Heuristic without pyobjc: subtract the menu bar (~28) and a
            # bottom-Dock-sized strip (~80). Assumes a bottom Dock; a left or
            # right Dock will overlap the widget at the default x=14 origin.
            # Install pyobjc-framework-Cocoa for true Dock-aware placement.
            sh = self.root.winfo_screenheight()
            sw = self.root.winfo_screenwidth()
            return 0, 28, sw, sh - 80
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            # SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _reposition(self):
        self.root.update_idletasks()
        _left, top, right, _bottom = self._screen_workarea()
        width = self.root.winfo_width()
        self.root.geometry(f"+{right - width - 14}+{top + 12}")

    def _tick(self):
        rows = resolve.resolve_per_session()
        agg, _color = resolve.resolve_color()
        now = time.time()

        pal = _palette(agg)
        wash, hbg = pal["wash"], pal["header_bg"]

        # Whole-panel alarm: the frame and header go red (violet for error) and the
        # body is tinted, so a blocked session is visible without reading any row.
        self.root.configure(bg=pal["frame"])
        self.card.configure(bg=wash)
        self.card.pack_configure(padx=(3 if pal["alarm"] else 1),
                                 pady=(3 if pal["alarm"] else 1))
        self.body.configure(bg=wash)
        self.header.configure(bg=hbg)
        self._rule.configure(bg=(hbg if pal["alarm"] else _RULE))
        self._title.configure(bg=hbg, fg=pal["header_fg"])
        self._agg_dot.configure(bg=hbg, fg=("#ffffff" if pal["alarm"] else HEX.get(agg, _DIMMER)))
        self._count.configure(text=(f"{len(rows)}" if rows else ""), bg=hbg,
                              fg=("#ffffff" if pal["alarm"] else _DIMMER))
        self.footer.configure(bg=wash)
        self._footer_rule.configure(bg=("#ffffff" if pal["alarm"] else _RULE))
        self._usage_lbl.configure(text=self._usage_text, bg=wash,
                                  fg=("#ffffff" if pal["alarm"] else _USAGE))

        for w in self._cells:
            w.destroy()
        self._cells = []

        if not rows:
            lbl = tk.Label(self.body, text="no active sessions", bg=wash, fg=_DIM,
                           font=self._f_dim, anchor="w")
            lbl.grid(row=0, column=1, columnspan=4, sticky="w", pady=2)
            self._cells.append(lbl)
        else:
            for i, r in enumerate(rows):
                _g, project, agent, state, age = row_fields(r, now)
                color = HEX.get(state, _FG)
                bar = tk.Frame(self.body, bg=color)
                bar.grid(row=i, column=0, sticky="nsew", padx=(0, 9), pady=2)
                cells = [
                    bar,
                    tk.Label(self.body, text=project, bg=wash, fg=_FG, font=self._f_proj, anchor="w"),
                    tk.Label(self.body, text=agent, bg=wash, fg=_DIM, font=self._f_dim, anchor="w"),
                    tk.Label(self.body, text=state, bg=wash, fg=color, font=self._f_dim, anchor="w"),
                    tk.Label(self.body, text=age, bg=wash, fg=_DIMMER, font=self._f_dim, anchor="e"),
                ]
                cells[1].grid(row=i, column=1, sticky="w", pady=1)
                cells[2].grid(row=i, column=2, sticky="w", padx=(8, 0), pady=1)
                cells[3].grid(row=i, column=3, sticky="w", padx=(8, 0), pady=1)
                cells[4].grid(row=i, column=4, sticky="e", padx=(8, 0), pady=1)
                self._cells.extend(cells)

        self.root.after(self.interval_ms, self._tick)

    def run(self):
        self.root.mainloop()


def main(interval_ms: int = 1000) -> int:
    Widget(interval_ms=interval_ms).run()
    return 0


if __name__ == "__main__":
    main()
