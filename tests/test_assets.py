import pytest
from PIL import Image, ImageFont

from bwpdiy.render.assets import AssetLibrary


def test_load_frame_and_mask(assets_dir):
    lib = AssetLibrary(assets_dir)
    frame = lib.frame("xt")
    assert frame.mode == "RGBA" and frame.size == (512, 512)
    mask = lib.mask("xt")
    assert mask.mode == "L" and mask.size == (512, 512)


def test_load_levels_and_rarity(assets_dir):
    lib = AssetLibrary(assets_dir)
    assert lib.level_base().mode == "RGBA"
    assert lib.level_star().mode == "RGBA"
    assert lib.level_num("brown", 2).mode == "RGBA"
    assert lib.rarity("SSR").mode == "RGBA"  # N.png 是 P 模式，必须 convert


def test_load_faction_and_icon(assets_dir):
    lib = AssetLibrary(assets_dir)
    assert lib.faction("red").mode == "RGBA"
    assert lib.icon("sm", "l").mode == "RGBA"


def test_load_fonts(assets_dir):
    lib = AssetLibrary(assets_dir)
    f = lib.font("name", 36)
    assert isinstance(f, ImageFont.FreeTypeFont) and f.size == 36
    assert lib.font("desc", 18).size == 18


def test_missing_resource_raises(assets_dir):
    lib = AssetLibrary(assets_dir)
    with pytest.raises(FileNotFoundError) as e:
        lib.frame("xx")
    assert "frame_xx_norm_low.png" in str(e.value)
