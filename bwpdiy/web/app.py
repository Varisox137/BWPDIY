"""FastAPI 编辑器服务（布局配置工具 + 项目/卡牌 REST API）。"""

import copy
import json
import os
import shutil
from io import BytesIO
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from bwpdiy import __version__
from bwpdiy.render.layout import load_layouts
from bwpdiy.render.pipeline import TYPE_FRAME_CODE, render_card
from bwpdiy.resources import default_library_dir
from bwpdiy.store import (
    SchemaError,
    StoreError,
    create_project,
    delete_card,
    delete_project,
    list_cards,
    list_projects,
    load_card,
    rename_project,
    save_card,
)
from bwpdiy.web.sample_cards import SAMPLE_CARDS

_STATIC = Path(__file__).parent / "static"
_SAMPLE_ART = Path(__file__).parent / "sample_art.png"  # 缺图占位（与样卡机制一致）


def create_app(assets_dir: Path, static_dir: Path | None = None,
               library_dir: Path | None = None,
               loopback_guard: bool = True) -> FastAPI:
    assets_dir = Path(assets_dir)
    static_dir = Path(static_dir) if static_dir else _STATIC
    library_dir = Path(library_dir) if library_dir else default_library_dir()
    app = FastAPI(title="BWPDIY")
    app.state.assets_dir = assets_dir
    app.state.library_dir = library_dir

    # Host 校验（防 DNS rebinding）：本机工具只应接受回环 Host——攻击者域名
    # 重绑定到 127.0.0.1 时浏览器带的是攻击者域名 Host，直接 400 堵住整条链。
    # testserver = FastAPI TestClient 默认 Host（浏览器不可能伪造该 Host 访问本机）。
    # 用户显式 --host 0.0.0.0 时由 __main__ 关掉本校验（并打告警）。
    _ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}
    if loopback_guard:
        @app.middleware("http")
        async def _host_guard(request, call_next):
            raw = request.headers.get("host", "")
            # IPv6 形如 [::1]:8630，先拆方括号再按冒号取主机名
            host = raw[1:].split("]")[0] if raw.startswith("[") else raw.split(":")[0]
            if host not in _ALLOWED_HOSTS:
                return JSONResponse(status_code=400,
                                    content={"detail": "非法 Host 头"})
            return await call_next(request)

    # store 异常 → HTTP 状态码：按 StoreError.code 分派（not_found 404、already_exists 409，
    # 其余 invalid_name/invalid_data/forbidden/path_escape 均 422），不受消息内嵌资源名影响
    _STATUS_BY_CODE = {"not_found": 404, "already_exists": 409}

    @app.exception_handler(StoreError)
    def _store_error(request, exc: StoreError):
        return JSONResponse(status_code=_STATUS_BY_CODE.get(exc.code, 422),
                            content={"detail": str(exc)})

    @app.exception_handler(SchemaError)
    def _schema_error(request, exc: SchemaError):
        return JSONResponse(status_code=422, content={"detail": exc.errors})

    @app.get("/")
    def editor_page():
        return FileResponse(static_dir / "editor.html")

    @app.get("/layout")
    def layout_page():
        # 布局设置已迁入编辑器主体页 tab（editor.html #layout），独立页退役，保留重定向兼容旧链接
        return RedirectResponse("/#layout")

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

    @app.get("/api/version")
    def get_version():
        return {"version": __version__}

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

    # ---------- 项目/卡牌 REST ----------

    @app.get("/api/projects")
    def get_projects():
        return JSONResponse(list_projects(library_dir))

    @app.post("/api/projects")
    async def post_project(request: dict):
        create_project(library_dir, request.get("name"))
        return {"ok": True}

    @app.put("/api/projects/{name}")
    async def put_project(name: str, request: dict):
        rename_project(library_dir, name, request.get("new_name"))
        return {"ok": True}

    @app.delete("/api/projects/{name}")
    def remove_project(name: str):
        delete_project(library_dir, name)
        return {"ok": True}

    @app.get("/api/projects/{project}/cards")
    def get_cards(project: str):
        return JSONResponse(list_cards(library_dir, project))

    @app.get("/api/projects/{project}/cards/{card}")
    def get_card(project: str, card: str):
        return JSONResponse(load_card(library_dir, project, card))

    @app.put("/api/projects/{project}/cards/{card}")
    async def put_card(project: str, card: str, request: dict):
        save_card(library_dir, project, card, request)
        return {"ok": True}

    @app.delete("/api/projects/{project}/cards/{card}")
    def remove_card(project: str, card: str):
        delete_card(library_dir, project, card)
        return {"ok": True}

    @app.post("/api/projects/{project}/cards/{card}/preview")
    async def preview_project_card(project: str, card: str, request: dict = Body(None)):
        card_data = load_card(library_dir, project, card)  # 卡牌不存在 → StoreError → 404
        card_data = _with_artwork_fallback(card_data, library_dir / project / "images")
        try:
            img = render_card(card_data, assets_dir,
                              layout=(request or {}).get("layout"), crop=False)
        except Exception as e:
            raise HTTPException(422, f"渲染失败: {e}") from e
        buf = BytesIO()
        img.save(buf, "PNG")
        return Response(buf.getvalue(), media_type="image/png")

    return app


def _with_artwork_fallback(card: dict, images_dir: Path) -> dict:
    """artwork 基准目录设为项目 images/；无 images 或首图文件缺失时回退占位图（与样卡一致）。

    store 刻意 load 不校验（支持手改 yaml），此处对 artwork 形状容错：
    artwork 非映射、images 非列表、首图非映射、path 非字符串一律视为无图，回退占位。
    """
    card = dict(card)
    card["_base_dir"] = str(images_dir)
    raw_artwork = card.get("artwork")
    artwork = dict(raw_artwork) if isinstance(raw_artwork, dict) else {}
    images = artwork.get("images")
    first = images[0] if isinstance(images, list) and images else None
    ref = dict(first) if isinstance(first, dict) else {}
    raw_path = ref.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raw_path = f"{card.get('name', '')}.png"
    art_path = Path(raw_path)
    if not art_path.is_absolute():
        art_path = images_dir / art_path
    if not art_path.is_file():
        ref = {k: ref[k] for k in ("offset_x", "offset_y", "scale")
               if k in ref and isinstance(ref[k], (int, float))}
        # 占位图在包内、不在项目 images/ 下：基准目录随之切到占位图所在目录，
        # 以通过渲染层的「卡图必须位于基准目录内」校验
        card["_base_dir"] = str(_SAMPLE_ART.parent)
        ref["path"] = _SAMPLE_ART.name
        artwork["images"] = [ref]
    card["artwork"] = artwork
    return card
