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
    # 紧致导出：高≈512 顶格（框缘抗锯齿可差 1px）、宽按内容（无 512 画布留白），bbox 即全图
    assert 511 <= img.height <= 512 and img.width < 512
    assert _content_bbox(img) == (0, 0, img.width, img.height)
    assert 0.5 < img.width / img.height < 0.7  # 竖版卡比例


def test_render_minimal_card(assets_dir, sample_art):
    # artwork 缺省 path → <name>.png
    card = {"type": "法术", "name": "sample_art", "_base_dir": str(sample_art.parent)}
    img = render_card(card, assets_dir)
    assert 511 <= img.height <= 512 and img.width < 512
    assert _content_bbox(img) == (0, 0, img.width, img.height)
    assert 0.5 < img.width / img.height < 0.7


def test_render_missing_artwork_raises(assets_dir):
    card = {"type": "法术", "name": "不存在", "artwork": {"images": [{"path": "nope.png"}]}}
    with pytest.raises(FileNotFoundError):
        render_card(card, assets_dir)


def _anchor_x(assets_dir, card_type: str) -> int:
    """管线同款归一化牌框左缘锚点（卡面空间 x 原点）。"""
    from bwpdiy.render.assets import AssetLibrary
    from bwpdiy.render.badges import TYPE_FRAME_CODE
    from bwpdiy.render.pipeline import _normalize_frame
    info = {}
    _normalize_frame(AssetLibrary(assets_dir).frame(TYPE_FRAME_CODE[card_type], "norm"), info)
    return info["anchor"][0]


def test_render_with_layout_override(assets_dir, sample_art):
    from bwpdiy.render.layout import load_layouts, get_type_layout
    layouts = load_layouts(assets_dir)
    tl = get_type_layout(layouts, "法术")
    # 布局坐标为卡面空间（x 原点 = 归一化牌框左缘），原 512 画布值 256 相应平移
    tl["elements"]["rarity"]["pos"] = [256 - _anchor_x(assets_dir, "法术"), 200]
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
    from bwpdiy.render.assets import _LIBRARIES
    monkeypatch.setattr(aw, "ARTWORK_MAX_PIXELS", 10)
    _LIBRARIES.clear()  # 共享资源库会缓存上面已加载的卡图，清掉强制重载以触发校验
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


def test_export_tight_bbox_native_size(assets_dir, sample_art):
    """导出：按 tightest alpha bbox 裁剪后原尺寸直接返回——高 512 顶格、宽按内容，
    四边无留白（不再缩放贴回 512×512 画布）；info 回填裁剪原点（卡面空间，
    可为负）与 anchor_x（卡面空间原点的画布位置）。"""
    card = make_card(sample_art.parent, "战斗", **{"level": 1, "rarity": "R", "power+": 1, "shield+": 1})
    info = {}
    out = render_card(card, assets_dir, crop=True, info=info)
    assert 511 <= out.height <= 512 and out.width < 512  # 高顶格（框缘抗锯齿可差 1px）
    assert _content_bbox(out) == (0, 0, out.width, out.height)
    ox, oy = info["crop_origin"]
    ax = info["anchor_x"]
    # 画布空间原点 = 卡面空间原点 + anchor_x，须落在画布内（ox 本身可为负——探出框左缘元素）
    assert 0 <= ox + ax and oy >= 0
    assert ox + ax + out.width <= 512 and oy + out.height <= 512


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
    # 布局元素为卡面空间坐标，先平移到 512 画布坐标再手动渲染
    from bwpdiy.render.pipeline import OBSTACLE_ALPHA, _to_canvas_coords
    tl = _to_canvas_coords(tl, _anchor_x(assets_dir, "战斗"))
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


def test_to_canvas_coords_translation():
    """卡面空间 → 512 画布：仅平移绝对 x（pos/fragile_pos/center），
    偏移/尺寸类字段不动；返回深拷贝不改原数据。"""
    from bwpdiy.render.pipeline import _to_canvas_coords
    tl = {"elements": {
              "name": {"kind": "text", "pos": [132, 337], "font_size": 24},
              "shield": {"kind": "stat", "pos": [237, 485], "num_offset": [22, 0],
                         "fragile_pos": [240, 485], "fragile_num_offset": [22, 0]}},
          "text_regions": {
              "desc": {"center": [132, 430], "center_offset": [0, -3],
                       "width": 220, "height": 125}}}
    out = _to_canvas_coords(tl, 124)
    assert out["elements"]["name"]["pos"] == [256, 337]
    assert out["elements"]["shield"]["pos"] == [361, 485]
    assert out["elements"]["shield"]["fragile_pos"] == [364, 485]
    assert out["text_regions"]["desc"]["center"] == [256, 430]
    # 偏移/尺寸类字段不动
    assert out["elements"]["shield"]["num_offset"] == [22, 0]
    assert out["elements"]["shield"]["fragile_num_offset"] == [22, 0]
    assert out["text_regions"]["desc"]["center_offset"] == [0, -3]
    assert out["text_regions"]["desc"]["width"] == 220
    # 原数据未被修改
    assert tl["elements"]["name"]["pos"] == [132, 337]
    assert tl["text_regions"]["desc"]["center"] == [132, 430]


