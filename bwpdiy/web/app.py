"""FastAPI 编辑器服务（当前含布局配置工具 API）。"""

import copy
import json
import os
import shutil
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from bwpdiy.render.layout import load_layouts
from bwpdiy.render.pipeline import TYPE_FRAME_CODE, render_card
from bwpdiy.web.sample_cards import SAMPLE_CARDS

_STATIC = Path(__file__).parent / "static"


def create_app(assets_dir: Path, static_dir: Path | None = None) -> FastAPI:
    assets_dir = Path(assets_dir)
    static_dir = Path(static_dir) if static_dir else _STATIC
    app = FastAPI(title="BWPDIY")
    app.state.assets_dir = assets_dir

    @app.get("/")
    @app.get("/layout")
    def layout_page():
        return FileResponse(static_dir / "layout.html")

    @app.get("/api/layout")
    def get_layout():
        return JSONResponse(load_layouts(assets_dir))

    @app.put("/api/layout")
    async def put_layout(request: dict):
        # 最小形状校验：非空 dict，每个类型值须与 load_layouts 产物同构；
        # 不强制六类型齐全（部分保存、缺省回退默认是特性）
        if not request:
            raise HTTPException(422, "布局为空：拒绝覆盖现有配置")
        for card_type, type_layout in request.items():
            if (not isinstance(type_layout, dict)
                    or "elements" not in type_layout
                    or "text_regions" not in type_layout):
                raise HTTPException(
                    422, f"布局形状非法: 类型 {card_type} 必须是含 elements/text_regions 键的对象")
        path = assets_dir / "layout.json"
        data = json.dumps(request, ensure_ascii=False, indent=2)
        try:
            if path.is_file():
                shutil.copy2(path, path.with_name(path.name + ".bak"))
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(data, encoding="utf-8")
            os.replace(tmp, path)
        except OSError as e:
            raise HTTPException(422, f"布局写盘失败: {e}") from e
        return {"ok": True}

    @app.get("/api/samples")
    def get_samples():
        """六类型预览样卡字段（剥内部键/卡图），供 GUI 卡牌内容输入框预填。"""
        return JSONResponse({
            t: {k: v for k, v in card.items()
                if not k.startswith("_") and k != "artwork"}
            for t, card in SAMPLE_CARDS.items()
        })

    @app.post("/api/preview")
    async def preview(request: dict):
        card_type = request.get("type")
        if card_type not in TYPE_FRAME_CODE:
            raise HTTPException(400, f"未知卡牌类型: {card_type}")
        card = copy.deepcopy(SAMPLE_CARDS[card_type])
        override = request.get("card")
        if override is not None:
            if not isinstance(override, dict):
                raise HTTPException(400, "card 必须是对象")
            for k, v in override.items():
                # 嵌套 artwork 按键合并而非整体替换（避免丢 images 列表）
                if k == "artwork" and isinstance(v, dict):
                    card["artwork"].update(v)
                else:
                    card[k] = v
        try:
            img = render_card(card, assets_dir, layout=request["layout"], crop=False)
        except Exception as e:
            raise HTTPException(422, f"渲染失败: {e}") from e
        buf = BytesIO()
        img.save(buf, "PNG")
        return Response(buf.getvalue(), media_type="image/png")

    return app
