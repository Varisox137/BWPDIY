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


def test_entity_native_size_and_level_zero(assets_dir, sample_art):
    card = _card(sample_art)
    state = {"level": 0, "level_color": "yellow", "power": 3, "health": 4,
             "combat_power": 1, "shield": -1, "art_scale": 1}
    base = render_entity(card, state, assets_dir)
    same = render_entity(card, state, assets_dir, width=base.width, height=base.height)
    assert same.tobytes() == base.tobytes()
    doubled = render_entity(card, state, assets_dir, height=base.height * 2)
    assert doubled.size == (base.width * 2, base.height * 2)
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
