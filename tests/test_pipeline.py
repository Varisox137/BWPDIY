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


def _content_bbox(img):
    return img.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()


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
    assert img.size == (512, 512)  # 导出恒 512×512
    bbox = _content_bbox(img)
    assert bbox[1] == 0 and bbox[3] == 512  # 上下顶格
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    assert 0.5 < w / h < 0.7  # 竖版卡比例（左右留白）


def test_render_minimal_card(assets_dir, sample_art):
    # artwork 缺省 path → <name>.png
    card = {"type": "法术", "name": "sample_art", "_base_dir": str(sample_art.parent)}
    img = render_card(card, assets_dir)
    assert img.size == (512, 512)
    bbox = _content_bbox(img)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
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


def test_footer_assist_shikigami_pair(assets_dir, sample_art):
    """协战脚注兜底：shikigami1/shikigami2 齐备 → 「山风×薰-协战」；缺任一 → 「协战」。"""
    base = {"type": "协战", "name": "sample_art", "rarity": "R",
            "_base_dir": str(sample_art.parent)}
    both = dict(base, shikigami1="山风", shikigami2="薰")
    assert (list(render_card(both, assets_dir, crop=False).getdata())
            == list(render_card(dict(base, footer="山风×薰-协战"), assets_dir, crop=False).getdata()))
    for missing in (dict(base, shikigami1="山风"), dict(base, shikigami2="薰"), base):
        assert (list(render_card(missing, assets_dir, crop=False).getdata())
                == list(render_card(dict(base, footer="协战"), assets_dir, crop=False).getdata()))


def test_artwork_path_escape_rejected(assets_dir, sample_art, monkeypatch):
    """卡图路径必须位于基准目录内：目录外绝对路径/.. 越界 → ValueError；像素超限 → ValueError。"""
    card = {"type": "法术", "name": "sample_art", "level": 1, "rarity": "N",
            "_base_dir": str(sample_art.parent)}
    for bad in ("/etc/passwd.png", "../outside.png"):
        c = dict(card, artwork={"images": [{"path": bad}]})
        with pytest.raises(ValueError, match="越出基准目录"):
            render_card(c, assets_dir)
    # 基准目录内的绝对路径合法
    ok = dict(card, artwork={"images": [{"path": str(sample_art.resolve())}]})
    assert render_card(ok, assets_dir).mode == "RGBA"
    # 像素上限（monkeypatch 调低，避免真造大图；校验在 AssetLibrary.artwork 加载缓存时）
    import bwpdiy.render.artwork as aw
    monkeypatch.setattr(aw, "ARTWORK_MAX_PIXELS", 10)
    with pytest.raises(ValueError, match="超像素上限"):
        render_card(card, assets_dir)


def test_footer_neutral_card(assets_dir, sample_art):
    """中立牌（无所属式神）脚注兜底 = 类型[/子类型]，无「所属式神-」前缀；
    式神卡无所属式神字段时回退卡名。"""
    base = {"type": "战斗", "name": "sample_art", "level": 1, "rarity": "N",
            "_base_dir": str(sample_art.parent)}
    assert (list(render_card(base, assets_dir, crop=False).getdata())
            == list(render_card(dict(base, footer="战斗"), assets_dir, crop=False).getdata()))
    assert (list(render_card(dict(base, special_type="惊雷"), assets_dir, crop=False).getdata())
            == list(render_card(dict(base, footer="战斗/惊雷"), assets_dir, crop=False).getdata()))
    body = dict(base, type="式神", power=3, health=4)
    assert (list(render_card(body, assets_dir, crop=False).getdata())
            == list(render_card(dict(body, footer="sample_art-式神"), assets_dir, crop=False).getdata()))


def test_export_fit_512_top_bottom_flush(assets_dir, sample_art):
    """导出适配：恒 512×512，内容上下顶格、水平居中（左右留白对称）。"""
    card = make_card(sample_art.parent, "战斗", **{"level": 1, "rarity": "R", "power+": 1, "shield+": 1})
    out = render_card(card, assets_dir, crop=True)
    assert out.size == (512, 512)
    bbox = _content_bbox(out)
    assert bbox[1] == 0 and bbox[3] == 512  # 上下顶格
    assert abs(bbox[0] - (512 - bbox[2])) <= 1  # 水平居中


