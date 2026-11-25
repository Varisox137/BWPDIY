from functools import partial
from http.client import HTTPConnection
import json
from pathlib import Path
from threading import Thread
from urllib.parse import quote

import pytest

from prototype.pyodide.log_admin import OnlineLogService
from prototype.pyodide.server import PROTOTYPE_DIR, PrototypeHandler, PrototypeServer


def make_logs(tmp_path: Path):
    current = tmp_path / "bwpdiy-20261123-000000-123.log"
    current.write_bytes("当前日志\n第二行".encode("utf-8"))
    (tmp_path / "bwpdiy-launcher-20261123-000000-123.log").write_bytes(
        "启动日志".encode("utf-8"))
    (tmp_path / "not-log.txt").write_text("不可访问", encoding="utf-8")
    return current


def test_log_service_auth_listing_preview_and_filename_boundary(tmp_path):
    current = make_logs(tmp_path)
    service = OnlineLogService(tmp_path, current)
    try:
        assert len(service.token) == 16
        assert service.rotate_seconds == 600
        assert service.authenticate(f"Bearer {service.token}", "local")
        assert not service.authenticate("Bearer wrong", "local")
        logs = service.list_logs()
        assert {item["name"] for item in logs} == {
            current.name, "bwpdiy-launcher-20261123-000000-123.log"}
        assert next(item for item in logs if item["current"])["name"] == current.name
        assert service.preview(current.name) == ("当前日志\n第二行", False)
        assert service.log_path(current.name) == current
        for name in ("../secret", "not-log.txt", current.name + ".lnk"):
            with pytest.raises(ValueError):
                service.log_path(name)
        for _ in range(5):
            assert not service.authenticate("Bearer wrong", "throttled")
        assert not service.authenticate(f"Bearer {service.token}", "throttled")
    finally:
        service.close()


def test_log_admin_http_api_is_read_only_and_authenticated(tmp_path):
    current = make_logs(tmp_path)
    service = OnlineLogService(tmp_path, current)
    handler = partial(PrototypeHandler, directory=str(PROTOTYPE_DIR))
    server = PrototypeServer(("127.0.0.1", 0), handler, log_admin=service)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/log-admin/")
        response = connection.getresponse()
        assert response.status == 200
        assert "日志运维" in response.read().decode("utf-8")
        connection.request("GET", "/api/log-admin/logs")
        assert connection.getresponse().status == 401
        headers = {"Authorization": f"Bearer {service.token}"}
        connection.request("GET", "/api/log-admin/logs", headers=headers)
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Cache-Control") == "no-store"
        payload = json.loads(response.read().decode("utf-8"))
        assert len(payload["logs"]) == 2

        path = f"/api/log-admin/logs/{quote(current.name)}/preview"
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read().decode("utf-8"))["text"] == "当前日志\n第二行"

        path = f"/api/log-admin/logs/{quote(current.name)}/download"
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        assert response.status == 200
        assert "attachment" in response.getheader("Content-Disposition")
        assert response.read().decode("utf-8") == "当前日志\n第二行"

        connection.request("POST", "/api/log-admin/logs", headers=headers)
        assert connection.getresponse().status in (405, 501)
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        service.close()