def test_shared_artwork_ref_and_loading(assets_dir, sample_art):
    """共享卡图入口保留缺省值、路径约束与旋转前 cover 基准尺寸。"""
    from bwpdiy.render.artwork import artwork_ref, load_card_artwork
    from bwpdiy.render.assets import get_library

    card = {"name": "sample_art", "_base_dir": str(sample_art.parent)}
    assert artwork_ref(card) == {
        "path": "sample_art.png", "offset_x": 0, "offset_y": 0,
        "scale": 1.0, "rotate": 0,
    }
    assert "artwork" not in card

    card["artwork"] = {"images": [{"path": sample_art.name, "rotate": 37}]}
    original, rotated = load_card_artwork(card, get_library(assets_dir))
    assert original == (1024, 1024)
    assert rotated.size != original

    card["artwork"]["images"][0]["path"] = "../outside.png"
    with pytest.raises(ValueError, match="越出基准目录"):
        load_card_artwork(card, get_library(assets_dir))


# ---------- 普通卡静态覆盖层缓存 ----------

def _render_card_reference(card, assets_dir, crop, layout=None):
    """缓存改造前的逐层合成顺序，作为逐像素独立参考。"""
    from PIL import Image, ImageChops

    from bwpdiy.render.artwork import artwork_ref, fit_artwork, load_card_artwork
    from bwpdiy.render.assets import get_library
    from bwpdiy.render.badges import TYPE_FRAME_CODE, render_element, stat_rendered
    from bwpdiy.render.layout import get_type_layout, load_layouts
    from bwpdiy.render.pipeline import (
        CARD_SIZE, FRAME_KEYWORD_FILL, FRAME_TEXT_FILL, OBSTACLE_ALPHA,
        _art_clip_contour, _normalize_frame, _to_canvas_coords, draw_region)

    card_type = card["type"]
    code = TYPE_FRAME_CODE[card_type]
    variant = "norm" if card_type == "协战" else card.get("frame_variant", "norm")
    lib = get_library(assets_dir)
    finfo = {}
    frame = _normalize_frame(lib.frame(code, variant), finfo)
    anchor_x = finfo["anchor"][0]
    ref = artwork_ref(card)
    orig_size, art = load_card_artwork(card, lib)
    art = fit_artwork(art, CARD_SIZE, ref["offset_x"], ref["offset_y"], ref["scale"],
                      cover_base=orig_size)
    art.putalpha(ImageChops.multiply(art.getchannel("A"), _art_clip_contour(frame)))
    canvas = Image.alpha_composite(art, frame)
    type_layout = layout if layout is not None else get_type_layout(
        load_layouts(assets_dir), card_type)
    type_layout = _to_canvas_coords(type_layout, anchor_x)
    elements = type_layout["elements"]
    card = dict(card)
    if not card.get("footer"):
        if card_type == "协战":
            s1, s2 = card.get("shikigami1"), card.get("shikigami2")
            card["footer"] = f"{s1}×{s2}-协战" if s1 and s2 else "协战"
        else:
            shikigami = card.get("shikigami") or (card["name"] if card_type == "式神" else None)
            card["footer"] = f"{shikigami}-{card_type}" if shikigami else card_type
            if card.get("special_type"):
                card["footer"] += f"/{card['special_type']}"
    name_width = 0
    name_elem = elements.get("name")
    if name_elem and name_elem.get("kind") == "text":
        name_font = lib.font(name_elem.get("font", "name"), name_elem["font_size"])
        name_width = name_font.getlength(card["name"])
    ctx = {"name_width": name_width}
    static = ("text", "rarity_flank")
    for elem_name, elem in elements.items():
        if elem["kind"] in static:
            canvas = render_element(canvas, lib, elem_name, elem, card, ctx)
    stat_elems = []
    for elem_name, elem in elements.items():
        if elem["kind"] in static:
            continue
        if elem["kind"] == "stat":
            stat_elems.append((elem_name, elem))
            canvas = render_element(canvas, lib, elem_name, elem, card, ctx,
                                    stat_part="icon")
        else:
            canvas = render_element(canvas, lib, elem_name, elem, card, ctx)
    regions = type_layout["text_regions"]
    if card.get("description") and "desc" in regions:
        rendered_stats = [e for _, e in stat_elems
                          if e.get("enabled", True) and stat_rendered(e, card)]
        obstacle_mask = None
        if rendered_stats:
            layer = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
            for i, elem in enumerate(rendered_stats):
                layer = render_element(layer, lib, f"stat_{i}", elem, card, ctx,
                                       composite=True)
            obstacle_mask = layer.getchannel("A").point(
                lambda value: 255 if value >= OBSTACLE_ALPHA else 0)
        desc_fill = FRAME_TEXT_FILL.get(variant, FRAME_TEXT_FILL["norm"])["desc"]
        kw_fill = FRAME_KEYWORD_FILL.get(variant, FRAME_KEYWORD_FILL["norm"])
        canvas = draw_region(canvas, lib, card["description"], regions["desc"],
                             obstacle_mask=obstacle_mask, fill=desc_fill,
                             keyword_fill=kw_fill, icon_variant=variant)
    for elem_name, elem in stat_elems:
        canvas = render_element(canvas, lib, elem_name, elem, card, ctx,
                                stat_part="number")
    if not crop:
        return canvas
    bbox = canvas.getchannel("A").point(lambda value: 255 if value > 10 else 0).getbbox()
    return canvas.crop(bbox) if bbox else canvas


