"""普通卡牌、对局小卡、头像的原生目标尺寸渲染。"""

import pytest
from PIL import Image

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.duo import render_portrait
from bwpdiy.render.entity import render_entity
from bwpdiy.render.layout import load_layouts
from bwpdiy.render.pipeline import render_card
from bwpdiy.render.size import fit_target_canvas, resolve_target_size


def _card(sample_art):
    return {"type": "式神", "name": "尺寸样卡", "power": 3, "health": 4,
            "description": "[[测试]]文本#ll。", "_base_dir": str(sample_art.parent),
            "artwork": {"images": [{"path": sample_art.name, "offset_x": 3,
                                     "offset_y": -2}]}}


def test_resolve_target_size_and_invalid_inputs():
    assert resolve_target_size((263, 512), None, None) is None
    assert resolve_target_size((263, 512), 526, None) == (526, 1024)
    assert resolve_target_size((263, 512), None, 1024) == (526, 1024)
    assert resolve_target_size((263, 512), 526, 1024) == (526, 1024)
    assert resolve_target_size((100, 100), 50, 51) == (50, 51)
    for width, height in ((100, 200), (0, None), (-1, None), (True, None),
                          (None, 1.5), (8193, None), (8192, 8192)):
        with pytest.raises(ValueError):
            resolve_target_size((263, 512), width, height)


def test_fit_target_canvas_only_crops_or_pads():
    image = Image.new("RGBA", (3, 3), "red")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Image.Image, "resize", lambda *_args: pytest.fail("不得重采样成品"))
        out = fit_target_canvas(image, (5, 2))
    assert out.size == (5, 2)
    assert out.getpixel((0, 0)) == (255, 0, 0, 255)
    assert out.getpixel((4, 1)) == (0, 0, 0, 0)


def test_card_native_size_and_default_pixel_compatibility(assets_dir, sample_art):
    card = _card(sample_art)
    base = render_card(card, assets_dir)
    same = render_card(card, assets_dir, width=base.width, height=base.height)
    assert same.tobytes() == base.tobytes()
    doubled = render_card(card, assets_dir, width=base.width * 2)
    by_height = render_card(card, assets_dir, height=base.height * 2)
    assert doubled.size == by_height.size == (base.width * 2, base.height * 2)
    with pytest.raises(ValueError, match="比例不一致"):
        render_card(card, assets_dir, width=base.width * 2, height=base.height)


def test_card_scales_artwork_and_font_natively(assets_dir, sample_art, monkeypatch):
    from bwpdiy.render import pipeline
    card = _card(sample_art)
    base = render_card(card, assets_dir)
    pipeline._STATIC_OVERLAY_CACHE.clear()
    fit_calls = []
    original_fit = pipeline.fit_artwork_cached
    monkeypatch.setattr(pipeline, "fit_artwork_cached",
                        lambda img, size, ox, oy, scale, cover_base=None:
                        fit_calls.append((size, ox, oy)) or original_fit(
                            img, size, ox, oy, scale, cover_base=cover_base))
    lib = pipeline.get_library(assets_dir)
    font_sizes = []
    original_font = lib.font
    monkeypatch.setattr(lib, "font", lambda kind, size:
                        font_sizes.append(size) or original_font(kind, size))
    render_card(card, assets_dir, width=base.width * 2)
    assert ((1024, 1024), 6, -4) in fit_calls
    name_size = load_layouts(assets_dir)["式神"]["elements"]["name"]["font_size"]
    assert name_size * 2 in font_sizes  # 字体按目标分辨率重新加载，而非放大位图


