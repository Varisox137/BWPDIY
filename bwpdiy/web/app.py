"""FastAPI 编辑器服务（当前含布局配置工具 API）。"""

import json
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
        path = assets_dir / "layout.json"
        path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}

    @app.post("/api/preview")
    async def preview(request: dict):
        card_type = request.get("type")
        if card_type not in TYPE_FRAME_CODE:
            raise HTTPException(400, f"未知卡牌类型: {card_type}")
        card = dict(SAMPLE_CARDS[card_type])
        try:
            img = render_card(card, assets_dir, layout=request["layout"])
        except Exception as e:
            raise HTTPException(422, f"渲染失败: {e}") from e
        buf = BytesIO()
        img.save(buf, "PNG")
        return Response(buf.getvalue(), media_type="image/png")

    return app