@pytest.mark.parametrize("card_type", ["式神", "战斗", "法术", "形态", "幻境", "协战"])
@pytest.mark.parametrize("crop", [False, True])
def test_static_layer_replay_matches_legacy_pixels(
        assets_dir, sample_art, card_type, crop):
    import bwpdiy.render.pipeline as pipeline

    pipeline._STATIC_OVERLAY_CACHE.clear()
    card = make_card(sample_art.parent, card_type, **{
        "level": 2, "rarity": "SR", "faction": "红莲", "power": 3, "health": 4,
        "power+": 1, "health+": 1, "shield+": -1, "durability": 5,
        "evolve": True, "description": "旧算法[[关键字]]逐像素对照。#hl",
        "artwork": {"images": [{"path": "sample_art.png", "rotate": 17,
                                "offset_x": 9, "offset_y": -7, "scale": 1.1}]},
    })
    expected = _render_card_reference(card, assets_dir, crop)
    for _ in range(2):
        actual = render_card(card, assets_dir, crop=crop)
        assert actual.size == expected.size
        assert actual.tobytes() == expected.tobytes()


@pytest.mark.parametrize("crop", [False, True])
def test_static_text_replay_matches_legacy_on_transparent_target(
        assets_dir, tmp_path, crop):
    from PIL import Image

    from bwpdiy.render.layout import get_type_layout, load_layouts
    import bwpdiy.render.pipeline as pipeline

    Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(tmp_path / "blank.png")
    card = make_card(tmp_path, "法术", name="透明文本", description="",
                     artwork={"images": [{"path": "blank.png"}]})
    layout = get_type_layout(load_layouts(assets_dir), "法术")
    layout["elements"]["name"]["pos"] = [-90, 100]
    pipeline._STATIC_OVERLAY_CACHE.clear()
    expected = _render_card_reference(card, assets_dir, crop, layout)
    for _ in range(2):
        actual = render_card(card, assets_dir, layout=layout, crop=crop)
        assert actual.size == expected.size
        assert actual.tobytes() == expected.tobytes()


def _cached_card(sample_art, **kw):
    return make_card(sample_art.parent, "战斗", level=1, rarity="R",
                     **{"power+": 2, "shield+": 1}, **kw)


def _uncached_render(monkeypatch, card, assets_dir, **kw):
    import bwpdiy.render.pipeline as pipeline

    monkeypatch.setattr(pipeline, "STATIC_OVERLAY_CACHE_MAX_ENTRIES", 0)
    return render_card(card, assets_dir, **kw)


