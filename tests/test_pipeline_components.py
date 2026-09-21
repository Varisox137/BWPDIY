"""六类型样卡组件绘制验证：透明画布单元素渲染 + 像素 alpha 墨迹检测。

渲染层只读调用（render_element/draw_region 为既有公开接口），不改 render。
区域从布局元素 pos/size 推导：正断言=组件预期区域确有墨迹；负断言=不该绘制的
组合画布全透明（协战无 stat 元素、幻境左下无 stat、非觉醒法术 stat 不绘、
无相无派系标、signed 0 值不绘、enabled=false/缺等级不绘等级标、双标间空隙）。
"""

import copy
from pathlib import Path

import pytest
from PIL import Image

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import render_element
from bwpdiy.render.layout import get_type_layout, load_layouts
from bwpdiy.render.text import draw_region
from bwpdiy.web.sample_cards import SAMPLE_CARDS

ASSETS = Path(__file__).resolve().parent.parent / "assets"
LIB = AssetLibrary(ASSETS)
LAYOUTS = load_layouts(ASSETS)
SIZE = (512, 512)
ALPHA_MIN = 10

ALL_TYPES = ["式神", "战斗", "法术", "形态", "幻境", "协战"]


def blank() -> Image.Image:
    return Image.new("RGBA", SIZE, (0, 0, 0, 0))


def ink(img: Image.Image, cx: float, cy: float, hw: float, hh: float) -> int:
    """以 (cx,cy) 为中心、半宽 hw 半高 hh 的矩形内 alpha > ALPHA_MIN 的像素数。"""
    region = img.crop((round(cx - hw), round(cy - hh), round(cx + hw), round(cy + hh)))
    hist = region.getchannel("A").histogram()
    return sum(hist[ALPHA_MIN + 1:])


def total_ink(img: Image.Image) -> int:
    hist = img.getchannel("A").histogram()
    return sum(hist[ALPHA_MIN + 1:])


def elem(card_type: str, name: str) -> dict:
    return get_type_layout(LAYOUTS, card_type)["elements"][name]


def sample(card_type: str, **overrides) -> dict:
    card = copy.deepcopy(SAMPLE_CARDS[card_type])
    # 脚注兜底与 pipeline.render_card 同口径（render_element 不做兜底）：
    # 协战双式神齐备标 式神1×式神2-协战；无所属式神（中立牌）只标 类型[/子类型]；
    # 式神卡回退卡名
    if not card.get("footer"):
        if card_type == "协战":
            s1, s2 = card.get("shikigami1"), card.get("shikigami2")
            card["footer"] = f"{s1}×{s2}-协战" if s1 and s2 else card_type
        else:
            shikigami = card.get("shikigami") or (card["name"] if card_type == "式神" else None)
            card["footer"] = f"{shikigami}-{card_type}" if shikigami else card_type
            if card.get("special_type"):
                card["footer"] += f"/{card['special_type']}"
    card.update(overrides)
    return card


def render_one(card_type: str, elem_name: str, card: dict | None = None) -> Image.Image:
    """透明画布上只渲染指定元素（ctx.name_width 置 0：rarity 双标取 gap 静态位）。

    duo_frame 默认不绘制（卡面开关）：单元素渲染默认开开关（空槽位框口径）。"""
    e = elem(card_type, elem_name)
    if card is None:
        card = sample(card_type)
        if e["kind"] == "duo_frame":
            card["duo_frame"] = True
    return render_element(blank(), LIB, elem_name, e, card, {"name_width": 0})


# ---------- 全类型 × 全元素：每个应当绘制的组件在其锚点区域确有墨迹 ----------

def _anchor_box(card_type: str, name: str) -> tuple:
    """组件主锚点墨迹检测框 (cx, cy, hw, hh)，从布局 pos/size 推导。"""
    e = elem(card_type, name)
    kind = e["kind"]
    if kind == "level_badge":
        return (*e["pos"], e["base_size"] / 2, e["base_size"] / 2)
    if kind == "rarity_flank":  # 左标为代表（双标镜像由专项测试覆盖）
        return (e["pos"][0] - e["gap"], e["pos"][1], e["size"] / 2, e["size"] / 2)
    if kind == "faction":
        return (*e["pos"], e["size"] / 2, e["size"] / 2)
    if kind == "stat":  # 图标为代表（数字由专项测试覆盖）
        return (*e["pos"], e["icon_size"] / 2, e["icon_size"] / 2)
    if kind == "text":
        return (e["pos"][0], e["pos"][1], 120, e["font_size"])
    if kind == "duo_frame":
        return (*e["pos"], e["size"][0] / 2, e["size"][1] / 2)
    raise AssertionError(f"未知 kind: {kind}")


