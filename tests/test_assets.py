import pytest
from PIL import Image, ImageFont

from bwpdiy.render.assets import AssetLibrary


def test_load_frame(assets_dir):
    lib = AssetLibrary(assets_dir)
    for code in ("form", "combat", "spell", "field", "reinforce"):
        frame = lib.frame(code)
        assert frame.mode == "RGBA" and frame.size == (512, 512)
    for variant in ("blue", "red", "black"):
        assert lib.frame("combat", variant).size == (512, 512)


def test_load_levels_and_rarity(assets_dir):
    lib = AssetLibrary(assets_dir)
    assert lib.level_base().mode == "RGBA"
    assert lib.level_star().mode == "RGBA"
    assert lib.level_num(2).mode == "RGBA"
    assert lib.rarity("SSR").mode == "RGBA"  # N.png 是 P 模式，必须 convert
    assert lib.rarity("N").mode == "RGBA"


def test_rarity_variant_fallback(assets_dir):
    """black 框品无专图：rarity(black) 回退 norm 底图；blue/red 用专图。"""
    lib = AssetLibrary(assets_dir)
    assert lib.rarity("SSR", "black") is lib.rarity("SSR")  # 缓存同对象：同一文件
    assert lib.rarity("SSR", "blue") is not lib.rarity("SSR")


def test_rarity_reinforce(assets_dir):
    """协战稀有度花标用 reinforce 专版（蓝/紫/金）。"""
    lib = AssetLibrary(assets_dir)
    mark = lib.rarity("SR", "reinforce")
    assert mark.mode == "RGBA"
    assert mark is lib.rarity("SR", "reinforce")
    assert mark is not lib.rarity("SR")


def test_load_stat_badge_and_sign(assets_dir):
    lib = AssetLibrary(assets_dir)
    assert lib.stat_badge("combat", "power").mode == "RGBA"
    assert lib.stat_badge("combat", "fragile_2").mode == "RGBA"
    assert lib.stat_badge("field", "intensity").mode == "RGBA"
    assert lib.sign("plus").mode == "RGBA"
    assert lib.sign("minus").mode == "RGBA"


def test_load_faction_and_icon(assets_dir):
    lib = AssetLibrary(assets_dir)
    assert lib.faction("red").mode == "RGBA"
    assert lib.icon("power").mode == "RGBA"


def test_load_fonts(assets_dir):
    lib = AssetLibrary(assets_dir)
    f = lib.font("name", 36)
    assert isinstance(f, ImageFont.FreeTypeFont) and f.size == 36
    assert lib.font("desc", 18).size == 18


def test_missing_resource_raises(assets_dir):
    lib = AssetLibrary(assets_dir)
    with pytest.raises(FileNotFoundError) as e:
        lib.frame("xx")
    assert "xx_norm.png" in str(e.value)
    with pytest.raises(FileNotFoundError):
        lib.stat_badge("xx", "power")
    with pytest.raises(FileNotFoundError):
        lib.sign("tilde")