def test_static_overlay_reused_when_only_artwork_offset_changes(
        assets_dir, sample_art, monkeypatch):
    import bwpdiy.render.badges as badges
    import bwpdiy.render.pipeline as pipeline

    card = _cached_card(sample_art)
    moved = dict(card, artwork={"images": [{"path": "sample_art.png", "offset_x": 20}]})
    expected = _uncached_render(monkeypatch, card, assets_dir, crop=False)
    expected_moved = _uncached_render(monkeypatch, moved, assets_dir, crop=False)
    monkeypatch.setattr(pipeline, "STATIC_OVERLAY_CACHE_MAX_ENTRIES", 8)
    pipeline._STATIC_OVERLAY_CACHE.clear()
    original = badges._render_digits
    calls = []

    def counted(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(badges, "_render_digits", counted)
    actual = render_card(card, assets_dir, crop=False)
    first_calls = len(calls)
    actual_moved = render_card(moved, assets_dir, crop=False)
    assert first_calls > 0
    assert len(calls) == first_calls
    assert actual.tobytes() == expected.tobytes()
    assert actual_moved.tobytes() == expected_moved.tobytes()


@pytest.mark.parametrize("changes", [
    {"description": "修改后的描述。"},
    {"power+": 7},
    {"frame_variant": "black"},
])
def test_static_overlay_invalidated_by_card_content(
        assets_dir, sample_art, monkeypatch, changes):
    import bwpdiy.render.pipeline as pipeline

    pipeline._STATIC_OVERLAY_CACHE.clear()
    original = pipeline.render_element
    calls = []

    def counted(*args, **kwargs):
        calls.append(args[2])
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "render_element", counted)
    card = _cached_card(sample_art)
    render_card(card, assets_dir)
    first_calls = len(calls)
    render_card(dict(card, **changes), assets_dir)
    assert first_calls > 0
    assert len(calls) > first_calls


def test_static_overlay_invalidated_by_actual_layout(assets_dir, sample_art, monkeypatch):
    from bwpdiy.render.layout import get_type_layout, load_layouts
    import bwpdiy.render.pipeline as pipeline

    pipeline._STATIC_OVERLAY_CACHE.clear()
    original = pipeline.render_element
    calls = []

    def counted(*args, **kwargs):
        calls.append(args[2])
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "render_element", counted)
    card = _cached_card(sample_art)
    layout = get_type_layout(load_layouts(assets_dir), "战斗")
    render_card(card, assets_dir, layout=layout)
    first_calls = len(calls)
    layout["elements"]["name"]["font_size"] += 1
    render_card(card, assets_dir, layout=layout)
    assert len(calls) > first_calls


@pytest.mark.parametrize("internal", [
    {"_duo": [None, None]},
    {"_duo": object()},
    {"_preview": object()},
])
def test_static_overlay_bypasses_duo_and_unserializable_data(
        assets_dir, sample_art, monkeypatch, internal):
    import bwpdiy.render.badges as badges
    import bwpdiy.render.pipeline as pipeline

    pipeline._STATIC_OVERLAY_CACHE.clear()
    original = badges._render_digits
    calls = []

    def counted(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(badges, "_render_digits", counted)
    card = _cached_card(sample_art, **internal)
    expected = render_card(_cached_card(sample_art), assets_dir, crop=False)
    cached_entries = len(pipeline._STATIC_OVERLAY_CACHE)
    assert render_card(card, assets_dir, crop=False).tobytes() == expected.tobytes()
    first_calls = len(calls)
    assert render_card(card, assets_dir, crop=False).tobytes() == expected.tobytes()
    assert len(calls) > first_calls
    assert len(pipeline._STATIC_OVERLAY_CACHE) == cached_entries


def test_static_overlay_cache_is_bounded(assets_dir, sample_art, monkeypatch):
    import bwpdiy.render.pipeline as pipeline

    monkeypatch.setattr(pipeline, "STATIC_OVERLAY_CACHE_MAX_ENTRIES", 2)
    pipeline._STATIC_OVERLAY_CACHE.clear()
    for i in range(3):
        render_card(_cached_card(sample_art, name=f"测试卡{i}"), assets_dir)
    assert len(pipeline._STATIC_OVERLAY_CACHE) == 2


def test_static_overlay_drawing_runs_outside_lock(assets_dir, sample_art, monkeypatch):
    import threading
    import bwpdiy.render.pipeline as pipeline

    pipeline._STATIC_OVERLAY_CACHE.clear()

    class RecordingLock:
        def __init__(self):
            self.lock = threading.RLock()
            self.held = False

        def __enter__(self):
            self.lock.acquire()
            self.held = True

        def __exit__(self, *args):
            self.held = False
            self.lock.release()

    lock = RecordingLock()
    monkeypatch.setattr(pipeline, "_STATIC_OVERLAY_LOCK", lock)
    original = pipeline.render_element

    def checked(*args, **kwargs):
        assert not lock.held
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "render_element", checked)
    render_card(_cached_card(sample_art), assets_dir)
