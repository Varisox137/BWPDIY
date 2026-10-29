import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def assets_dir() -> Path:
    return ASSETS


@pytest.fixture(scope="session")
def web_assets_copy(tmp_path_factory) -> Path:
    """Web 测试共享一份资源拷贝，避免逐用例复制约 54MB 美术资源。"""
    dst = tmp_path_factory.mktemp("web-assets") / "assets"
    shutil.copytree(ASSETS, dst)
    return dst


@pytest.fixture()
def web_assets_dir(web_assets_copy) -> Path:
    """逐用例恢复唯一可写的布局文件，其余美术资源保持只读共享。"""
    layout = web_assets_copy / "layout.json"
    backup = web_assets_copy / "layout.json.bak"
    before = layout.read_bytes()
    backup_before = backup.read_bytes() if backup.exists() else None
    yield web_assets_copy
    layout.write_bytes(before)
    if backup_before is None:
        backup.unlink(missing_ok=True)
    else:
        backup.write_bytes(backup_before)


@pytest.fixture()
def sample_art() -> Path:
    return FIXTURES / "sample_art.png"
