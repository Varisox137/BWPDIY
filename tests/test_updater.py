"""自动更新测试：版本解析、latest release 检查（mock 网络）、sha256 校验、web 端点分派。

不触真实网络：urlopen 一律 monkeypatch。
"""

import hashlib
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
    exe = f"BWPDIY-{tag}.exe"
    return {"tag_name": tag, "assets": assets or [
        {"name": exe, "browser_download_url": "https://example.com/x.exe",
         "size": 30_000_000},
        {"name": exe + ".sha256", "browser_download_url": "https://example.com/x.exe.sha256"},
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
    assert r["sha256_url"] == "https://example.com/x.exe.sha256"


def test_check_update_older_or_equal(monkeypatch):
    _mock_urlopen(monkeypatch, _release("v0.0.1"))
    assert updater.check_update()["has_update"] is False


def test_check_update_no_exe_asset(monkeypatch):
    _mock_urlopen(monkeypatch, _release("v99.0.0", assets=[{"name": "源码.zip"}]))
    r = updater.check_update()
    assert r["has_update"] is False and "资产" in r["error"]


def test_check_update_no_sha256_asset(monkeypatch):
    """缺 sha256 校验文件：安全校验不降级，视为无更新并报错说明。"""
    _mock_urlopen(monkeypatch, _release("v99.0.0", assets=[
        {"name": "BWPDIY-v99.0.0.exe", "browser_download_url": "https://example.com/x.exe"}]))
    r = updater.check_update()
    assert r["has_update"] is False and "sha256" in r["error"]


def test_check_update_network_error_silent(monkeypatch):
    _mock_urlopen(monkeypatch, exc=OSError("离线"))
    r = updater.check_update()
    assert r["has_update"] is False and "离线" in r["error"]


def test_check_update_bad_tag(monkeypatch):
    _mock_urlopen(monkeypatch, _release("最新版"))
    assert updater.check_update()["has_update"] is False


# ---------- sha256 下载校验 ----------

def test_verify_download_ok(tmp_path):
    """校验通过：sha256sum 格式（双空格分隔）匹配，文件保留。"""
    f = tmp_path / "BWPDIY-v9.9.9.exe"
    f.write_bytes(b"MZ" + b"0" * 1000)
    digest = hashlib.sha256(f.read_bytes()).hexdigest()
    updater._verify_download(f, f"{digest}  BWPDIY-v9.9.9.exe", "BWPDIY-v9.9.9.exe")
    assert f.is_file()


def test_verify_download_mismatch_deletes(tmp_path):
    """校验失败：hash 不匹配时报「下载校验失败」并删除已下载文件。"""
    f = tmp_path / "BWPDIY-v9.9.9.exe"
    f.write_bytes(b"MZ" + b"0" * 1000)
    with pytest.raises(ValueError, match="下载校验失败"):
        updater._verify_download(f, f"{'0' * 64}  BWPDIY-v9.9.9.exe", "BWPDIY-v9.9.9.exe")
    assert not f.exists()


@pytest.mark.parametrize("text", [
    "",
    "不是hash  BWPDIY-v9.9.9.exe",
    f"{'0' * 64}  别的文件.exe",  # 校验文件与 exe 资产不对应
])
def test_verify_download_bad_sha_file(tmp_path, text):
    f = tmp_path / "BWPDIY-v9.9.9.exe"
    f.write_bytes(b"MZ" + b"0" * 1000)
    with pytest.raises(ValueError):
        updater._verify_download(f, text, "BWPDIY-v9.9.9.exe")
    assert not f.exists()


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


# ---------- updater bat 与启动探测 ----------

def test_updater_bat_inplace_move(tmp_path):
    """回退模式（目录不可写/同名）：bat 为 move 覆盖 + 启动旧路径。"""
    from bwpdiy.updater import _write_updater_bat
    old = tmp_path / "旧版.exe"
    new = tmp_path / "新版.exe"
    bat = _write_updater_bat(old, new, inplace=True)
    body = bat.read_text(encoding="gbk")
    assert f'move /y "{new}" "{old}"' in body and f'start "" "{old}"' in body
    bat.unlink()


def test_updater_bat_side_by_side(tmp_path):
    """首选模式（同目录并存）：bat 为删旧（等待循环）+ 启动新版。"""
    from bwpdiy.updater import _write_updater_bat
    old = tmp_path / "BWPDIY-v1.2.0.exe"
    new = tmp_path / "BWPDIY-v1.2.1.exe"
    bat = _write_updater_bat(old, new, inplace=False)
    body = bat.read_text(encoding="gbk")
    assert f'del "{old}"' in body and f'start "" "{new}"' in body
    assert "move" not in body
    bat.unlink()


def _mock_probe(monkeypatch, payload=None, exc=None):
    from bwpdiy import __main__ as m
    class Resp:
        def read(self):
            return json.dumps(payload).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    def fake(url, timeout=None):
        if exc:
            raise exc
        return Resp()
    monkeypatch.setattr(m.urllib.request, "urlopen", fake)


def test_probe_running_bwpdiy(monkeypatch):
    from bwpdiy.__main__ import _probe_running
    _mock_probe(monkeypatch, {"version": "1.1.3"})
    assert _probe_running("127.0.0.1", 8630) == "1.1.3"


def test_probe_running_free_port(monkeypatch):
    from bwpdiy.__main__ import _probe_running
    _mock_probe(monkeypatch, exc=OSError("connection refused"))
    assert _probe_running("127.0.0.1", 8630) is None


def test_probe_running_foreign_service(monkeypatch):
    import urllib.error
    from bwpdiy.__main__ import _probe_running
    _mock_probe(monkeypatch, exc=urllib.error.HTTPError(
        "http://x", 404, "Not Found", None, None))
    assert _probe_running("127.0.0.1", 8630) == "?"
