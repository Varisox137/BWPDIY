"""协战双式神框（duo_frame）：牌框左上外侧叠加的双菱形头像组件。

每槽位自底向上：黑底板 back（其 alpha 即菱形掩膜）→ 头像（cover 适配槽位盒，
乘底板 alpha 裁菱形）→ 斜方框（突出高光 highlight_i + 框线 frame_i，同一偏移）→
派系小标（无相/缺派系不画）。两槽位竖直对齐（x 一致），槽位2 只有竖直间距。

布局元素（仅协战类型，上下两框共用除 pos/slot2_dy 外的全部参数，共 10 项）：
- pos：上框底图（槽位1 基底）中心
- slot2_dy：下框底图相对上框底图的竖直间距（缺省 74）
- back_size：底图大小（等比 contain 进该边长方框，缺省 88）
- frame_size：斜方框大小（高光+框线同一尺寸框，缺省 75）
- frame_offset：斜方框相对底图中心的偏移（缺省 [0, 0]）
- faction_offset：派系标中心相对底图中心的偏移（缺省 [17, 23]）
- faction_size：派系标大小（等比 contain，缺省 32）
头像内容取自 card["_duo"]（web 层按 shikigami1/2 注入的所属式神卡图，内部键
不进 schema/yaml）；槽位数据缺失只画底板+框（空菱形，派系标按槽位 faction 照画，
供布局预览定位）。
"""

from pathlib import Path

from PIL import Image, ImageChops

from bwpdiy.render.artwork import fit_artwork
from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import FACTION_COLOR, _paste_element


def _load_art_cropped(lib: AssetLibrary, path: Path, rotate) -> Image.Image:
    """载入头像卡图（复用旋转缓存），先裁 alpha 透明边再交给 cover 适配居中：
    卡图常带透明边（如 512×512 两侧留空），不裁则可见内容不居中。"""
    _, art = lib.artwork(path, rotate)
    bbox = art.getchannel("A").getbbox()
    if bbox and bbox != (0, 0, art.width, art.height):
        art = art.crop(bbox)
    return art

# 内部几何缺省（512 画布标定值）
_DEFAULT_BACK_SIZE = 88     # 底图（黑底板 88×80，等比 contain）
_DEFAULT_FRAME_SIZE = 75    # 斜方框（高光 75×75 / 框线 77×78，等比 contain）
_DEFAULT_SLOT2_DY = 74
_DEFAULT_FACTION_OFFSET = [17, 23]
_DEFAULT_FACTION_SIZE = 32


