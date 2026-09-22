from PIL import Image

import pytest

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import STAT_COLORS, render_element


def canvas():
    return Image.new("RGBA", (512, 512), (0, 0, 0, 0))


def opaque(img):
    return sum(1 for p in img.getdata() if p[3] > 0)


def test_level_badge(assets_dir):
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "level_badge", "pos": [120, 65], "base_size": 72, "star_size": 60, "num_size": 40}
    img = render_element(canvas(), lib, "level", elem, {"level": 2, "evolve": True})
    assert img.getpixel((120, 65))[3] > 0
    # 无 level 字段：跳过
    assert render_element(canvas(), lib, "level", elem, {}) == canvas() or \
        opaque(render_element(canvas(), lib, "level", elem, {})) == 0


def test_level_badge_layer_offsets(assets_dir):
    """星标/勾玉偏移：相对底座 pos 位移生效（偏移层墨迹移出原位），缺省 [0,0] 不变。"""
    elem = {"kind": "level_badge", "pos": [120, 65], "base_size": 72,
            "star_size": 60, "num_size": 40}
    base = render_element(canvas(), AssetLibrary(assets_dir), "level",
                          elem, {"level": 2, "evolve": True})
    moved = render_element(canvas(), AssetLibrary(assets_dir), "level",
                           dict(elem, star_offset=[-20, -15], num_offset=[18, 12]),
                           {"level": 2, "evolve": True})
    assert list(base.getdata()) != list(moved.getdata())
    # 底座不动：底座圆盘左缘像素两版一致有墨迹
    assert base.getpixel((120 - 36 + 2, 65))[3] > 0
    assert moved.getpixel((120 - 36 + 2, 65))[3] > 0
    # 勾玉层右上移至 (138,77)：移动版该点有墨迹，原版同点相对墨迹更少（星/勾玉均不在此中心）
    assert moved.getpixel((138, 77))[3] > 0
    # 缺省偏移与显式 [0,0] 等价
    explicit = render_element(canvas(), AssetLibrary(assets_dir), "level",
                              dict(elem, star_offset=[0, 0], num_offset=[0, 0]),
                              {"level": 2, "evolve": True})
    assert list(base.getdata()) == list(explicit.getdata())


def _flank_elem():
    return {"kind": "rarity_flank", "pos": [256, 358], "gap": 32, "size": 24, "margin": 8}


def test_rarity_flank_short_name_static(assets_dir):
    """短名（name_width/2+margin <= gap）双标固定在 pos±gap，位置与卡名宽度无关。"""
    lib = AssetLibrary(assets_dir)
    elem = _flank_elem()
    no_name = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"}, {"name_width": 0})
    # 40/2+8=28 < 32：仍按默认半间距，逐像素一致
    short = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"}, {"name_width": 40})
    assert list(no_name.getdata()) == list(short.getdata())
    assert no_name.getpixel((256 - 32, 358))[3] > 0  # 左标中心 x=224
    assert no_name.getpixel((256 - 32 - 24, 358))[3] == 0  # 左标之左无墨迹
    # 无 rarity 字段：按默认 R 渲染
    default_r = render_element(canvas(), lib, "rarity", elem, {}, {"name_width": 0})
    assert opaque(default_r) > 0
    # margin 缺省回退 8
    no_margin = render_element(canvas(), lib, "rarity",
                               {"kind": "rarity_flank", "pos": [256, 358], "gap": 32, "size": 24},
                               {"rarity": "SSR"}, {"name_width": 0})
    assert list(no_margin.getdata()) == list(no_name.getdata())


def test_rarity_flank_long_name_moves(assets_dir):
    """长名（name_width/2+margin > gap）双标按与卡名缘固定 margin 外移。"""
    lib = AssetLibrary(assets_dir)
    elem = _flank_elem()
    # 120/2+8=68 > 32：右标中心 x=256+68(+1)
    wide = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"}, {"name_width": 120})
    assert wide.getpixel((256 + 68, 358))[3] > 0
    assert wide.getpixel((256 + 68 + 24, 358))[3] == 0
    short = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"}, {"name_width": 0})
    assert short.getpixel((256 + 68, 358))[3] == 0


