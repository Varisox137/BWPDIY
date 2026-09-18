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
