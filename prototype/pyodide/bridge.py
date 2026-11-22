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


def _artwork(card, artwork_path, transform):
    card = copy.deepcopy(card)
    base_dir = USER_DIR if artwork_path else SAMPLE_ART.parent
    card["_base_dir"] = str(base_dir)
    art = {key: value for key, value in transform.items()
           if key in {"offset_x", "offset_y", "scale", "rotate"}}
    art["path"] = artwork_path or SAMPLE_ART.name
    card["artwork"] = {"images": [art]}
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
            card = copy.deepcopy(SAMPLE_CARDS[payload["card"]["type"]])
            override = {key: value for key, value in payload["card"].items()
                        if not key.startswith("_") and key != "artwork"}
            card.update(override)
            if card["type"] == "法术" and not card.get("evolve"):
                card.pop("power+", None)
                card.pop("health+", None)
            card = _artwork(card, payload.get("artwork_path"),
                            payload.get("artwork", {}))
            width = payload.get("width")
            if kind == "card":
                img = render_card(card, ASSETS, width=width)
            elif kind == "entity":
                img = render_entity(card, payload["state"], ASSETS, width=width)
            elif kind == "portrait":
                layouts = load_layouts(ASSETS)
                elem = layouts["协战"]["elements"]["duo_frame"]
                portrait = payload.get("portrait", {})
                art = {key: value for key, value in portrait.items()
                       if key in {"offset_x", "offset_y", "scale", "rotate"}}
                art["path"] = str(Path(card["_base_dir"]) / card["artwork"]["images"][0]["path"])
                img = render_portrait(get_library(ASSETS), elem, art,
                                      card.get("faction"),
                                      faction_style=card.get("faction_style"),
                                      with_frame=portrait.get("frame", True) is not False,
                                      width=width)
            else:
                raise ValueError(f"未知渲染类型：{kind}")
        last_render_error = ""
        return _png_info(img, started, kind)
    except Exception:
        import traceback
        last_render_error = traceback.format_exc()
        raise