def test_rarity_flank_mirror_symmetric(assets_dir):
    """长短名下双标均关于 cx 镜像对称（右标 +1px 补偿偶数尺寸，容差 1px）。"""
    lib = AssetLibrary(assets_dir)
    elem = _flank_elem()
    for name_width in (0, 120):
        img = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"},
                             {"name_width": name_width})
        region = img.crop((150, 340, 362, 376))
        bbox = region.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
        assert bbox
        left_edge, right_edge = bbox[0] + 150, bbox[2] + 150
        assert abs((256 - left_edge) - (right_edge - 256)) <= 1


def test_faction(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = render_element(canvas(), lib, "faction",
                         {"kind": "faction", "pos": [256, 318], "size": 44}, {"faction": "红莲"})
    assert opaque(img) > 0
    # 无相：跳过
    assert opaque(render_element(canvas(), lib, "faction",
                                 {"kind": "faction", "pos": [256, 318], "size": 44},
                                 {"faction": "无相"})) == 0


def test_faction_style(assets_dir):
    """卡面 faction_style（1-3）覆盖布局元素 style（缺省 2）：三样式渲染互不相同。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "faction", "pos": [256, 318], "size": 44, "style": 2}
    imgs = [render_element(canvas(), lib, "faction", elem,
                           {"faction": "红莲", "faction_style": s}) for s in (1, 2, 3)]
    for img in imgs:
        assert opaque(img) > 0
    assert list(imgs[0].getdata()) != list(imgs[1].getdata())
    assert list(imgs[1].getdata()) != list(imgs[2].getdata())
    # 缺省 faction_style = 布局 style（2）
    assert list(imgs[1].getdata()) == list(render_element(
        canvas(), lib, "faction", elem, {"faction": "红莲"}).getdata())


def test_stat_digit_spacing(assets_dir):
    """多位数逐字拼接：相邻字墨迹最小水平间距=_DIGIT_GAP（窄字「41」不按 box 等距）；
    各字墨迹中点竖直对齐。"""
    from bwpdiy.render.badges import _DIGIT_GAP, _render_digits, _row_ink_extents
    lib = AssetLibrary(assets_dir)
    font = lib.font("name", 40)
    one = _render_digits("1", font, 2)
    four = _render_digits("4", font, 2)
    pair = _render_digits("41", font, 2)
    # 「41」宽度应明显小于 box 等距（4 右缘与 1 左缘的 box 间距被墨迹间距取代）
    assert pair.width < four.width + one.width + _DIGIT_GAP
    # 精确间距用对称「22」验证：第二字恒位于 pair 右端，逐行回算最小墨迹间距
    two = _render_digits("2", font, 2)
    pair2 = _render_digits("22", font, 2)
    h2 = pair2.height
    x1 = pair2.width - two.width
    off1 = (h2 - two.height) // 2
    extL = _row_ink_extents(pair2.crop((0, 0, x1, h2)))
    extR = _row_ink_extents(pair2.crop((x1, 0, pair2.width, h2)))
    dists = [x1 + extR[y - off1][0] - extL[y][1]
             for y in range(h2)
             if 0 <= y - off1 < two.height and extL[y] and extR[y - off1]]
    assert min(dists) == _DIGIT_GAP
    # 竖直中点对齐：对称「11」两字墨迹行区间完全一致（同字形同中线）
    pair11 = _render_digits("11", font, 2)
    x1 = pair11.width - one.width
    rowsL = [y for y, e in enumerate(_row_ink_extents(pair11.crop((0, 0, x1, pair11.height)))) if e]
    rowsR = [y for y, e in enumerate(_row_ink_extents(pair11.crop((x1, 0, pair11.width, pair11.height)))) if e]
    assert rowsL == rowsR


@pytest.mark.parametrize("color", ["red", "green", "purple"])
def test_stat_value_colors(assets_dir, color):
    """数值变色（<field>_color）：与默认白字渲染不同；带符号时符号同步变色。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "power+", "pos": [160, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": 30}
    white = render_element(canvas(), lib, "power", elem, {"type": "战斗", "power+": 2})
    colored = render_element(canvas(), lib, "power", elem,
                             {"type": "战斗", "power+": 2, "power+_color": color})
    assert list(white.getdata()) != list(colored.getdata())
    top, _ = STAT_COLORS[color]
    # 变色数字墨迹中出现目标色系像素（渐变顶色附近）
    found = any(abs(r - top[0]) < 40 and abs(g - top[1]) < 40 and abs(b - top[2]) < 40
                for r, g, b, a in colored.getdata() if a > 200)
    assert found


@pytest.mark.parametrize("color", ["yellow", "cyan", "purple", "red", "blue", "brown"])
def test_level_badge_colors(assets_dir, color):
    """勾玉六色素材齐备可渲染；非黄色与黄色渲染结果不同。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "level_badge", "pos": [120, 65], "base_size": 72, "num_size": 40}
    img = render_element(canvas(), lib, "level", elem, {"level": 2, "level_color": color})
    assert opaque(img) > 0
    if color != "yellow":
        yellow = render_element(canvas(), lib, "level", elem, {"level": 2})
        assert list(img.getdata()) != list(yellow.getdata())


def test_stat_signed_and_offset(assets_dir):
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "power+", "pos": [160, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": 30}
    img = render_element(canvas(), lib, "power", elem, {"type": "战斗", "power+": 1})
    assert opaque(img) > 100  # 图标+符号+数字像素
    # 缺字段跳过
    assert opaque(render_element(canvas(), lib, "power", elem, {"type": "战斗"})) == 0


def test_stat_group_offset_stacks_on_num_offset(assets_dir):
    """group_offset：符号+数字整体相对角标的额外偏移，叠加在 num_offset 之上；
    图标不动、符号随数字整体一起移动。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "power+", "pos": [160, 485],
            "icon_size": 32, "num_offset": [60, 0], "font_size": 30}
    card = {"type": "战斗", "power+": 2}
    base = render_element(canvas(), lib, "power", elem, card)
    moved = render_element(canvas(), lib, "power",
                           dict(elem, group_offset=[10, -6]), card)
    assert list(base.getdata()) != list(moved.getdata())
    # 图标（角标）不动：图标中心像素两版一致
    assert base.getpixel((160, 485)) == moved.getpixel((160, 485))
    # 数字块整体位移：带符号数字带 bbox 中心移动 ≈ (10, -6)
    bx = _band_bbox(base, 180, 512)     # 图标右侧数字带（含符号）
    mx = _band_bbox(moved, 180, 512)
    assert bx and mx
    assert abs(((mx[0] + mx[2]) / 2) - ((bx[0] + bx[2]) / 2) - 10) <= 1
    assert abs(_cy(mx) - _cy(bx) + 6) <= 1
    # 缺省 [0,0] 与不带键等价
    explicit = render_element(canvas(), lib, "power",
                              dict(elem, group_offset=[0, 0]), card)
    assert list(base.getdata()) == list(explicit.getdata())


def test_text_element_centered(assets_dir):
    """kind=text 点元素：以 pos 为中心水平居中单行文本；字段缺失跳过。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "text", "pos": [256, 358], "font_size": 30, "font": "name"}
    img = render_element(canvas(), lib, "name", elem, {"name": "测试卡名"})
    bbox = img.getchannel("A").getbbox()
    assert bbox
    cx = (bbox[0] + bbox[2]) / 2
    assert abs(cx - 256) <= 1  # 水平居中于 pos
    cy = (bbox[1] + bbox[3]) / 2
    assert abs(cy - 358) < elem["font_size"] / 2  # 竖直在 pos 附近（mm 锚点按字体度量居中）
    # 字段缺失/为空：原样返回
    assert opaque(render_element(canvas(), lib, "footer", elem, {})) == 0


def _band_bbox(img, x0, x1, y0=460, y1=510):
    """条带内不透明像素的整体 bbox（原图坐标）；无墨迹返回 None。"""
    region = img.crop((x0, y0, x1, y1))
    bbox = region.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    if bbox is None:
        return None
    return (bbox[0] + x0, bbox[1] + y0, bbox[2] + x0, bbox[3] + y0)


def _cy(bbox):
    return (bbox[1] + bbox[3]) / 2


@pytest.mark.parametrize("value", [3, -3, -12])
def test_stat_signed_block_centered(assets_dir, value):
    """带号 stat（战斗）：符号贴图+数字整体块的视觉中心对齐 num_pos（容差 1px）。

    覆盖 + 与 -：符号为 signs/plus|minus.png 贴图（裁 bbox 等比 contain 进
    sign_size 见方框），与数字墨迹中心竖直对齐组成整体块。
    """
    lib = AssetLibrary(assets_dir)
    # num_offset 拉大，使数字带与图标像素分离便于测量；num_pos=(160,485)
    elem = {"kind": "stat", "field": "power+", "pos": [100, 485],
            "icon_size": 32, "num_offset": [60, 0], "font_size": 30,
            "sign_size_plus": 12, "sign_size_minus": 12}
    signed = render_element(canvas(), lib, "power", elem, {"type": "战斗", "power+": value})
    # 整体块：num_pos=(160,485) 附近（图标在 x≤116，不进带）
    block = _band_bbox(signed, 120, 260)
    assert block
    assert abs((block[0] + block[2]) / 2 - 160) <= 1  # 块视觉中心对齐 num_pos.x
    # 符号/数字竖直居中：数字带 = 块右侧 digit_ink 宽（与渲染同源 _render_digits 口径）
    from bwpdiy.render.badges import _render_digits
    font = lib.font("name", 30)
    dw = _render_digits(str(abs(value)), font, 2).width
    s_digits = _band_bbox(signed, block[2] - dw, block[2])
    s_sign = _band_bbox(signed, block[0], block[2] - dw - 1)
    assert s_digits and s_sign  # alpha 含符号区（贴图）与数字区
    assert abs(_cy(s_sign) - _cy(s_digits)) <= 1
    # 符号贴图明显窄于数字块
    assert (s_sign[2] - s_sign[0]) < (s_digits[2] - s_digits[0])


def test_stat_sign_size_split(assets_dir):
    """加号/减号尺寸分开可调：sign_size_plus 只影响正值、sign_size_minus 只影响负值；
    缺省回退 sign_size → font_size/2。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "power+", "pos": [100, 485],
            "icon_size": 32, "num_offset": [60, 0], "font_size": 30,
            "sign_size_plus": 8, "sign_size_minus": 20}
    pos_img = render_element(canvas(), lib, "power", elem, {"type": "战斗", "power+": 2})
    neg_img = render_element(canvas(), lib, "power", elem, {"type": "战斗", "power+": -2})
    # 符号带宽度：加号 8px 档明显窄于减号 20px 档（数字部分等宽，比较整块左缘）
    pos_block = _band_bbox(pos_img, 120, 260)
    neg_block = _band_bbox(neg_img, 120, 260)
    assert pos_block and neg_block
    assert (neg_block[2] - neg_block[0]) - (pos_block[2] - pos_block[0]) >= 8
    # 旧数据回退：sign_size 同时喂给加/减号
    legacy = {"kind": "stat", "field": "power+", "pos": [100, 485],
              "icon_size": 32, "num_offset": [60, 0], "font_size": 30, "sign_size": 12}
    new_default = dict(legacy, sign_size_plus=12, sign_size_minus=12)
    del new_default["sign_size"]
    for v in (2, -2):
        a = render_element(canvas(), lib, "power", legacy, {"type": "战斗", "power+": v})
        b = render_element(canvas(), lib, "power", new_default, {"type": "战斗", "power+": v})
        assert list(a.getdata()) == list(b.getdata())