def _neighborhood(card_type: str, name: str) -> tuple:
    """组件全部墨迹应落入的邻域框（局部性断言）：覆盖该 kind 的全部绘制部分。"""
    e = elem(card_type, name)
    kind = e["kind"]
    if kind == "duo_frame":  # 槽位盒(88×80)大于双框：槽位间距 70 + 盒高 80
        return (*e["pos"], 44 + 8, 35 + 40 + 8)
    if kind == "level_badge":  # 觉醒星标大于底座
        return (*e["pos"], e["star_size"] / 2 + 8, e["star_size"] / 2 + 8)
    if kind == "rarity_flank":  # 左右双标整体
        return (e["pos"][0], e["pos"][1], e["gap"] + e["size"] / 2 + 8, e["size"] / 2 + 8)
    if kind == "stat":  # 图标 + 数字偏移块
        return (*e["pos"], e["icon_size"] / 2 + abs(e["num_offset"][0]) + e["font_size"],
                e["icon_size"] / 2 + abs(e["num_offset"][1]) + e["font_size"])
    if kind == "faction":
        return (*e["pos"], e["size"] / 2 + 8, e["size"] / 2 + 8)
    if kind == "text":
        return (e["pos"][0], e["pos"][1], 136, e["font_size"] + 8)
    raise AssertionError(f"未知 kind: {kind}")


@pytest.mark.parametrize("card_type", ALL_TYPES)
def test_all_elements_draw_at_anchor(card_type):
    """布局元素表逐元素：透明画布渲染后，锚点区域有墨迹、且墨迹全落在组件邻域内。"""
    for name, e in get_type_layout(LAYOUTS, card_type)["elements"].items():
        img = render_one(card_type, name)
        assert ink(img, *_anchor_box(card_type, name)) > 0, \
            f"{card_type}/{name}({e['kind']}) 锚点区域无墨迹"
        # 局部性：邻域之外不得有墨迹（防止断言被错位渲染蒙混）
        assert total_ink(img) == ink(img, *_neighborhood(card_type, name)), \
            f"{card_type}/{name} 墨迹逸出组件邻域"


# ---------- 等级标：底座/数字/星标三层 ----------

@pytest.mark.parametrize("card_type", ALL_TYPES)
def test_level_badge_base_and_num_layers(card_type):
    """六类型样卡均带 level：底座边缘与中心数字都有墨迹（协战等价始终启用）。"""
    e = elem(card_type, "level")
    img = render_one(card_type, "level")
    x, y = e["pos"]
    assert ink(img, x, y, e["num_size"] / 2, e["num_size"] / 2) > 0  # 数字层
    edge = e["base_size"] / 2 - 4  # 底座圆盘近边缘（contain 贴边，数字够不着的位置）
    assert ink(img, x - edge, y, 3, 6) > 0  # 底座层


def test_level_badge_star_layer_only_on_evolve():
    """星标层仅觉醒卡绘制：觉醒与否两版的 alpha 差落在星标框内且超出底座框。"""
    from PIL import ImageChops
    e = elem("法术", "level")
    x, y = e["pos"]
    ev = render_one("法术", "level")                      # 样卡 evolve=true
    ne = render_one("法术", "level", sample("法术", evolve=False))
    diff = ImageChops.difference(ev.getchannel("A"), ne.getchannel("A")).getbbox()
    assert diff is not None, "觉醒星标未产生任何额外墨迹"
    sh, bh = e["star_size"] / 2 + 2, e["base_size"] / 2
    assert x - sh <= diff[0] and diff[2] <= x + sh and y - sh <= diff[1] and diff[3] <= y + sh
    assert diff[0] < x - bh or diff[2] > x + bh  # 星环比底座大（差集探出底座框）
    # 非觉醒版墨迹不超出底座框；觉醒版在底座框外有星环墨迹（星标贴图自身覆盖底座区，
    # 故不比底座区内像素）
    def ring_ink(img):
        return total_ink(img) - ink(img, x, y, e["base_size"] / 2 + 1, e["base_size"] / 2 + 1)
    assert ring_ink(ne) == 0
    assert ring_ink(ev) > 0


@pytest.mark.parametrize("card_type", ["战斗", "形态", "幻境"])
def test_level_badge_star_on_evolve_fight_form_field(card_type):
    """战斗/形态/幻境同样可觉醒：evolve=true 时星标环墨迹探出底座框，缺省不绘。"""
    e = elem(card_type, "level")
    x, y = e["pos"]
    ev = render_one(card_type, "level", sample(card_type, evolve=True))
    ne = render_one(card_type, "level")

    def ring_ink(img):
        return total_ink(img) - ink(img, x, y, e["base_size"] / 2 + 1, e["base_size"] / 2 + 1)
    assert ring_ink(ne) == 0
    assert ring_ink(ev) > 0


def test_level_badge_suppressed_when_disabled_or_no_level():
    e = elem("战斗", "level")
    assert total_ink(render_one("战斗", "level", {k: v for k, v in sample("战斗").items()
                                                if k != "level"})) == 0  # 缺等级不绘
    disabled = dict(e, enabled=False)
    img = render_element(blank(), LIB, "level", disabled, sample("战斗"), {"name_width": 0})
    assert total_ink(img) == 0  # enabled=false 不绘


# ---------- 稀有度双标：左右对称双标 + 中间空隙 ----------

RARITY_TYPES = ["战斗", "法术", "形态", "幻境", "协战"]


