from functools import partial
from http.client import HTTPConnection
from io import BytesIO
from threading import Thread
from zipfile import ZipFile

from prototype.pyodide.server import (
    PROTOTYPE_DIR, PrototypeHandler, ThreadingHTTPServer, build_runtime_zip)


def test_runtime_zip_contains_renderer_and_real_assets():
    archive = ZipFile(BytesIO(build_runtime_zip()))
    names = set(archive.namelist())

    assert "bwpdiy/render/pipeline.py" in names
    assert "bwpdiy/render/default_layout.json" in names
    assert "bwpdiy/web/sample_art.png" in names
    assert "bridge.py" in names
    assert any(name.startswith("assets/fonts/") for name in names)
    assert any(name.startswith("assets/frames/") for name in names)
    assert not any(name.startswith("assets/ref/") for name in names)
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)


def test_static_server_only_exposes_prototype_directory():
    handler = partial(PrototypeHandler, directory=str(PROTOTYPE_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/README.md")
        assert connection.getresponse().status == 404
        connection.request("GET", "/prototype/pyodide/")
        response = connection.getresponse()
        assert response.status == 200
        assert b"Pyodide" in response.read()
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