def test_stat_unsigned_block_centered(assets_dir):
    """不带号 stat（式神/形态/幻境等其余类型）：数字视觉中心对齐 num_pos。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "power", "pos": [100, 485],
            "icon_size": 32, "num_offset": [60, 0], "font_size": 30}
    img = render_element(canvas(), lib, "power", elem, {"type": "式神", "power": 12})
    block = _band_bbox(img, 120, 260)
    assert block
    assert abs((block[0] + block[2]) / 2 - 160) <= 1


def test_stat_sign_derived_by_type(assets_dir):
    """符号规则按 stat 适用矩阵：战斗/法术觉醒 ±，式神/形态/幻境不带号。

    法术觉醒与战斗共用同一 signed 贴图路径（含负值 minus.png），数字带逐像素一致——
    钉死审查遗留的"法术负值走全宽 - 路径"不一致（图标按类型不同，只比数字带）。
    """
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "power+", "pos": [100, 485],
            "icon_size": 32, "num_offset": [60, 0], "font_size": 30,
            "sign_size_plus": 12, "sign_size_minus": 12}

    def digit_band(card):
        img = render_element(canvas(), lib, "power", elem, card)
        return _band_bbox(img, 120, 260)

    spell = digit_band({"type": "法术", "evolve": True, "power+": 3})  # 法术觉醒：+
    combat = digit_band({"type": "战斗", "power+": -3})  # 战斗：+/-
    assert spell and combat
    # 法术觉醒与战斗同值渲染的数字带（符号+数字块）逐像素一致（同一 signed 路径）
    for value in (3, -3):
        combat_img = render_element(canvas(), lib, "power", elem,
                                    {"type": "战斗", "power+": value})
        spell_img = render_element(canvas(), lib, "power", elem,
                                   {"type": "法术", "evolve": True, "power+": value})
        assert (combat_img.crop((120, 400, 260, 512)).tobytes()
                == spell_img.crop((120, 400, 260, 512)).tobytes())


@pytest.mark.parametrize("card", [
    {"type": "法术", "power+": 3},                # 非觉醒法术：无任何角标
    {"type": "法术", "evolve": False, "power+": 3},
    {"type": "协战", "power+": 3},                # 协战：无 stat
    {"type": "式神", "power+": 3},                # 表外 (type, field) 组合
    {"type": "形态", "shield+": 2},               # 表外：形态无护甲加成
    {"power+": 3},                                # 缺 type
])
def test_stat_matrix_off_whitelist_skipped(assets_dir, card):
    """适用矩阵表外组合即使 card 带该字段也不绘制。"""
    lib = AssetLibrary(assets_dir)
    field = "shield+" if "shield+" in card else "power+"
    elem = {"kind": "stat", "field": field, "pos": [160, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": 30}
    assert opaque(render_element(canvas(), lib, "stat", elem, card)) == 0


@pytest.mark.parametrize("card_type,field", [("战斗", "power+"), ("战斗", "shield+"),
                                             ("法术", "power+"), ("法术", "health+")])
def test_stat_zero_skipped_for_combat_evolve_spell(assets_dir, card_type, field):
    """战斗/法术觉醒的加成 stat 值为 0 时整个角标（图标+数字）不渲染。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": field, "pos": [160, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": 30}
    card = {field: 0, "type": card_type, "evolve": True}
    assert opaque(render_element(canvas(), lib, "stat", elem, card)) == 0
    card[field] = 1
    assert opaque(render_element(canvas(), lib, "stat", elem, card)) > 0


