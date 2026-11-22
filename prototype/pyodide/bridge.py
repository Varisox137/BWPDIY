import copy
import json
import sys
import time
from io import BytesIO
from pathlib import Path

import PIL

from bwpdiy import __version__
from bwpdiy.render import render_card, render_entity
from bwpdiy.render.assets import get_library
from bwpdiy.render.duo import render_portrait
from bwpdiy.render.layout import load_layouts
from bwpdiy.render.mech import render_mechanism
from bwpdiy.web.sample_cards import SAMPLE_CARDS

ASSETS = Path("/work/assets")
SAMPLE_ART = Path("/work/bwpdiy/web/sample_art.png")
USER_DIR = Path("/work/user")
USER_DIR.mkdir(exist_ok=True)
last_render_info = "{}"
last_render_error = ""


def environment_info():
    return json.dumps({
        "python": sys.version.split()[0],
        "pillow": PIL.__version__,
        "bwpdiy": __version__,
        "fonts": [path.name for path in (ASSETS / "fonts").iterdir()],
    }, ensure_ascii=False)


def _artwork(card, artwork_path):
    card = copy.deepcopy(card)
    if artwork_path:
        card["_base_dir"] = str(USER_DIR)
        card["artwork"] = {"images": [{"path": artwork_path}]}
    else:
        card["_base_dir"] = str(SAMPLE_ART.parent)
        card["artwork"] = {"images": [{"path": SAMPLE_ART.name}]}
    return card


def _png_info(img, started, kind):
    global last_render_info
    output = BytesIO()
    img.save(output, "PNG")
    last_render_info = json.dumps({
        "kind": kind,
        "width": img.width,
        "height": img.height,
        "render_ms": round((time.perf_counter() - started) * 1000, 1),
        "png_bytes": output.tell(),
    }, ensure_ascii=False)
    return output.getvalue()


def browser_render(payload_json):
    global last_render_error
    started = time.perf_counter()
    try:
        payload = json.loads(payload_json)
        kind = payload["kind"]
        if kind == "mechanism":
            mechanism = payload["mechanism"]
            img = render_mechanism(
                mechanism, ASSETS, layout=load_layouts(ASSETS)["机制"],
                chars_per_line=mechanism.get("chars_per_line", 12))
        else:
            card = copy.deepcopy(SAMPLE_CARDS[payload.get("type", "战斗")])
            for field in ("name", "description"):
                if field in payload:
                    card[field] = payload[field]
            card = _artwork(card, payload.get("artwork_path"))
            width = payload.get("width")
            if kind == "card":
                img = render_card(card, ASSETS, width=width)
            elif kind == "entity":
                state = {
                    "level": 2,
                    "level_color": "yellow",
                    "frame_variant": "norm",
                    "power": 3,
                    "health": 4,
                    "combat_power": 1,
                    "shield": -2,
                    "energy": 2,
                    "art_scale": 1.0,
                }
                img = render_entity(card, state, ASSETS, width=width)
            elif kind == "portrait":
                layouts = load_layouts(ASSETS)
                elem = layouts["协战"]["elements"]["duo_frame"]
                art = card["artwork"]["images"][0]
                art["path"] = str(Path(card["_base_dir"]) / art["path"])
                img = render_portrait(get_library(ASSETS), elem, art,
                                      card.get("faction"), faction_style=2,
                                      width=width)
            else:
                raise ValueError(f"未知渲染类型：{kind}")
        last_render_error = ""
        return _png_info(img, started, kind)
    except Exception:
        import traceback
        last_render_error = traceback.format_exc()
        raise
