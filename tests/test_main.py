"""bwpdiy/__main__.py 启动行为测试：浏览器自启 URL 拼接与 --no-browser 开关。

uvicorn.run / webbrowser.open / threading.Timer 全部打桩，不起真实服务、不开浏览器。
"""

import sys
import threading
import webbrowser

import pytest

from bwpdiy.__main__ import main


@pytest.fixture()
def fakes(monkeypatch):
    calls = {"uvicorn": None, "browser": [], "timers": []}

    class FakeTimer:
        def __init__(self, interval, func, args=()):
            calls["timers"].append((interval, func, args))
            self.daemon = False

        def start(self):
            pass

    monkeypatch.setattr(threading, "Timer", FakeTimer)
    monkeypatch.setattr(webbrowser, "open", lambda url: calls["browser"].append(url))
    import uvicorn
    monkeypatch.setattr(uvicorn, "run",
                        lambda app, host, port, **kw: calls.update(uvicorn=(host, port)))
    from bwpdiy import runlog
    monkeypatch.setattr(runlog, "setup_run_logging", lambda: "test.log")  # 测试不落真实日志文件
    import atexit
    # main 退出清理注册在测试中不得生效：pytest 进程退出时会对真实 library/ 删图
    monkeypatch.setattr(atexit, "register", lambda fn: None)
    import bwpdiy.__main__ as m
    monkeypatch.setattr(m, "_probe_running", lambda host, port: None)  # 不打真实网络
    monkeypatch.setattr(m, "_port_owner_pid", lambda port: None)
    return calls


def _run(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["bwpdiy", *argv])
    assert main() == 0


def test_browser_autopen_default(fakes, monkeypatch):
    _run(monkeypatch, [])
    assert fakes["uvicorn"] == ("127.0.0.1", 8631)
    assert len(fakes["timers"]) == 1
    interval, func, args = fakes["timers"][0]
    assert 0 < interval <= 2  # 延迟约 1 秒，等服务就绪
    func(*args)
    assert fakes["browser"] == ["http://127.0.0.1:8631/"]


def test_version_line_has_blank_line_after(fakes, monkeypatch, capsys):
    from bwpdiy import __version__
    _run(monkeypatch, [])
    assert capsys.readouterr().out.startswith(f"BWPDIY v{__version__}\n\n")


def test_frozen_default_port(fakes, monkeypatch):
    from pathlib import Path
    from bwpdiy import resources
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(Path.cwd()), raising=False)
    monkeypatch.setattr(resources, "default_library_dir", lambda: Path("library"))
    _run(monkeypatch, [])
    assert fakes["uvicorn"] == ("127.0.0.1", 8630)


def test_browser_autopen_custom_host_port(fakes, monkeypatch):
    _run(monkeypatch, ["--host", "0.0.0.0", "--port", "8633"])
    assert fakes["uvicorn"] == ("0.0.0.0", 8633)
    _interval, func, args = fakes["timers"][0]
    func(*args)
    # 通配地址对浏览器无意义，回退回环地址；端口拼进 URL
    assert fakes["browser"] == ["http://127.0.0.1:8633/"]


def test_no_browser(fakes, monkeypatch):
    _run(monkeypatch, ["--no-browser"])
    assert fakes["uvicorn"] == ("127.0.0.1", 8631)
    assert fakes["timers"] == []
    assert fakes["browser"] == []


# ---------- 启动实例探测 ----------

def test_occupied_port_requires_confirmation_then_starts(fakes, monkeypatch, capsys):
    """占用时回车确认才关闭对应 PID；同版本也不再直接复用。"""
    import bwpdiy.__main__ as m
    from bwpdiy import __version__
    killed = []
    monkeypatch.setattr(m, "_port_owner_pid", lambda port: 1234)
    monkeypatch.setattr(m, "_probe_running", lambda host, port: __version__)
    monkeypatch.setattr(m, "_confirm_replace_owner", lambda port, running, pid: True)
    monkeypatch.setattr(m, "_kill_and_wait", lambda pid, port: killed.append(pid) or True)
    monkeypatch.setattr(sys, "argv", ["bwpdiy"])
    assert main() == 0
    assert killed == [1234]
    assert fakes["uvicorn"] == ("127.0.0.1", 8631)
    assert f"BWPDIY v{__version__}" in capsys.readouterr().out


def test_occupied_port_non_tty_refuses_kill(fakes, monkeypatch, capsys):
    """非交互环境只告警退出，不关闭占用进程。"""
    import bwpdiy.__main__ as m
    monkeypatch.setattr(m, "_port_owner_pid", lambda port: 1234)
    monkeypatch.setattr(m, "_probe_running", lambda host, port: "0.5.0")
    monkeypatch.setattr(m, "_pause_exit", lambda: None)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sys, "argv", ["bwpdiy"])
    assert main() == 1
    assert fakes["uvicorn"] is None and fakes["browser"] == []
    err = capsys.readouterr().err
    assert "1234" in err and "非交互" in err and "BWPDIY v0.5.0" in err


def test_confirm_replace_owner_only_empty_enter(monkeypatch, capsys):
    import bwpdiy.__main__ as m
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    answers = iter(["取消", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert not m._confirm_replace_owner(8631, "?", 1234)
    assert capsys.readouterr().out == "\n\n"  # 回车交互前后各留一行
    assert m._confirm_replace_owner(8631, "?", 1234)


def test_pause_exit_skipped_when_not_tty(monkeypatch):
    """非交互终端（测试/脚本/输出捕获）暂停直接跳过，不读 stdin。"""
    import bwpdiy.__main__ as m
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    m._pause_exit()  # 不挂起即通过


def test_pause_exit_has_blank_lines(monkeypatch, capsys):
    import msvcrt
    import bwpdiy.__main__ as m
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(msvcrt, "getch", lambda: "x")
    m._pause_exit()
    assert capsys.readouterr().out == "\n按任意键退出……\n\n"


def test_probe_non_loopback_skipped(fakes, monkeypatch):
    """非回环监听不做实例探测。"""
    import bwpdiy.__main__ as m
    called = []
    monkeypatch.setattr(m, "_probe_running", lambda host, port: called.append(1) or "x")
    _run(monkeypatch, ["--host", "0.0.0.0", "--port", "8633"])
    assert called == []


def test_no_idle_stop_disables_watchdog(fakes, monkeypatch):
    """--no-idle-stop：create_app 收到 idle_timeout=0（关闭闲置看门狗）；缺省保持 7200。"""
    import bwpdiy.web.app as app_mod
    seen = []
    real = app_mod.create_app
    def spy(*a, **kw):
        seen.append(kw.get("idle_timeout", 7200.0))
        return real(*a, **kw)
    monkeypatch.setattr(app_mod, "create_app", spy)
    _run(monkeypatch, ["--no-idle-stop", "--no-browser"])
    _run(monkeypatch, ["--no-browser"])
    assert seen == [0, 7200.0]


def test_current_version_has_changelog():
    from bwpdiy import __version__
    from bwpdiy.changelog import CHANGELOG

    assert __version__ in CHANGELOG
    assert "1.6.3" not in CHANGELOG
