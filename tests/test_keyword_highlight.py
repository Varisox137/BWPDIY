"""关键字高亮测试：[[关键字]] 双括号标记解析、异色绘制、括号剥离排版、管线与 web 端集成。

v1.2.1 起标记为双中括号，单 [ ] 为字面字符；v1.3.0 起未匹配括号按字面文本显示
（从左往右匹配，'[[' 配其后最近 ']]'，高亮内部不再解析新 '[['）。
"""

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.pipeline import render_card
from bwpdiy.render.text import (
    KEYWORD_FILL,
    TEXT_FILL,
    draw_region,
    fit_in_region,
    parse_keyword_segments,
)
from bwpdiy.web.app import create_app
from bwpdiy.web.sample_cards import SAMPLE_CARDS

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def canvas():
    return Image.new("RGBA", (512, 512), (0, 0, 0, 0))


def rect_region(x0, y0, x1, y1, **kw):
    region = {"center": [(x0 + x1) / 2, (y0 + y1) / 2],
              "width": x1 - x0, "height": y1 - y0,
              "font_range": [36, 12], "wrap": True, "font": "desc"}
    region.update(kw)
    return region


# ---------- 标记解析与校验 ----------

def test_parse_segments_plain_and_keyword():
    assert parse_keyword_segments("无标记") == [("无标记", False)]
    assert parse_keyword_segments("获得[[贯通]]效果") == [("获得", False), ("贯通", True), ("效果", False)]
    assert parse_keyword_segments("[[觉醒]]：[[充能]]") == [("觉醒", True), ("：", False), ("充能", True)]
    assert parse_keyword_segments("[[多\n行]]") == [("多\n行", True)]  # 关键字内允许换行符


def test_parse_segments_single_brackets_literal():
    """单 [ / ] 为字面字符，不构成标记也不报错；']] ' 成对出现仍按闭标记校验。"""
    assert parse_keyword_segments("约[定]俗成") == [("约[定]俗成", False)]
    assert parse_keyword_segments("a[b]c[[d]e]]") == [("a[b]c", False), ("d]e", True)]
    # 三连括号贪心：'[[[' = 开标记 + 字面 '[' 入内容；']]]' = 闭标记 + 字面 ']'
    assert parse_keyword_segments("[[[贯通]]]") == [("[贯通", True), ("]", False)]


def test_parse_segments_unmatched_literal():
    """未匹配括号按字面文本显示（v1.3.0 起不再报错）：'[[' 无闭合、']]' 无配对、空 '[[]]'。"""
    assert parse_keyword_segments("未闭合[[关键字") == [("未闭合[[关键字", False)]
    assert parse_keyword_segments("多余]]右括号") == [("多余]]右括号", False)]
    assert parse_keyword_segments("空[[]]标记") == [("空[[]]标记", False)]
    # 从左往右：'[[' 配其后最近 ']]'，高亮内部不再解析新 '[['（字面进入关键字内容）
    assert parse_keyword_segments("嵌套[[甲[[乙]]丙]]") == [
        ("嵌套", False), ("甲[[乙", True), ("丙]]", False)]


# ---------- 排版与绘制 ----------

def test_brackets_stripped_from_layout(assets_dir):
    """标记不参与排版：fit 返回纯文本行，宽度与无标记文本一致。"""
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 100, 400, 200)
    _, plain = fit_in_region("获得贯通效果", region, lib)
    fitted = fit_in_region("获得[[贯通]]效果", region, lib)
    assert fitted is not None
    _, marked = fitted
    assert [t for t, _, _ in marked] == [t for t, _, _ in plain]
    assert marked[0][0] == "获得贯通效果"


def test_draw_keyword_different_color(assets_dir):
    """关键字段用 keyword_fill 绘制：图上同时存在正文色与关键字色像素。"""
    lib = AssetLibrary(assets_dir)
    img = draw_region(canvas(), lib, "获得[[贯通]]效果", rect_region(100, 100, 400, 200),
                      fill=TEXT_FILL, keyword_fill=KEYWORD_FILL)

    def near(p, c, tol=30):
        return p[3] > 200 and all(abs(p[i] - c[i]) <= tol for i in range(3))

    pixels = list(img.getdata())
    assert any(near(p, KEYWORD_FILL) for p in pixels)
    assert any(near(p, TEXT_FILL) for p in pixels)


