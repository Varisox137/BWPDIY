from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def assets_dir() -> Path:
    return ASSETS


@pytest.fixture()
def sample_art() -> Path:
    return FIXTURES / "sample_art.png"