@pytest.mark.parametrize("card_type", RARITY_TYPES)
def test_rarity_flank_double_marks(card_type):
    e = elem(card_type, "rarity")
    cx, y = e["pos"]
    offset = max(e["gap"], e.get("margin", 8))  # ctx.name_width=0 → 静态 gap 位
    img = render_one(card_type, "rarity")
    half = e["size"] / 2 + 2
    assert ink(img, cx - offset, y, half, half) > 0  # 左标
    assert ink(img, cx + offset + 1, y, half, half) > 0  # 右标（偶数尺寸右移 1px）
    gap_half = offset - e["size"] / 2 - 4  # 双标之间的卡名区（本画布无卡名）应为空
    assert ink(img, cx, y, gap_half, e["size"] / 2) == 0


# ---------- 派系标：仅式神；无相不绘 ----------

def test_faction_drawn_for_shikigami_only():
    img = render_one("式神", "faction")  # 样卡苍叶
    e = elem("式神", "faction")
    assert ink(img, *e["pos"], e["size"] / 2, e["size"] / 2) > 0
    for t in ALL_TYPES:
        if t != "式神":
            assert "faction" not in get_type_layout(LAYOUTS, t)["elements"]


def test_faction_wuxiang_not_drawn():
    assert total_ink(render_one("式神", "faction", sample("式神", faction="无相"))) == 0


# ---------- stat：图标 + 数字；符号/零值/觉醒门控/表外 ----------

STAT_ELEMENTS = [("式神", "power"), ("式神", "health"),
                 ("战斗", "power"), ("战斗", "shield"),
                 ("法术", "power"), ("法术", "health"),
                 ("形态", "power"), ("形态", "health"),
                 ("幻境", "durability")]


@pytest.mark.parametrize("card_type,name", [(t, n) for t, n in STAT_ELEMENTS])
def test_stat_icon_and_number(card_type, name):
    e = elem(card_type, name)
    img = render_one(card_type, name)
    assert ink(img, *e["pos"], e["icon_size"] / 2, e["icon_size"] / 2) > 0  # 图标
    nx = e["pos"][0] + e["num_offset"][0]
    ny = e["pos"][1] + e["num_offset"][1]
    assert ink(img, nx, ny, e["font_size"], e["font_size"] * 0.75) > 0  # 数字


def test_stat_signed_zero_not_drawn():
    assert total_ink(render_one("战斗", "power", sample("战斗", **{"power+": 0}))) == 0
    # plain 模式（式神）0 值照常绘制
    assert total_ink(render_one("式神", "power", sample("式神", power=0))) > 0


def test_stat_non_evolve_spell_not_drawn():
    plain = sample("法术", evolve=False)
    assert total_ink(render_one("法术", "power", plain)) == 0
    assert total_ink(render_one("法术", "health", plain)) == 0


def test_stat_negative_shield_switches_icon():
    """战斗护甲负值自动换破甲贴图：+2 与 -2 的图标区像素不同，数字区都有墨迹。"""
    e = elem("战斗", "shield")
    box = (e["pos"][0], e["pos"][1], e["icon_size"] // 2, e["icon_size"] // 2)
    pos_img = render_one("战斗", "shield", sample("战斗", **{"shield+": 2}))
    neg_img = render_one("战斗", "shield", sample("战斗", **{"shield+": -2}))
    crop = lambda img: img.crop((box[0] - box[2], box[1] - box[3],
                                 box[0] + box[2], box[1] + box[3])).tobytes()
    assert crop(pos_img) != crop(neg_img)
    assert ink(neg_img, *box) > 0


def test_no_stat_where_matrix_excludes():
    """协战布局无任何 stat 元素；幻境仅右侧耐久（左下 x<256 无 stat）。"""
    xz = get_type_layout(LAYOUTS, "协战")["elements"]
    assert not any(e["kind"] == "stat" for e in xz.values())
    for name, e in get_type_layout(LAYOUTS, "幻境")["elements"].items():
        if e["kind"] == "stat":
            assert e["pos"][0] > 256, f"幻境左下不应有 stat: {name}"


# ---------- 卡名/脚注点文本 ----------

@pytest.mark.parametrize("card_type", ALL_TYPES)
@pytest.mark.parametrize("name", ["name", "footer"])
def test_text_elements(card_type, name):
    e = elem(card_type, name)
    img = render_one(card_type, name)
    assert ink(img, e["pos"][0], e["pos"][1], 120, e["font_size"]) > 0


# ---------- 描述文本区：区内有墨迹、区外无墨迹 ----------

@pytest.mark.parametrize("card_type", ALL_TYPES)
def test_desc_region(card_type):
    region = get_type_layout(LAYOUTS, card_type)["text_regions"]["desc"]
    img = draw_region(blank(), LIB, sample(card_type)["description"], region)
    cx, cy = region["center"]
    hw, hh = region["width"] / 2, region["height"] / 2
    assert ink(img, cx, cy, hw, hh) > 0
    inner = ink(img, cx, cy, hw + 6, hh + 6)  # 6px 容差（描边/字形溢出）
    assert total_ink(img) == inner, f"{card_type} 描述墨迹逸出文本区"