@pytest.mark.parametrize("card_type,field", [("式神", "power"), ("形态", "health"),
                                             ("幻境", "durability")])
def test_stat_zero_rendered_for_body_types(assets_dir, card_type, field):
    """式神/形态/幻境的 stat 值为 0 也照常渲染。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": field, "pos": [160, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": 30}
    assert opaque(render_element(canvas(), lib, "stat", elem, {field: 0, "type": card_type})) > 0


def test_stat_rendered_helper():
    """stat_rendered：stat 元素实际渲染判定（渲染与文本避让障碍同口径），按适用矩阵。"""
    from bwpdiy.render.badges import stat_rendered
    shield = {"kind": "stat", "field": "shield+"}
    assert stat_rendered(shield, {"type": "战斗", "shield+": 2})
    assert stat_rendered(shield, {"type": "战斗", "shield+": -1})
    assert not stat_rendered(shield, {"type": "战斗", "shield+": 0})
    assert not stat_rendered(shield, {"type": "战斗"})  # 字段缺失
    durability = {"kind": "stat", "field": "durability"}
    assert stat_rendered(durability, {"type": "幻境", "durability": 0})  # 幻境 0 照渲
    power = {"kind": "stat", "field": "power+"}
    assert stat_rendered(power, {"type": "法术", "evolve": True, "power+": 3})  # 法术觉醒
    assert not stat_rendered(power, {"type": "法术", "evolve": True, "power+": 0})  # 觉醒 0 不绘
    assert not stat_rendered(power, {"type": "法术", "power+": 3})  # 非觉醒法术不绘
    assert not stat_rendered(power, {"type": "协战", "power+": 3})  # 协战无 stat
    assert not stat_rendered(power, {"type": "式神", "power+": 3})  # 表外组合
    body = {"kind": "stat", "field": "power"}
    assert stat_rendered(body, {"type": "式神", "power": 0})  # 式神 0 照渲


def test_level_badge_disabled(assets_dir):
    """level_badge 支持 per-type enabled 开关：enabled=false 整体跳过，缺省/true 照常渲染。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "level_badge", "pos": [120, 65], "base_size": 72, "star_size": 60, "num_size": 40}
    assert opaque(render_element(canvas(), lib, "level", dict(elem, enabled=False),
                                 {"level": 2, "evolve": True})) == 0
    assert opaque(render_element(canvas(), lib, "level", dict(elem, enabled=True),
                                 {"level": 2})) > 0
    # 缺省 enabled 视为 true（兼容旧布局）
    assert opaque(render_element(canvas(), lib, "level", elem, {"level": 2})) > 0


