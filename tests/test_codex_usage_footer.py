import importlib
import sys
import types


def _import_widget_without_tk(monkeypatch):
    fake_tk = types.ModuleType("tkinter")
    fake_tkfont = types.ModuleType("tkinter.font")
    fake_tk.TclError = RuntimeError
    monkeypatch.setitem(sys.modules, "tkinter", fake_tk)
    monkeypatch.setitem(sys.modules, "tkinter.font", fake_tkfont)
    sys.modules.pop("vibesignal.widget", None)
    return importlib.import_module("vibesignal.widget")


def test_codex_usage_footer_shows_remaining_percent_and_reset(monkeypatch):
    widget = _import_widget_without_tk(monkeypatch)
    data = {
        "rate_limit": {
            "primary_window": {
                "used_percent": 37,
                "limit_window_seconds": 18_000,
                "reset_after_seconds": 16_938,
            },
            "secondary_window": {
                "used_percent": 35,
                "limit_window_seconds": 604_800,
                "reset_after_seconds": 490_219,
            },
        }
    }

    assert widget._format_codex_usage(data) == "5h 63% (4h42m) · wk 65% (5d16h)"


def test_codex_usage_footer_accepts_remaining_percent(monkeypatch):
    widget = _import_widget_without_tk(monkeypatch)
    data = {
        "rate_limit": {
            "primary_window": {"remaining_percent": 91, "reset_after_seconds": 125},
            "secondary_window": {"remaining_percent": 74, "reset_after_seconds": 172_800},
        }
    }

    assert widget._format_codex_usage(data) == "5h 91% (0h02m) · wk 74% (2d00h)"


def test_fetch_usage_returns_empty_when_codex_usage_unavailable(monkeypatch, tmp_path):
    widget = _import_widget_without_tk(monkeypatch)

    def boom():
        raise OSError("offline")

    monkeypatch.setattr(widget, "_codex_usage_json", boom)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "empty-codex-home"))

    assert widget._fetch_usage() == ""


def test_fetch_usage_falls_back_to_codex_session_logs(monkeypatch, tmp_path):
    widget = _import_widget_without_tk(monkeypatch)
    codex_home = tmp_path / "codex"
    session_dir = codex_home / "sessions" / "2026" / "07" / "02"
    session_dir.mkdir(parents=True)
    (session_dir / "rollout.jsonl").write_text(
        '{"type":"event_msg","payload":{"type":"token_count",'
        '"rate_limits":{"primary":{"used_percent":46,"resets_at":1800000300},'
        '"secondary":{"used_percent":38,"resets_at":1800172800}}}}\n',
        encoding="utf-8",
    )

    def boom():
        raise OSError("offline")

    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setattr(widget, "_codex_usage_json", boom)
    monkeypatch.setattr(widget.time, "time", lambda: 1_800_000_000)

    assert widget._fetch_usage() == "5h 54% (0h05m) · wk 62% (2d00h)"
