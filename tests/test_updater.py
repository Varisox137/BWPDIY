"""自动更新测试：版本解析、latest release 检查（mock 网络）、web 端点分派。

不触真实网络：urlopen 一律 monkeypatch。
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bwpdiy import updater
from bwpdiy.web.app import create_app

ASSETS = Path(__file__).resolve().parent.parent / "assets"


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(ASSETS, library_dir=tmp_path / "library"))


class _FakeResp:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self, *args):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _release(tag, assets=None):
    return {"tag_name": tag, "assets": assets or [
        {"name": f"BWPDIY-{tag}.exe", "browser_download_url": "https://example.com/x.exe",
         "size": 30_000_000},
    ]}


# ---------- parse_version ----------

@pytest.mark.parametrize("tag,expected", [
    ("v1.2.3", (1, 2, 3)), ("1.2.3", (1, 2, 3)), ("v10.0.0", (10, 0, 0)),
])
def test_parse_version_valid(tag, expected):
    assert updater.parse_version(tag) == expected


@pytest.mark.parametrize("tag", ["", "v1.2", "v1.2.3.4", "abc", "v1.2.x"])
def test_parse_version_invalid(tag):
    assert updater.parse_version(tag) is None


# ---------- check_update ----------

def _mock_urlopen(monkeypatch, payload=None, exc=None):
    def fake(req, timeout=None):
        if exc:
            raise exc
        return _FakeResp(payload)
    monkeypatch.setattr(updater.urllib.request, "urlopen", fake)


def test_check_update_has_update(monkeypatch):
    _mock_urlopen(monkeypatch, _release("v99.0.0"))
    r = updater.check_update()
    assert r["has_update"] and r["latest"] == "v99.0.0"
    assert r["asset_name"] == "BWPDIY-v99.0.0.exe" and r["current"] == updater.__version__


def test_check_update_older_or_equal(monkeypatch):
    _mock_urlopen(monkeypatch, _release("v0.0.1"))
    assert updater.check_update()["has_update"] is False


def test_check_update_no_exe_asset(monkeypatch):
    _mock_urlopen(monkeypatch, _release("v99.0.0", assets=[{"name": "源码.zip"}]))
    r = updater.check_update()
    assert r["has_update"] is False and "资产" in r["error"]


def test_check_update_network_error_silent(monkeypatch):
    _mock_urlopen(monkeypatch, exc=OSError("离线"))
    r = updater.check_update()
    assert r["has_update"] is False and "离线" in r["error"]


def test_check_update_bad_tag(monkeypatch):
    _mock_urlopen(monkeypatch, _release("最新版"))
    assert updater.check_update()["has_update"] is False


# ---------- web 端点 ----------

def test_update_check_endpoint(client, monkeypatch):
    monkeypatch.setattr(updater, "check_update",
                        lambda: {"current": "1.0.0", "frozen": False, "has_update": False})
    r = client.get("/api/update/check")
    assert r.status_code == 200 and r.json()["has_update"] is False


def test_update_apply_no_update_422(client, monkeypatch):
    monkeypatch.setattr(updater, "check_update",
                        lambda: {"current": "1.0.0", "frozen": True, "has_update": False})
    r = client.post("/api/update/apply")
    assert r.status_code == 422


def test_update_apply_not_frozen_422(client, monkeypatch):
    monkeypatch.setattr(updater, "check_update", lambda: {
        "current": "1.0.0", "frozen": False, "has_update": True,
        "latest": "v9.9.9", "asset_name": "BWPDIY-v9.9.9.exe", "asset_url": "https://x/y.exe"})
    r = client.post("/api/update/apply")
    assert r.status_code == 422 and "开发模式" in r.json()["detail"]


def test_update_apply_success(client, monkeypatch):
    calls = []
    monkeypatch.setattr(updater, "check_update", lambda: {
        "current": "1.0.0", "frozen": True, "has_update": True,
        "latest": "v9.9.9", "asset_name": "BWPDIY-v9.9.9.exe", "asset_url": "https://x/y.exe"})
    monkeypatch.setattr(updater, "download_and_schedule_restart",
                        lambda info: calls.append(info) or info["latest"])
    r = client.post("/api/update/apply")
    assert r.status_code == 200 and r.json()["latest"] == "v9.9.9"
    assert len(calls) == 1  # 下载+重启编排被调用，URL 来自服务端自查而非前端


def test_update_apply_download_failure_422(client, monkeypatch):
    monkeypatch.setattr(updater, "check_update", lambda: {
        "current": "1.0.0", "frozen": True, "has_update": True,
        "latest": "v9.9.9", "asset_name": "BWPDIY-v9.9.9.exe", "asset_url": "https://x/y.exe"})
    def boom(info):
        raise ValueError("下载产物过小")
    monkeypatch.setattr(updater, "download_and_schedule_restart", boom)
    r = client.post("/api/update/apply")
    assert r.status_code == 422 and "更新失败" in r.json()["detail"]