def test_card_native_size_scales_text_badges_and_signed_digits(
        assets_dir, sample_art, monkeypatch):
    """战斗牌多位带符号数字可绘制，文本与各类角标几何均按目标尺寸缩放。"""
    from bwpdiy.render import pipeline
    art = sample_art.resolve()
    layout = load_layouts(assets_dir)["战斗"]
    layout["elements"]["power"]["sign_offset"] = [3, 4]
    layout["elements"]["shield"]["fragile_sign_offset"] = [5, 6]
    card = {"type": "战斗", "name": "尺寸核验", "level": 1, "rarity": "R",
            "power+": 12, "shield+": -34, "description": "[[测试]]文本#ll。",
            "_base_dir": str(art.parent), "artwork": {"images": [{"path": art.name}]}}
    seen = []
    original = pipeline._draw_static

    def capture(canvas, type_layout, card, lib, variant):
        seen.append(type_layout)
        return original(canvas, type_layout, card, lib, variant)

    monkeypatch.setattr(pipeline, "_draw_static", capture)
    pipeline._STATIC_OVERLAY_CACHE.clear()
    base = render_card(card, assets_dir, layout)
    doubled = render_card(card, assets_dir, layout, width=base.width * 2)
    scaled = seen[-1]
    assert doubled.size == (base.width * 2, base.height * 2)
    region = scaled["text_regions"]["desc"]
    assert (region["width"], region["height"], region["center"][1]) == (500, 250, 836)
    assert region["font_range"] == [48, 24] and region["icon_scale"] == 0.9
    assert scaled["elements"]["name"]["font_size"] == 48
    assert scaled["elements"]["footer"]["font_size"] == 30
    assert scaled["elements"]["rarity"]["size"] == 44
    assert scaled["elements"]["rarity"]["gap"] == 180
    assert scaled["elements"]["level"]["base_size"] == 136
    assert scaled["elements"]["level"]["num_size"] == 96
    for key in ("icon_size", "font_size", "stroke_width", "sign_size_plus", "sign_size_minus"):
        assert scaled["elements"]["power"][key] == layout["elements"]["power"][key] * 2
    assert scaled["elements"]["power"]["num_offset"] == [-2, 4]
    assert scaled["elements"]["power"]["group_offset"] == [-2, 0]
    assert scaled["elements"]["power"]["sign_offset"] == [6, 8]
    assert scaled["elements"]["shield"]["fragile_icon_size"] == 140
    assert scaled["elements"]["shield"]["fragile_num_offset"] == [2, 4]
    assert scaled["elements"]["shield"]["fragile_sign_offset"] == [10, 12]


def test_entity_native_size_and_level_zero(assets_dir, sample_art):
    card = _card(sample_art)
    state = {"level": 0, "level_color": "yellow", "power": 12, "health": 34,
             "combat_power": 11, "shield": -22, "art_scale": 1}
    base = render_entity(card, state, assets_dir)
    same = render_entity(card, state, assets_dir, width=base.width, height=base.height)
    assert same.tobytes() == base.tobytes()
    doubled = render_entity(card, state, assets_dir, height=base.height * 2)
    assert doubled.size == (base.width * 2, base.height * 2)
    assert doubled.getpixel((doubled.width // 2, doubled.height - 2))[3] > 0
    assert doubled.getpixel((doubled.width - 2, doubled.height // 2))[3] > 0
    with pytest.raises(ValueError, match="比例不一致"):
        render_entity(card, state, assets_dir, width=base.width, height=base.height * 2)


def test_portrait_native_square_size_with_and_without_frame(assets_dir, sample_art):
    lib = AssetLibrary(assets_dir)
    elem = load_layouts(assets_dir)["协战"]["elements"]["duo_frame"]
    art = {"path": str(sample_art), "offset_x": 2, "offset_y": 3}
    for with_frame in (True, False):
        base = render_portrait(lib, elem, art, "红莲", with_frame=with_frame)
        same = render_portrait(lib, elem, art, "红莲", with_frame=with_frame,
                               width=base.width, height=base.height)
        assert same.tobytes() == base.tobytes()
        doubled = render_portrait(lib, elem, art, "红莲", with_frame=with_frame,
                                  width=base.width * 2, height=base.width * 2)
        assert doubled.size == (base.width * 2, base.height * 2)
    with pytest.raises(ValueError, match="比例不一致"):
        render_portrait(lib, elem, art, "红莲", width=200, height=100)