def test_artwork_clipped_to_eroded_contour(assets_dir, sample_art, tmp_path):
    """卡图轮廓预裁剪：卡图墨迹全部在「框 alpha≥128 实心区内缩 2px」轮廓内。

    框缘半透明带（轮廓外、框形内）之下没有卡图——与全透明卡图渲染对比，
    轮廓外区域两者必须逐像素一致（卡图零贡献）；轮廓内两者必不同（卡图在画）。
    """
    from PIL import Image, ImageChops

    from bwpdiy.render.assets import AssetLibrary
    from bwpdiy.render.pipeline import _art_clip_contour, _normalize_frame

    lib = AssetLibrary(assets_dir)
    # 全透明卡图对照组
    Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(tmp_path / "blank.png")
    card = make_card(sample_art.parent, "法术", footer=" ")
    blank_card = dict(card, _base_dir=str(tmp_path),
                      artwork={"images": [{"path": "blank.png"}]})
    for variant in ("norm", "black", "blue", "red"):
        kw = {"frame_variant": variant}
        # 合成到品红底再比 RGB（alpha=0 区域的 RGB 残留不参与比较）
        def on_bg(img):
            bg = Image.new("RGBA", img.size, (255, 0, 255, 255))
            bg.alpha_composite(img)
            return bg.convert("RGB")
        with_art = on_bg(render_card(dict(card, **kw), assets_dir, crop=False))
        without_art = on_bg(render_card(dict(blank_card, **kw), assets_dir, crop=False))
        diff = ImageChops.difference(with_art, without_art)
        diff = diff.convert("L").point(lambda v: 255 if v > 10 else 0)
        # 与管线同口径：轮廓基于归一化（512 画布）后的框
        contour = _art_clip_contour(_normalize_frame(lib.frame("spell", variant)))
        outside = contour.point(lambda v: 255 if v == 0 else 0)
        assert outside.getbbox() is not None  # 确实存在轮廓外区域（测试有效性）
        # 轮廓外卡图零贡献
        assert ImageChops.darker(diff, outside).getbbox() is None
        # 轮廓内卡图确实在画（对照有效性）
        assert ImageChops.darker(diff, contour).getbbox() is not None


def test_art_clip_contour_properties(assets_dir):
    """轮廓掩膜性质：包含框实心区（腐蚀单调性）、画布四边全为 0（框外排除）、非空。"""
    from bwpdiy.render.assets import AssetLibrary
    from bwpdiy.render.pipeline import (
        FRAME_CONTOUR_ALPHA, FRAME_CONTOUR_ERODE, _art_clip_contour, _normalize_frame)

    assert FRAME_CONTOUR_ALPHA == 128 and FRAME_CONTOUR_ERODE == 2
    lib = AssetLibrary(assets_dir)
    for frame_path in sorted((assets_dir / "frames").glob("*.png")):
        frame = _normalize_frame(lib.frame(frame_path.stem.rsplit("_", 1)[0],
                                           frame_path.stem.rsplit("_", 1)[1]))
        contour = _art_clip_contour(frame)
        assert contour.getbbox() is not None, frame_path.name
        # 画布左右两边（框外）全排除（竖版框上下顶格，顶/底边不强制）
        px = contour.load()
        assert not any(px[0, y] or px[511, y] for y in range(512)), frame_path.name
        # 外轮廓 ⊇ 实心区（卡图窗被纳入），腐蚀后仍 ⊇ 实心区腐蚀（单调性）
        from PIL import ImageChops, ImageFilter
        solid = frame.getchannel("A").point(
            lambda v: 255 if v >= FRAME_CONTOUR_ALPHA else 0)
        solid_eroded = solid.filter(ImageFilter.MinFilter(2 * FRAME_CONTOUR_ERODE + 1))
        assert ImageChops.subtract(solid_eroded, contour).getbbox() is None, frame_path.name


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
    """端到端：竖直贴邻（≤1px）的行之间，描述墨迹与 stat 角标碰撞轮廓
    （图标+数字，alpha≥128）横向相距 ≥ obstacle_gap（缺省 4）。"""
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

    # 角标墨迹 = 与管线同口径：stat_rendered 元素在透明层渲染，取 alpha≥128 碰撞轮廓
    from bwpdiy.render.pipeline import OBSTACLE_ALPHA
    lib = AssetLibrary(assets_dir)
    layer = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    i = 0
    for e in tl["elements"].values():
        if e["kind"] == "stat" and e.get("enabled", True) and stat_rendered(e, card):
            layer = render_element(layer, lib, f"stat_{i}", e, card, {"name_width": 0},
                                   composite=True)  # 与管线掩膜采集同口径
            i += 1
    assert i > 0
    stat_ink = layer.getchannel("A").point(lambda v: 255 if v >= OBSTACLE_ALPHA else 0)
    # 逐行验证：竖直距离 ≤1px 的行对之间，横向区间间距 ≥ gap
    from bwpdiy.render.geometry import mask_row_runs
    text_runs = mask_row_runs(text_ink)
    stat_runs = mask_row_runs(stat_ink)
    for y, truns in text_runs.items():
        for dy in (-1, 0, 1):
            for sx0, sx1 in stat_runs.get(y + dy, ()):
                for tx0, tx1 in truns:
                    assert tx1 + gap <= sx0 or sx1 + gap <= tx0


def test_artwork_rotate_changes_render(assets_dir, sample_art):
    """artwork rotate（v1.2.1）：绕中心旋转参与合成，输出与未旋转不同。"""
    base = render_card(make_card(sample_art.parent, "法术", level=1, rarity="R",
                                 evolve=True), assets_dir, crop=False)
    rotated = render_card(make_card(sample_art.parent, "法术", level=1, rarity="R",
                                    evolve=True, artwork={"images": [
                                        {"path": "sample_art.png", "rotate": 37}]}),
                          assets_dir, crop=False)
    assert list(base.getdata()) != list(rotated.getdata())
