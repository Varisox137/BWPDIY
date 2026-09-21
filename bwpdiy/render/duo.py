"""协战双式神框（duo_frame）：牌框左上外侧叠加的双菱形头像组件。

每槽位自底向上：黑底板 back（其 alpha 即菱形掩膜）→ 头像（cover 适配槽位盒，
乘底板 alpha 裁菱形）；随后统一叠 斜方框（突出高光 highlight_i + 框线 frame_i，
同一偏移）→ 派系小标（无相/缺派系不画）。

布局元素（仅协战类型）：
- pos：槽位1 基底中心；slot2_offset：槽位2 基底相对槽位1 的偏移（缺省 [0, 74]）
- size：基底渲染尺寸（缺省 88×80，全组件等比缩放基准）
- frame_offset_1/2：斜方框相对本槽位基底中心的偏移（缺省 [0, 0]）
- faction_offset_1/2：派系小标中心相对本槽位基底中心的偏移（缺省 [17, 23]）
头像内容取自 card["_duo"]（web 层按 shikigami1/2 注入的所属式神卡图，内部键
不进 schema/yaml）；槽位数据缺失只画底板+框（空菱形，派系标按槽位 faction 照画，
供布局预览定位）。
"""

from pathlib import Path

from PIL import Image, ImageChops

from bwpdiy.render.artwork import fit_artwork
from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import FACTION_COLOR
from bwpdiy.render.common import paste_centered

# 内部几何基准（512 画布标定值；size 缺省=基底原尺寸，其余按 sx/sy 等比缩放）
_BACK_SIZE = (88, 80)       # 槽位盒（黑底板）
_HIGHLIGHT_SIZE = 72        # 突出高光边长
_FRAME_SIZE = (74, 75)      # 单槽位框线（双框拆半后缩放目标）
_FACTION_SIZE = (26, 32)    # 派系小标 contain 框
_DEFAULT_SLOT2_OFFSET = [0, 74]
_DEFAULT_FACTION_OFFSET = [17, 23]


def _scaled(size: tuple[int, int], sx: float, sy: float) -> tuple[int, int]:
    return (max(1, round(size[0] * sx)), max(1, round(size[1] * sy)))


def render_duo_frame(canvas: Image.Image, lib: AssetLibrary,
                     elem: dict, card: dict) -> Image.Image:
    size = elem.get("size") or list(_BACK_SIZE)
    sx, sy = size[0] / _BACK_SIZE[0], size[1] / _BACK_SIZE[1]
    slot2_off = elem.get("slot2_offset") or _DEFAULT_SLOT2_OFFSET
    p1 = elem["pos"]
    centers = [(round(p1[0]), round(p1[1])),
               (round(p1[0] + slot2_off[0]), round(p1[1] + slot2_off[1]))]
    duo = card.get("_duo")
    slots = duo if isinstance(duo, list) else []

    back = lib.duo("back")
    back_size = _scaled(_BACK_SIZE, sx, sy)
    back_fit = back.resize(back_size, Image.Resampling.LANCZOS)
    out = canvas.copy()
    # 第一遍：底板 + 头像
    for i, center in enumerate(centers):
        box = (center[0] - back_size[0] // 2, center[1] - back_size[1] // 2)
        out.paste(back_fit, box, back_fit)
        slot = slots[i] if i < len(slots) else None
        if isinstance(slot, dict):
            art_ref = slot.get("art")
            if isinstance(art_ref, dict) and art_ref.get("path"):
                art = _slot_artwork(lib, art_ref, card, back_size,
                                    back_fit.getchannel("A"))
                out.alpha_composite(art, box)
    # 第二遍：斜方框（高光 + 框线，共用 frame_offset_i）
    for i, center in enumerate(centers):
        off = elem.get(f"frame_offset_{i + 1}") or [0, 0]
        target = (center[0] + round(off[0]), center[1] + round(off[1]))
        out = paste_centered(out, lib.duo(f"highlight_{i + 1}"), target,
                             _scaled((_HIGHLIGHT_SIZE,) * 2, sx, sy))
        out = paste_centered(out, lib.duo(f"frame_{i + 1}"), target,
                             _scaled(_FRAME_SIZE, sx, sy))
    # 第三遍：派系小标
    for i, center in enumerate(centers):
        slot = slots[i] if i < len(slots) else None
        if not isinstance(slot, dict):
            continue
        color = FACTION_COLOR.get(slot.get("faction", ""))
        if color is None:
            continue
        off = elem.get(f"faction_offset_{i + 1}") or _DEFAULT_FACTION_OFFSET
        target = (center[0] + round(off[0]), center[1] + round(off[1]))
        out = paste_centered(out, lib.duo(f"faction_{color}"), target,
                             _scaled(_FACTION_SIZE, sx, sy))
    return out


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
