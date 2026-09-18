import pytest
from PIL import Image, ImageFont

from bwpdiy.render.assets import AssetLibrary


def test_load_frame(assets_dir):
    lib = AssetLibrary(assets_dir)
    for code in ("form", "combat", "spell", "field", "reinforce"):
        frame = lib.frame(code)
        # 素材为手工修整的紧致裁剪图：RGBA、不超过 512 画布（居中贴回由管线负责）
        assert frame.mode == "RGBA"
        assert 0 < frame.width <= 512 and 0 < frame.height <= 512
    for variant in ("blue", "red", "black"):
        assert lib.frame("combat", variant).mode == "RGBA"


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
    assert lib.stat_badge("power").mode == "RGBA"
    assert lib.stat_badge("combat_fragile_2").mode == "RGBA"
    assert lib.stat_badge("field_intensity").mode == "RGBA"
    assert lib.sign("plus").mode == "RGBA"
    assert lib.sign("minus").mode == "RGBA"


def test_stats_dir_no_duplicate_assets(assets_dir):
    """stats/ 文件集合钉死：力量/生命全类型共用，不允许 form_/spell_/combat_ 前缀重复资源回归。"""
    files = sorted(p.name for p in (assets_dir / "stats").glob("*.png"))
    assert files == ["combat_fragile_1.png", "combat_fragile_2.png",
                     "combat_shield.png", "field_intensity.png",
                     "health.png", "power.png"]


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
        lib.stat_badge("xx")
    with pytest.raises(FileNotFoundError):
        lib.sign("tilde")
