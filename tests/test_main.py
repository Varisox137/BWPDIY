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
                        lambda app, host, port: calls.update(uvicorn=(host, port)))
    import bwpdiy.__main__ as m
    monkeypatch.setattr(m, "_probe_running", lambda host, port: None)  # 不打真实网络
    return calls


def _run(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["bwpdiy", *argv])
    assert main() == 0


def test_browser_autopen_default(fakes, monkeypatch):
    _run(monkeypatch, [])
    assert fakes["uvicorn"] == ("127.0.0.1", 8630)
    assert len(fakes["timers"]) == 1
    interval, func, args = fakes["timers"][0]
    assert 0 < interval <= 2  # 延迟约 1 秒，等服务就绪
    func(*args)
    assert fakes["browser"] == ["http://127.0.0.1:8630/"]


def test_browser_autopen_custom_host_port(fakes, monkeypatch):
    _run(monkeypatch, ["--host", "0.0.0.0", "--port", "8633"])
    assert fakes["uvicorn"] == ("0.0.0.0", 8633)
    _interval, func, args = fakes["timers"][0]
    func(*args)
    # 通配地址对浏览器无意义，回退回环地址；端口拼进 URL
    assert fakes["browser"] == ["http://127.0.0.1:8633/"]


def test_no_browser(fakes, monkeypatch):
    _run(monkeypatch, ["--no-browser"])
    assert fakes["uvicorn"] == ("127.0.0.1", 8630)
    assert fakes["timers"] == []
    assert fakes["browser"] == []


# ---------- 启动实例探测 ----------

def test_probe_same_version_reuses_instance(fakes, monkeypatch, capsys):
    """同版本已在运行：不起新服务，直接开浏览器复用，暂停等按键后返回 0。"""
    import bwpdiy.__main__ as m
    from bwpdiy import __version__
    paused = []
    monkeypatch.setattr(m, "_probe_running", lambda host, port: __version__)
    monkeypatch.setattr(m, "_pause_exit", lambda: paused.append(1))
    monkeypatch.setattr(sys, "argv", ["bwpdiy"])
    assert main() == 0
    assert fakes["uvicorn"] is None
    assert fakes["browser"] == ["http://127.0.0.1:8630/"]
    out = capsys.readouterr().out
    assert "已在运行" in out and f"BWPDIY v{__version__}" in out  # 启动先打印版本
    assert paused == [1]


def test_probe_old_version_refuses_start(fakes, monkeypatch, capsys):
    """异版本占用端口：拒绝启动并提示先保存再关闭旧程序，暂停等按键后返回 1。"""
    import bwpdiy.__main__ as m
    paused = []
    monkeypatch.setattr(m, "_probe_running", lambda host, port: "0.5.0")
    monkeypatch.setattr(m, "_pause_exit", lambda: paused.append(1))
    monkeypatch.setattr(sys, "argv", ["bwpdiy"])
    assert main() == 1
    assert fakes["uvicorn"] is None and fakes["browser"] == []
    assert "旧版本" in capsys.readouterr().err
    assert paused == [1]


def test_pause_exit_skipped_when_not_tty(monkeypatch):
    """非交互终端（测试/脚本/输出捕获）暂停直接跳过，不读 stdin。"""
    import bwpdiy.__main__ as m
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    m._pause_exit()  # 不挂起即通过


def test_probe_non_loopback_skipped(fakes, monkeypatch):
    """非回环监听不做实例探测。"""
    import bwpdiy.__main__ as m
    called = []
    monkeypatch.setattr(m, "_probe_running", lambda host, port: called.append(1) or "x")
    _run(monkeypatch, ["--host", "0.0.0.0", "--port", "8633"])
    assert called == []
