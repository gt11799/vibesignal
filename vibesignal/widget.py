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

# --- ccusage usage footer (managed by vibesignal-restyle) ---
import json
import os
import subprocess
import threading
import urllib.request
from datetime import datetime, timezone

_CCUSAGE = "/opt/homebrew/bin/ccusage"


def _fmt_tok(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    if n >= 1e9:
        return f"{n / 1e9:.1f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}k"
    return str(int(n))


def _ccusage_json(*args):
    env = dict(os.environ)
    env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "/usr/bin:/bin")
    out = subprocess.run([_CCUSAGE, *args, "--json", "--offline"],
                         capture_output=True, text=True, timeout=120, env=env)
    if out.returncode != 0:
        return None
    return json.loads(out.stdout)


def _oauth_usage():
    """Official subscription utilization, via the Claude Code OAuth token in the keychain."""
    out = subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
        capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        return None
    token = json.loads(out.stdout.strip())["claudeAiOauth"]["accessToken"]
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={"Authorization": "Bearer " + token,
                 "anthropic-beta": "oauth-2025-04-20"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _fmt_reset(iso):
    try:
        secs = (datetime.fromisoformat(iso) - datetime.now(timezone.utc)).total_seconds()
    except Exception:
        return ""
    if secs <= 0:
        return ""
    m = int(secs // 60)
    if m >= 2880:
        return f" ({m // 1440}d{(m % 1440) // 60}h)"
    return f" ({m // 60}h{m % 60:02d}m)"


def _fetch_usage():
    parts = []
    try:
        u = _oauth_usage() or {}
        for key, label in (("five_hour", "5h"), ("seven_day", "wk")):
            w = u.get(key) or {}
            if w.get("utilization") is not None:
                parts.append(f"{label} {w['utilization']:.0f}%{_fmt_reset(w.get('resets_at') or '')}")
    except Exception:
        pass
    try:
        day = _ccusage_json("daily", "--since", time.strftime("%Y%m%d"))
        tot = (day or {}).get("totals") or {}
        if tot.get("totalCost"):
            parts.append(f"today ${tot['totalCost']:.1f}")
        if not any(p.startswith("5h") for p in parts):
            blk = _ccusage_json("blocks", "--active")
            for b in (blk or {}).get("blocks", []):
                if b.get("isActive"):
                    left = int((b.get("projection") or {}).get("remainingMinutes") or 0)
                    tail = f" ({left // 60}h{left % 60:02d}m)" if left else ""
                    parts.append(f"5h {_fmt_tok(b.get('totalTokens'))} ${b.get('costUSD', 0):.2f}{tail}")
    except Exception:
        pass
    return " · ".join(parts)


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
_BORDER = "#3a3f4b"
_BG = "#1f232a"      # dark card
_FG = "#e5e7eb"
_DIM = "#9ca3af"
_DIMMER = "#7b8290"
_RULE = "#343946"
_HEADER = "#e5e7eb"

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
            self.root.attributes("-alpha", 0.85)
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
        self._f_title = tkfont.Font(family=fam, size=9, weight="bold")
        self._f_proj = tkfont.Font(family=fam, size=9)
        self._f_dim = tkfont.Font(family=fam, size=8)
        self._f_dot = tkfont.Font(family=fam, size=10)

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
        self.body.pack(fill="both", expand=True, padx=(8, 12), pady=(5, 8))
        self.body.grid_columnconfigure(0, minsize=4)              # accent bar
        self.body.grid_columnconfigure(1, minsize=118, weight=1)  # project
        self.body.grid_columnconfigure(2, minsize=46)             # agent
        self.body.grid_columnconfigure(3, minsize=54)             # state
        self.body.grid_columnconfigure(4, minsize=40)             # age

        self._usage_text = ""
        self.footer = tk.Frame(self.card, bg=_BG)
        self.footer.pack(fill="x", padx=11, pady=(0, 6))
        self._usage_lbl = tk.Label(self.footer, text="", bg=_BG, fg=_DIMMER,
                                   font=self._f_dim, anchor="w")
        self._usage_lbl.pack(side="left")
        threading.Thread(target=self._usage_loop, daemon=True).start()

        for w in (self.root, self.card, self.header, self._agg_dot, self._title, self._count):
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
        self._usage_lbl.configure(text=self._usage_text, bg=wash,
                                  fg=("#ffffff" if pal["alarm"] else _DIMMER))

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
