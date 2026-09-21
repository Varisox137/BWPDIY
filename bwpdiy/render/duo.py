"""协战双式神框（duo_frame）：牌框左上外侧叠加的双菱形头像组件。

每槽位自底向上：黑底板 back（其 alpha 即菱形掩膜）→ 头像（cover 适配槽位盒，
乘底板 alpha 裁菱形）→ 突出高光 highlight_1/2 → 派系小标（无相/缺派系不画）；
两槽位完成后 frame.png 双框线盖顶。

布局元素：{"kind": "duo_frame", "pos": [x, y], "size": [w, h]}——pos=双框中心
（两槽位中点），size=双框渲染尺寸（缺省 74×147）；槽位间距/派系偏移等内部几何
按比例从 size 推导，不开放布局键。头像内容取自 card["_duo"]（web 层按
shikigami1/2 注入的所属式神卡图，内部键不进 schema/yaml）；槽位数据缺失只画
底板+框（空菱形）。
"""

from pathlib import Path

from PIL import Image, ImageChops

from bwpdiy.render.artwork import fit_artwork
from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import FACTION_COLOR
from bwpdiy.render.common import paste_centered

# 内部几何基准（512 画布标定值，相对 size 缺省 74×147 按比例推导）
_BASE_SIZE = (74, 147)      # 双框渲染尺寸
_SLOT_DY = 35               # 槽位中心相对双框中心的竖直偏移（间距 70）
_BACK_SIZE = (88, 80)       # 槽位盒（黑底板）
_HIGHLIGHT_SIZE = 72        # 突出高光边长
_FACTION_SIZE = (26, 32)    # 派系小标 contain 框
_FACTION_OFFSET = (17, 23)  # 派系小标中心相对槽位中心偏移


def render_duo_frame(canvas: Image.Image, lib: AssetLibrary,
                     elem: dict, card: dict) -> Image.Image:
    size = elem.get("size") or list(_BASE_SIZE)
    sx, sy = size[0] / _BASE_SIZE[0], size[1] / _BASE_SIZE[1]
    cx, cy = elem["pos"]
    back = lib.duo("back")
    back_size = (max(1, round(_BACK_SIZE[0] * sx)), max(1, round(_BACK_SIZE[1] * sy)))
    back_fit = back.resize(back_size, Image.Resampling.LANCZOS)
    duo = card.get("_duo")
    slots = duo if isinstance(duo, list) else []
    out = canvas.copy()
    for i in range(2):
        center = (round(cx), round(cy + (_SLOT_DY if i else -_SLOT_DY) * sy))
        box = (center[0] - back_size[0] // 2, center[1] - back_size[1] // 2)
        out.paste(back_fit, box, back_fit)
        slot = slots[i] if i < len(slots) else None
        if isinstance(slot, dict):
            art_ref = slot.get("art")
            if isinstance(art_ref, dict) and art_ref.get("path"):
                art = _slot_artwork(lib, art_ref, card, back_size,
                                    back_fit.getchannel("A"))
                out.alpha_composite(art, box)
        hl_size = (max(1, round(_HIGHLIGHT_SIZE * sx)), max(1, round(_HIGHLIGHT_SIZE * sy)))
        out = paste_centered(out, lib.duo(f"highlight_{i + 1}"), center, hl_size)
        if isinstance(slot, dict):
            color = FACTION_COLOR.get(slot.get("faction", ""))
            if color is not None:
                badge = lib.duo(f"faction_{color}")
                badge_pos = (center[0] + round(_FACTION_OFFSET[0] * sx),
                             center[1] + round(_FACTION_OFFSET[1] * sy))
                badge_size = (max(1, round(_FACTION_SIZE[0] * sx)),
                              max(1, round(_FACTION_SIZE[1] * sy)))
                out = paste_centered(out, badge, badge_pos, badge_size)
    return paste_centered(out, lib.duo("frame"), (round(cx), round(cy)),
                          (round(size[0]), round(size[1])))


def _slot_artwork(lib: AssetLibrary, ref: dict, card: dict,
                  slot_box: tuple[int, int], mask: Image.Image) -> Image.Image:
    """槽位头像：复用卡图加载缓存与 cover 适配（目标尺寸=槽位盒），底板 alpha 作菱形掩膜。"""
    path = Path(ref["path"])
    if not path.is_absolute():
        path = Path(card.get("_base_dir", ".")) / path
    if not path.is_file():
        raise FileNotFoundError(f"双式神框头像缺失: {path}")
    orig_size, art = lib.artwork(path, ref.get("rotate", 0))
    art = fit_artwork(art, slot_box, ref.get("offset_x", 0), ref.get("offset_y", 0),
                      ref.get("scale", 1.0), cover_base=orig_size)
    art.putalpha(ImageChops.multiply(art.getchannel("A"), mask))
    return art
