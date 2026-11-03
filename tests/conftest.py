import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_layout_home(tmp_path, monkeypatch):
    from bwpdiy import resources

    home = tmp_path / "home"
    monkeypatch.setattr(resources.Path, "home", lambda: home)


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
    """布局写入逐用例隔离的 HOME，共享美术资源保持只读。"""
    return web_assets_copy


@pytest.fixture()
def sample_art() -> Path:
    return FIXTURES / "sample_art.png"
