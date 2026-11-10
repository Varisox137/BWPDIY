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


def test_evolve_circle_import_is_repeatable_and_preserves_registration(assets_dir, tmp_path):
    """圆盘重导入须确定且保留原画布；新版觉醒星不得再被旧 PSD 覆盖。"""
    from scripts.import_psd_assets import import_levels
    source = assets_dir / "psd_export/勾玉/底框-觉醒.png"
    with Image.open(source) as img:
        source_size = img.size
    import_levels(tmp_path)
    target = tmp_path / "evolve_circle.png"
    first = target.read_bytes()
    import_levels(tmp_path)
    assert target.read_bytes() == first
    with Image.open(target) as img:
        assert img.mode == "RGBA" and img.size == source_size
        assert img.getpixel((0, 0))[3] == 0
        assert img.getpixel((img.width // 2, img.height // 2))[3] > 0
    assert not (tmp_path / "evolve.png").exists()
    assert AssetLibrary(assets_dir).level_evolve_circle().mode == "RGBA"


def test_rarity_variant_fallback(assets_dir):
    """black 框品无专图：rarity(black) 回退 norm 底图；blue/red 用专图。"""
    lib = AssetLibrary(assets_dir)
    assert lib.rarity("SSR", "black") is lib.rarity("SSR")  # 缓存同对象：同一文件
    assert lib.rarity("SSR", "blue") is not lib.rarity("SSR")


def test_new_number_badge_and_reinforce_fallback(assets_dir):
    lib = AssetLibrary(assets_dir)
    assert lib.number("white", "0").size == (36, 64)
    assert lib.number("orange", "plus").mode == "RGBA"
    for status in ("bless", "eclipse", "bond", "curse", "radiance", "nightmare",
                   "eternal", "endless", "unused", "multi_status", "shown"):
        expected = 128 if status == "multi_status" else 64
        assert lib.badge(status).size == (expected, expected)
    assert lib.rarity("SR", "reinforce") is lib.rarity("SR")
    assert lib.icon("bounty").mode == "RGBA"


def test_load_stat_badge_and_sign(assets_dir):
    lib = AssetLibrary(assets_dir)
    assert lib.stat_badge("power").mode == "RGBA"
    assert lib.stat_badge("combat_fragile_2").mode == "RGBA"
    assert lib.stat_badge("intensity").mode == "RGBA"
    assert lib.sign("plus") is lib.number("white", "plus")
    assert lib.sign("minus") is lib.number("white", "minus")


def test_stats_dir_no_duplicate_assets(assets_dir):
    """stats/ 文件集合钉死：力量/生命全类型共用，不允许 form_/spell_/combat_ 前缀重复资源回归。"""
    files = sorted(p.name for p in (assets_dir / "stats").glob("*.png"))
    assert files == ["combat_fragile_1.png", "combat_fragile_2.png",
                     "combat_power.png", "countdown.png", "defeated_countdown.png",
                     "energy.png", "health.png", "intensity.png", "power.png",
                     "shield.png", "weak.png"]


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


# ---------- 用户卡图缓存（v1.2.1 旋转支持） ----------

def test_artwork_cache_by_path_rotate(tmp_path):
    """缓存键 = (路径, mtime, 旋转角)：同参复用同对象，异角/改文件各自重载。
    返回 (原图尺寸, 旋转后图)：原图尺寸供 fit_artwork 作 cover 基准。"""
    import os
    p = tmp_path / "图.png"
    Image.new("RGB", (100, 50), (200, 100, 50)).save(p)
    lib = AssetLibrary(tmp_path)
    a = lib.artwork(p)
    assert a[0] == (100, 50) and a[1].mode == "RGBA" and a[1].size == (100, 50)
    assert lib.artwork(p) is a                      # 同参命中缓存
    r = lib.artwork(p, 90)
    assert r is not a and r[0] == (100, 50) and r[1].size == (50, 100)  # 旋转扩展画布
    os.utime(p, (p.stat().st_mtime + 10, p.stat().st_mtime + 10))
    assert lib.artwork(p) is not a                  # mtime 变化重载


def test_artwork_pixel_limit(tmp_path, monkeypatch):
    """超像素上限的用户供图在加载缓存时拒绝（防解压炸弹口径）。"""
    from bwpdiy.render import artwork as aw
    big = tmp_path / "big.png"
    Image.new("RGB", (100, 100)).save(big)
    monkeypatch.setattr(aw, "ARTWORK_MAX_PIXELS", 99)  # artwork() 调用时才 import 该名，补丁生效
    with pytest.raises(ValueError, match="像素上限"):
        AssetLibrary(tmp_path).artwork(big)


def test_artwork_cache_cap(tmp_path):
    """卡图缓存设条目上限（v1.5.x）：滚轮旋转每档一个角度键，超限按插入序淘汰，
    防实时预览时大幅旋转图堆满内存；帧/字体等静态资源不受限。"""
    p = tmp_path / "图.png"
    Image.new("RGB", (30, 30)).save(p)
    lib = AssetLibrary(tmp_path)
    for angle in range(0, 360, 3):  # 远超上限的角度数
        lib.artwork(p, angle)
    art_keys = [k for k in lib._cache if k[0] == "artwork"]
    assert len(art_keys) == AssetLibrary.ARTWORK_CACHE_CAP
    assert lib.artwork(p, 0) is not None  # 淘汰后可重载，不报错


def test_get_library_shared(assets_dir):
    """get_library 按资源根目录共享实例（预览提速：帧/字体缓存跨渲染复用）。"""
    from bwpdiy.render.assets import get_library
    a = get_library(assets_dir)
    assert a is get_library(assets_dir)