def render_duo_frame(canvas: Image.Image, lib: AssetLibrary,
                     elem: dict, card: dict) -> Image.Image:
    p1 = elem["pos"]
    dy = elem.get("slot2_dy", _DEFAULT_SLOT2_DY)
    centers = [(round(p1[0]), round(p1[1])), (round(p1[0]), round(p1[1] + dy))]
    back_size = max(1, round(elem.get("back_size", _DEFAULT_BACK_SIZE)))
    frame_size = max(1, round(elem.get("frame_size", _DEFAULT_FRAME_SIZE)))
    faction_size = max(1, round(elem.get("faction_size", _DEFAULT_FACTION_SIZE)))
    frame_off = elem.get("frame_offset") or [0, 0]
    faction_off = elem.get("faction_offset") or _DEFAULT_FACTION_OFFSET
    duo = card.get("_duo")
    slots = duo if isinstance(duo, list) else []

    back = lib.duo("back")  # 裁透明边后等比 contain 进 back_size 方框
    back = back.crop(back.getchannel("A").getbbox())
    scale = back_size / max(back.size)
    back_box = (max(1, round(back.width * scale)), max(1, round(back.height * scale)))
    back_fit = back.resize(back_box, Image.Resampling.LANCZOS)
    out = canvas.copy()
    for i, center in enumerate(centers):
        # 底图（黑底板 + 头像菱形裁剪）
        box = (center[0] - back_box[0] // 2, center[1] - back_box[1] // 2)
        out.paste(back_fit, box, back_fit)
        slot = slots[i] if i < len(slots) else None
        if isinstance(slot, dict):
            art_ref = slot.get("art")
            if isinstance(art_ref, dict) and art_ref.get("path"):
                art = _slot_artwork(lib, art_ref, card, back_box,
                                    back_fit.getchannel("A"))
                out.alpha_composite(art, box)
        # 斜方框（高光 + 框线，共用 frame_offset 与 frame_size）
        target = (center[0] + round(frame_off[0]), center[1] + round(frame_off[1]))
        out = _paste_element(out, lib.duo(f"highlight_{i + 1}"), target,
                             (frame_size, frame_size))
        out = _paste_element(out, lib.duo(f"frame_{i + 1}"), target,
                             (frame_size, frame_size))
        # 派系小标
        if isinstance(slot, dict):
            color = FACTION_COLOR.get(slot.get("faction", ""))
            if color is not None:
                out = _paste_element(out, lib.duo(f"faction_{color}"),
                                     (center[0] + round(faction_off[0]),
                                      center[1] + round(faction_off[1])),
                                     (faction_size, faction_size))
    return out


def render_portrait(lib: AssetLibrary, elem: dict, art_ref: dict | None,
                    faction: str | None, scale: int = 2) -> Image.Image:
    """式神头像预览：单槽位合成（底图→头像菱形裁剪→斜方框→派系标），按布局 ×scale。

    取协战 duo_frame 布局参数（back_size/frame_size/faction_size/frame_offset/
    faction_offset）放大 scale 倍；art_ref 缺/缺图只画底图+框+派系标。
    返回整组件 tightest alpha bbox 裁剪后的 RGBA 图。
    """
    back_size = max(1, round(elem.get("back_size", _DEFAULT_BACK_SIZE) * scale))
    frame_size = max(1, round(elem.get("frame_size", _DEFAULT_FRAME_SIZE) * scale))
    faction_size = max(1, round(elem.get("faction_size", _DEFAULT_FACTION_SIZE) * scale))
    frame_off = elem.get("frame_offset") or [0, 0]
    faction_off = elem.get("faction_offset") or _DEFAULT_FACTION_OFFSET

    back = lib.duo("back")
    back = back.crop(back.getchannel("A").getbbox())
    bs = back_size / max(back.size)
    back_box = (max(1, round(back.width * bs)), max(1, round(back.height * bs)))
    back_fit = back.resize(back_box, Image.Resampling.LANCZOS)

    # 画布：容纳各部件（中心 + 偏移 ± 尺寸半径）的并集，最后按 alpha bbox 收紧
    ext = max(back_box[0] // 2, back_box[1] // 2,
              frame_size // 2 + max(abs(round(frame_off[0] * scale)),
                                    abs(round(frame_off[1] * scale))),
              faction_size // 2 + max(abs(round(faction_off[0] * scale)),
                                      abs(round(faction_off[1] * scale))))
    side = ext * 2 + 16
    center = (side // 2, side // 2)
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    box = (center[0] - back_box[0] // 2, center[1] - back_box[1] // 2)
    out.paste(back_fit, box, back_fit)
    if isinstance(art_ref, dict) and art_ref.get("path"):
        path = Path(art_ref["path"])
        if path.is_file():
            art = _load_art_cropped(lib, path, art_ref.get("rotate", 0))
            art = fit_artwork(art, back_box, art_ref.get("offset_x", 0) * scale,
                              art_ref.get("offset_y", 0) * scale,
                              art_ref.get("scale", 1.0))
            art.putalpha(ImageChops.multiply(art.getchannel("A"),
                                             back_fit.getchannel("A")))
            out.alpha_composite(art, box)
    out = _paste_element(out, lib.duo("highlight_1"),
                         (center[0] + round(frame_off[0] * scale),
                          center[1] + round(frame_off[1] * scale)),
                         (frame_size, frame_size))
    out = _paste_element(out, lib.duo("frame_1"),
                         (center[0] + round(frame_off[0] * scale),
                          center[1] + round(frame_off[1] * scale)),
                         (frame_size, frame_size))
    color = FACTION_COLOR.get(faction or "")
    if color is not None:
        out = _paste_element(out, lib.duo(f"faction_{color}"),
                             (center[0] + round(faction_off[0] * scale),
                              center[1] + round(faction_off[1] * scale)),
                             (faction_size, faction_size))
    bbox = out.getchannel("A").getbbox()
    return out.crop(bbox) if bbox else out


def _slot_artwork(lib: AssetLibrary, ref: dict, card: dict,
                  slot_box: tuple[int, int], mask: Image.Image) -> Image.Image:
    """槽位头像：复用卡图加载缓存与 cover 适配（目标尺寸=槽位盒），底板 alpha 作菱形掩膜。"""
    path = Path(ref["path"])
    if not path.is_absolute():
        path = Path(card.get("_base_dir", ".")) / path
    if not path.is_file():
        raise FileNotFoundError(f"双式神框头像缺失: {path}")
    art = _load_art_cropped(lib, path, ref.get("rotate", 0))
    art = fit_artwork(art, slot_box, ref.get("offset_x", 0), ref.get("offset_y", 0),
                      ref.get("scale", 1.0))
    art.putalpha(ImageChops.multiply(art.getchannel("A"), mask))
    return art
