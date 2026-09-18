import pytest

from bwpdiy.render import render_card


def make_card(fixtures, type_, **kw):
    card = {
        "type": type_,
        "name": "测试卡",
        "description": "测试描述文本。",
        "_base_dir": str(fixtures),
        "artwork": {"images": [{"path": "sample_art.png"}]},
    }
    card.update(kw)
    return card


@pytest.mark.parametrize("kw", [
    {"type": "式神", "faction": "红莲", "power": 3, "health": 4},
    {"type": "战斗", "level": 1, "rarity": "R", "power+": 1, "shield+": 1},
    {"type": "法术", "level": 2, "rarity": "SR", "evolve": True},
    {"type": "形态", "level": 3, "rarity": "SSR", "power": 2, "health": 2},
    {"type": "幻境", "rarity": "N", "durability": 6},
    {"type": "协战", "rarity": "R"},
])
def test_render_all_types(assets_dir, sample_art, kw):
    card = make_card(sample_art.parent, kw.pop("type"), **kw)
    img = render_card(card, assets_dir)
    assert img.mode == "RGBA"
    w, h = img.size
    assert 0.5 < w / h < 0.7  # 竖版卡比例（裁剪后各类型尺寸略有差异）


def test_render_minimal_card(assets_dir, sample_art):
    # artwork 缺省 path → <name>.png
    card = {"type": "法术", "name": "sample_art", "_base_dir": str(sample_art.parent)}
    img = render_card(card, assets_dir)
    w, h = img.size
    assert 0.5 < w / h < 0.7


def test_render_missing_artwork_raises(assets_dir):
    card = {"type": "法术", "name": "不存在", "artwork": {"images": [{"path": "nope.png"}]}}
    with pytest.raises(FileNotFoundError):
        render_card(card, assets_dir)


def test_render_with_layout_override(assets_dir, sample_art):
    from bwpdiy.render.layout import load_layouts, get_type_layout
    layouts = load_layouts(assets_dir)
    tl = get_type_layout(layouts, "法术")
    tl["elements"]["rarity"]["pos"] = [256, 200]  # 上移稀有度双标（保持牌框内部，裁剪 bbox 不变）
    card = {"type": "法术", "name": "sample_art", "rarity": "R",
            "_base_dir": str(sample_art.parent)}
    default = render_card(card, assets_dir)
    moved = render_card(card, assets_dir, layout=tl)
    assert moved.mode == "RGBA"
    # 覆盖生效判别：稀有度双标移入牌框内部，裁剪 bbox 不变但像素必变
    assert moved.size == default.size
    assert list(moved.getdata()) != list(default.getdata())


def test_footer_rendered(assets_dir, sample_art):
    card = {"type": "战斗", "name": "sample_art", "shikigami": "测试式神",
            "level": 1, "rarity": "N", "_base_dir": str(sample_art.parent)}
    img = render_card(card, assets_dir)  # footer = "测试式神-战斗"，不炸即过
    assert img.mode == "RGBA"


def test_footer_with_special_type(assets_dir, sample_art):
    card = {"type": "法术", "name": "sample_art", "shikigami": "测试式神",
            "special_type": "惊雷", "level": 1, "rarity": "N",
            "_base_dir": str(sample_art.parent)}
    img = render_card(card, assets_dir)  # footer = "测试式神-法术/惊雷"，不炸即过
    assert img.mode == "RGBA"


def test_crop_tightest_alpha_bbox(assets_dir, sample_art):
    """导出裁剪 = 整卡合成结果的 tightest alpha bbox：小于 512×512，且探出框缘的
    元素（如左上角探出的等级标）包含在内（bbox 宽于框体自身）。"""
    card = make_card(sample_art.parent, "战斗", **{"level": 1, "rarity": "R", "power+": 1, "shield+": 1})
    full = render_card(card, assets_dir, crop=False)
    bbox = full.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    expected = full.crop(bbox)
    out = render_card(card, assets_dir, crop=True)
    assert out.size == expected.size
    assert out.size[0] < 512 and out.size[1] <= 512
    assert list(out.getdata()) == list(expected.getdata())
    # 探出元素包含：合成 bbox 比框体 alpha bbox 更宽（等级标探出左缘）
    from bwpdiy.render.assets import AssetLibrary
    frame = AssetLibrary(assets_dir).frame("combat", "norm")
    fbbox = frame.getchannel("A").getbbox()
    assert bbox[0] < fbbox[0]  # 左缘探出（等级标）
    assert bbox[2] - bbox[0] >= fbbox[2] - fbbox[0]