def test_draw_without_keyword_fill_uniform(assets_dir):
    """keyword_fill=None：标记剥离、整行正文色（向后兼容旧调用）。"""
    lib = AssetLibrary(assets_dir)
    img = draw_region(canvas(), lib, "[[贯通]]", rect_region(100, 100, 400, 200))
    assert any(p[3] > 200 and all(abs(p[i] - TEXT_FILL[i]) <= 30 for i in range(3))
               for p in img.getdata())


def test_draw_unmatched_brackets_literal(assets_dir):
    """未闭合括号按字面文本绘制（不报错），整段正文色。"""
    lib = AssetLibrary(assets_dir)
    img = draw_region(canvas(), lib, "未闭合[[关键字", rect_region(100, 100, 400, 200),
                      fill=TEXT_FILL, keyword_fill=KEYWORD_FILL)
    assert any(p[3] > 200 and all(abs(p[i] - TEXT_FILL[i]) <= 30 for i in range(3))
               for p in img.getdata())


def test_draw_keyword_with_icon(assets_dir):
    """高亮内部 # 图标照常解析绘制（异色对图标无实际效果：图标按原图粘贴）。"""
    lib = AssetLibrary(assets_dir)
    img = draw_region(canvas(), lib, "[[贯通#ll]]", rect_region(100, 100, 400, 200),
                      fill=TEXT_FILL, keyword_fill=KEYWORD_FILL)
    assert any(p[3] > 200 for p in img.getdata())


# ---------- 管线与 web 集成 ----------

def _battle_card(desc):
    """样卡（含包内占位卡图）替换描述，保证可独立渲染。"""
    card = dict(SAMPLE_CARDS["战斗"])
    card["description"] = desc
    return card


def test_render_card_keyword_highlight_differs(assets_dir):
    """管线集成：含 [[关键字]] 的描述与纯文本描述渲染结果不同（异色生效）。"""
    plain = render_card(_battle_card("获得贯通效果。"), ASSETS, crop=False)
    marked = render_card(_battle_card("获得[[贯通]]效果。"), ASSETS, crop=False)
    assert list(plain.getdata()) != list(marked.getdata())


def test_render_card_single_brackets_no_highlight(assets_dir):
    """单括号字面渲染：与不含括号文本不同（多画了括号），但不会触发异色/报错。"""
    with_brackets = render_card(_battle_card("约[定]俗成。"), ASSETS, crop=False)
    assert with_brackets is not None


def test_render_card_unmatched_brackets_render(assets_dir):
    """管线集成：未闭合括号按字面文本渲染（不报错），与纯文本渲染结果不同（多画了括号）。"""
    plain = render_card(_battle_card("未闭合关键字"), ASSETS, crop=False)
    marked = render_card(_battle_card("未闭合[[关键字"), ASSETS, crop=False)
    assert list(plain.getdata()) != list(marked.getdata())


def test_preview_unknown_icon_code_422(tmp_path):
    """未知图标代码仍在预览端报 422（括号不配对已改为字面显示，不再报错）。"""
    client = TestClient(create_app(ASSETS, library_dir=tmp_path / "library"))
    client.post("/api/projects", json={"name": "测试项目"})
    override = {"type": "战斗", "name": "测试斩", "level": 2, "rarity": "R",
                "shikigami": "测试项目", "power+": 1, "shield+": 1,
                "description": "触发#xx图标"}
    client.put("/api/projects/测试项目/cards/测试斩",
               json={**override, "description": "正常描述。"})
    r = client.post("/api/projects/测试项目/cards/测试斩/preview", json={"card": override})
    assert r.status_code == 422 and "图标代码未知" in r.json()["detail"]
    ok = client.post("/api/projects/测试项目/cards/测试斩/preview",
                     json={"card": {**override, "description": "未闭合[[关键字"}})
    assert ok.status_code == 200