def test_stat_negative_shield_uses_fragile_badge(assets_dir):
    """战斗护甲按当前值自动选贴图：值 < 0 用破甲（combat_fragile_2），否则护甲。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "shield+", "pos": [360, 485],
            "icon_size": 32, "num_offset": [40, 0], "font_size": 30}  # 数字远移，图标区纯净
    pos_img = render_element(canvas(), lib, "shield", elem, {"type": "战斗", "shield+": 1})
    neg_img = render_element(canvas(), lib, "shield", elem, {"type": "战斗", "shield+": -1})
    assert list(pos_img.getdata()) != list(neg_img.getdata())  # 负值换用破甲贴图
    # 负值图标区与 fragile_2 贴图直贴一致（钉死负值贴图来源）
    from bwpdiy.render.badges import FRAGILE_VARIANT, _paste_element
    direct = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    direct = _paste_element(direct, lib.stat_badge(f"combat_fragile_{FRAGILE_VARIANT}"),
                            (360, 485), (32, 32))
    icon_box = (344, 469, 376, 501)
    assert (neg_img.crop(icon_box).tobytes() == direct.crop(icon_box).tobytes())


def test_stat_fragile_separate_layout_keys(assets_dir):
    """战斗负护甲读 fragile_* 四键（坐标/图标大小/数字偏移/符号偏移），缺省回退基础键。"""
    from bwpdiy.render.badges import FRAGILE_VARIANT, _paste_element
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "shield+", "pos": [360, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": 30,
            "fragile_pos": [200, 200], "fragile_icon_size": 20,
            "fragile_num_offset": [60, 0]}  # 数字远移，图标区纯净
    card = {"type": "战斗", "shield+": -1}
    out = render_element(canvas(), lib, "shield", elem, card)
    # 破甲图标出现在 fragile_pos（200,200）尺寸 fragile_icon_size（20），与直贴一致
    direct = _paste_element(Image.new("RGBA", (512, 512), (0, 0, 0, 0)),
                            lib.stat_badge(f"combat_fragile_{FRAGILE_VARIANT}"),
                            (200, 200), (20, 20))
    icon_box = (190, 190, 210, 210)
    assert out.crop(icon_box).tobytes() == direct.crop(icon_box).tobytes()
    # 基础 pos（360,485）处不再有破甲图标
    assert out.getchannel("A").crop((344, 469, 376, 501)).getbbox() is None
    # 正值仍用基础键：图标在基础 pos
    pos_img = render_element(canvas(), lib, "shield", elem, {"type": "战斗", "shield+": 1})
    assert pos_img.getchannel("A").crop((344, 469, 376, 501)).getbbox() is not None
    assert pos_img.getchannel("A").crop((190, 190, 210, 210)).getbbox() is None
    # 缺省 fragile_* 键回退基础键：与无键元素渲染一致
    bare = {k: v for k, v in elem.items() if not k.startswith("fragile_")}
    assert (render_element(canvas(), lib, "shield", bare, card).tobytes()
            == render_element(canvas(), lib, "shield",
                              dict(bare, fragile_pos=bare["pos"],
                                   fragile_icon_size=bare["icon_size"],
                                   fragile_num_offset=bare["num_offset"]),
                              card).tobytes())


def test_stat_fragile_variant_selectable(assets_dir):
    """破甲贴图变体可配：fragile_variant=1 用 combat_fragile_1，缺省为 2。"""
    from bwpdiy.render.badges import FRAGILE_VARIANT, _paste_element
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "shield+", "pos": [360, 485],
            "icon_size": 32, "num_offset": [40, 0], "font_size": 30}
    card = {"type": "战斗", "shield+": -1}
    v1 = render_element(canvas(), lib, "shield", dict(elem, fragile_variant=1), card)
    direct = _paste_element(Image.new("RGBA", (512, 512), (0, 0, 0, 0)),
                            lib.stat_badge("combat_fragile_1"), (360, 485), (32, 32))
    icon_box = (344, 469, 376, 501)
    assert v1.crop(icon_box).tobytes() == direct.crop(icon_box).tobytes()
    default = render_element(canvas(), lib, "shield", elem, card)
    direct2 = _paste_element(Image.new("RGBA", (512, 512), (0, 0, 0, 0)),
                             lib.stat_badge(f"combat_fragile_{FRAGILE_VARIANT}"),
                             (360, 485), (32, 32))
    assert default.crop(icon_box).tobytes() == direct2.crop(icon_box).tobytes()
    assert list(v1.getdata()) != list(default.getdata())  # 两变体视觉不同


def test_stat_part_split(assets_dir):
    """stat 分层绘制：icon 层只画角标图标、number 层只画符号+数字，
    两层顺序叠加与完整渲染逐像素一致（pipeline 描述文本后压数值层的依据）。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "power+", "pos": [160, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": 30}
    card = {"type": "战斗", "power+": -2}
    full = render_element(canvas(), lib, "power", elem, card)
    icon_only = render_element(canvas(), lib, "power", elem, card, stat_part="icon")
    number_only = render_element(canvas(), lib, "power", elem, card, stat_part="number")
    layered = render_element(icon_only, lib, "power", elem, card, stat_part="number")
    assert layered.tobytes() == full.tobytes()
    # number 层不带图标：图标中心（160,485）在 number_only 上无墨迹，full 上有
    assert number_only.getchannel("A").getpixel((160, 485)) == 0
    assert full.getchannel("A").getpixel((160, 485)) > 0


# ---------- 掩膜采集：composite 贴图保真（P1 修复） ----------

def test_paste_centered_composite_preserves_alpha():
    """composite=True 走 alpha_composite：透明层上源 alpha 保真（默认 paste 会平方 alpha）。"""
    from bwpdiy.render.common import paste_centered
    src = Image.new("RGBA", (4, 4), (10, 10, 10, 20))  # 淡边缘 alpha=20
    out = paste_centered(canvas(), src, (100, 100), composite=True)
    assert out.getchannel("A").getpixel((100, 100)) == 20  # 保真入掩膜（>10）
    default = paste_centered(canvas(), src, (100, 100))
    assert default.getchannel("A").getpixel((100, 100)) < 10  # 默认 paste：20²/255≈1 被掩膜丢弃


def test_stat_mask_composite_covers_faint_edges(assets_dir):
    """淡边缘图标：composite 掩膜严格覆盖默认 paste 掩膜，且吃到 alpha≤50 的淡边缘。"""
    from types import SimpleNamespace

    from bwpdiy.render.geometry import mask_row_runs
    lib = AssetLibrary(assets_dir)
    # 合成淡边缘图标：中心实、外圈 alpha=20（实卡有 ~8% 可见度，默认 paste 平方后被 alpha_min=10 丢弃）
    icon = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    from PIL import ImageDraw
    d = ImageDraw.Draw(icon)
    d.rectangle((8, 8, 23, 23), fill=(10, 10, 10, 255))
    d.rectangle((4, 4, 27, 27), outline=(10, 10, 10, 20), width=4)
    fake_lib = SimpleNamespace(stat_badge=lambda *a, **k: icon, font=lib.font)
    elem = {"kind": "stat", "field": "power",
            "pos": [100, 100], "icon_size": 32, "num_offset": [60, 0], "font_size": 30}
    card = {"type": "式神", "power": 3}
    default_runs = mask_row_runs(render_element(canvas(), fake_lib, "power", elem, card)
                                 .getchannel("A"))
    composite_runs = mask_row_runs(render_element(canvas(), fake_lib, "power", elem, card,
                                                  composite=True).getchannel("A"))
    # 图标行 y=100：默认掩膜左界在实芯 x≈92，composite 掩膜吃到淡边缘 x≈88（严格更宽）
    default_left = min(x0 for x0, _ in default_runs[100])
    composite_left = min(x0 for x0, _ in composite_runs[100])
    assert composite_left < default_left
    # 超集关系：默认掩膜的每个墨迹区间都被 composite 掩膜覆盖
    for row, runs in default_runs.items():
        for x0, x1 in runs:
            assert any(c0 <= x0 and x1 <= c1 for c0, c1 in composite_runs[row])


# ---------- 协战双式神框（duo_frame） ----------

def _duo_elem():
    return {"kind": "duo_frame", "pos": [91, 164], "size": [74, 147]}


def _duo_slot(art, faction="苍叶"):
    return {"art": {"path": str(art), "offset_x": 0, "offset_y": 0, "scale": 1.0, "rotate": 0},
            "faction": faction}


def test_duo_frame_off_by_default(assets_dir):
    """双式神框默认不绘制：无 duo_frame 字段 / False / 非协战类型均不画。"""
    lib = AssetLibrary(assets_dir)
    elem = _duo_elem()
    assert opaque(render_element(canvas(), lib, "duo_frame", elem, {"type": "协战"})) == 0
    assert opaque(render_element(canvas(), lib, "duo_frame", elem,
                                 {"type": "协战", "duo_frame": False})) == 0
    assert opaque(render_element(canvas(), lib, "duo_frame", elem,
                                 {"type": "战斗", "duo_frame": True})) == 0


def test_duo_frame_empty_slots_fallback(assets_dir):
    """开启但无 _duo（或槽位 None）：只画底板+双框（空菱形），不报错。"""
    lib = AssetLibrary(assets_dir)
    card = {"type": "协战", "duo_frame": True}
    a = render_element(canvas(), lib, "duo_frame", _duo_elem(), card)
    assert opaque(a) > 0
    b = render_element(canvas(), lib, "duo_frame", _duo_elem(), {**card, "_duo": [None, None]})
    assert list(a.getdata()) == list(b.getdata())
    # 两槽位中心（91,164)/(91,238) 为黑底板墨迹；组件盒外 (41,114) 无墨
    assert a.getpixel((91, 164))[3] > 0 and a.getpixel((91, 238))[3] > 0
    assert a.getchannel("A").getpixel((41, 114)) == 0


def test_duo_frame_slot_art_masked_and_faction(assets_dir, sample_art):
    """槽位头像 cover 适配槽位盒并按底板 alpha 菱形裁剪；派系小标按 faction 选图。"""
    lib = AssetLibrary(assets_dir)
    card = {"type": "协战", "duo_frame": True,
            "_duo": [_duo_slot(sample_art, "苍叶"), _duo_slot(sample_art, "红莲")]}
    img = render_element(canvas(), lib, "duo_frame", _duo_elem(), card)
    empty = render_element(canvas(), lib, "duo_frame", _duo_elem(),
                           {"type": "协战", "duo_frame": True})
    assert list(img.getdata()) != list(empty.getdata())  # 头像注入生效
    # 菱形掩膜：组件盒外 (41,114) 即使有头像也不落墨
    assert img.getchannel("A").getpixel((41, 114)) == 0
    # 无相/缺派系不画小标：与带派系渲染不同
    no_faction = render_element(canvas(), lib, "duo_frame", _duo_elem(),
                                {"type": "协战", "duo_frame": True,
                                 "_duo": [{"art": _duo_slot(sample_art)["art"]},
                                          _duo_slot(sample_art, "无相")]})
    assert list(img.getdata()) != list(no_faction.getdata())
    # 派系异色选图：槽位1 苍叶 vs 青岚 渲染不同
    other = render_element(canvas(), lib, "duo_frame", _duo_elem(),
                           {"type": "协战", "duo_frame": True,
                            "_duo": [_duo_slot(sample_art, "青岚"),
                                     _duo_slot(sample_art, "红莲")]})
    assert list(img.getdata()) != list(other.getdata())


# ---------- 式神头像预览（render_portrait，duo_frame 单槽位 ×2） ----------

def test_render_portrait_layers_and_scale(assets_dir, sample_art):
    """单槽位合成：空槽=底板+框+派系标有墨迹；头像注入生效；scale=2 比 1 大。"""
    from bwpdiy.render.duo import render_portrait
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "duo_frame", "pos": [91, 164]}
    art_ref = {"path": str(sample_art), "offset_x": 0, "offset_y": 0,
               "scale": 1.0, "rotate": 0}
    empty = render_portrait(lib, elem, None, "苍叶")
    assert opaque(empty) > 0
    with_art = render_portrait(lib, elem, art_ref, "苍叶")
    assert list(with_art.getdata()) != list(empty.getdata())
    small = render_portrait(lib, elem, art_ref, "苍叶", scale=1)
    assert with_art.width > small.width and with_art.height > small.height


def test_render_portrait_faction_badge(assets_dir, sample_art):
    """派系标随 faction：异派系渲染不同，无相/缺派系不画小标。"""
    from bwpdiy.render.duo import render_portrait
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "duo_frame", "pos": [91, 164]}
    art_ref = {"path": str(sample_art), "offset_x": 0, "offset_y": 0,
               "scale": 1.0, "rotate": 0}
    a = render_portrait(lib, elem, art_ref, "苍叶")
    b = render_portrait(lib, elem, art_ref, "青岚")
    c = render_portrait(lib, elem, art_ref, "无相")
    d = render_portrait(lib, elem, art_ref, None)
    assert list(a.getdata()) != list(b.getdata())
    assert list(a.getdata()) != list(c.getdata())
    assert list(c.getdata()) == list(d.getdata())  # 无相与缺派系同：均不画小标