@pytest.mark.parametrize("card_type", ["式神", "战斗", "法术", "形态", "幻境", "协战"])
@pytest.mark.parametrize("variant", ["norm", "black"])
def test_render_frame_variants_smoke(assets_dir, sample_art, card_type, variant):
    """四框品冒烟：每类型 × norm/black（协战恒 norm，variant 字段被忽略）。"""
    card = make_card(sample_art.parent, card_type, **{
        "level": 2, "rarity": "SR", "faction": "红莲", "power": 3, "health": 4,
        "power+": 1, "health+": 1, "shield+": -1, "durability": 5, "evolve": True,
        "frame_variant": variant,
        "description": "框品冒烟测试描述文本。"})
    img = render_card(card, assets_dir)
    assert img.mode == "RGBA" and img.size[0] > 0


def test_frame_variant_changes_pixels(assets_dir, sample_art):
    """frame_variant 生效：同卡 black 与 norm 渲染像素不同。"""
    card = make_card(sample_art.parent, "法术", **{"level": 1, "rarity": "R",
                                                  "description": "框品对比。"})
    norm = render_card(card, assets_dir)
    black = render_card(dict(card, frame_variant="black"), assets_dir)
    assert list(norm.getdata()) != list(black.getdata())


def test_desc_avoids_stat_obstacles(assets_dir, sample_art):
    # 左右下有数值贴图的战斗牌 + 长描述：排版须避让（不炸且出图）
    card = {"type": "战斗", "name": "sample_art", "shikigami": "测试式神",
            "level": 1, "rarity": "N", "power+": 2, "shield+": -1,
            "description": "这是一段相当长的描述文本，用来验证末端行避开数值贴图的排版行为是否正常工作。" * 2,
            "_base_dir": str(sample_art.parent)}
    img = render_card(card, assets_dir)
    assert img.mode == "RGBA"


def test_desc_ink_keeps_gap_from_stat_ink(assets_dir, sample_art):
    """端到端：描述墨迹与 stat 角标真实墨迹（图标+数字）相距 ≥ obstacle_gap（缺省 4）。"""
    from pathlib import Path

    from PIL import Image, ImageChops, ImageFilter

    from bwpdiy.render.assets import AssetLibrary
    from bwpdiy.render.badges import render_element, stat_rendered
    from bwpdiy.render.layout import get_type_layout, load_layouts

    card = {"type": "战斗", "name": "sample_art", "shikigami": "测试式神",
            "level": 1, "rarity": "N", "power+": 2, "shield+": -1,
            "description": "这是一段相当长的描述文本，用来验证末端行避开数值贴图的排版行为是否正常工作。" * 2,
            "_base_dir": str(sample_art.parent)}
    tl = get_type_layout(load_layouts(Path(assets_dir)), "战斗")
    gap = tl["text_regions"]["desc"].get("obstacle_gap", 4)

    # 描述墨迹 = 有/无描述两版渲染的 RGB 差分（文本画在不透明卡面上，差 alpha 无意义）
    with_desc = render_card(card, assets_dir, crop=False)
    without_desc = render_card(dict(card, description=""), assets_dir, crop=False)
    diff = ImageChops.difference(with_desc.convert("RGB"), without_desc.convert("RGB"))
    text_ink = diff.convert("L").point(lambda v: 255 if v > 10 else 0)

    # 角标墨迹 = 与管线同口径：stat_rendered 元素在透明层渲染取 alpha
    lib = AssetLibrary(assets_dir)
    layer = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    i = 0
    for e in tl["elements"].values():
        if e["kind"] == "stat" and e.get("enabled", True) and stat_rendered(e, card):
            layer = render_element(layer, lib, f"stat_{i}", e, card, {"name_width": 0})
            i += 1
    assert i > 0
    stat_ink = layer.getchannel("A").point(lambda v: 255 if v > 10 else 0)
    # 角标墨迹外扩 gap-1 px 后与描述墨迹零重叠 ⇔ 两者距离 ≥ gap
    dilated = stat_ink.filter(ImageFilter.MaxFilter(2 * gap - 1))
    assert ImageChops.darker(text_ink, dilated).getbbox() is None
