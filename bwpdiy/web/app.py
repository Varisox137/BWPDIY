"""FastAPI 编辑器服务（布局配置工具 + 项目/卡牌 REST API）。

空闲自动终止（防占用）：连续 idle_timeout 秒（默认 2h）无任何操作则进程退出。
「操作」= HTTP 请求，但前端自动轮询（/api/update/check，每 1min）不算——
否则挂着页面就永远不空闲。GUI 侧对所有请求失败弹「连接已断开」提示。
"""

import copy
import json
import os
import shutil
import threading
import time
from io import BytesIO
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from PIL import Image

from bwpdiy import __version__
from bwpdiy import updater
from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.duo import render_portrait
from bwpdiy.render.layout import get_type_layout, load_layouts, merge_card_layout
from bwpdiy.render.pipeline import ARTWORK_MAX_PIXELS, TYPE_FRAME_CODE, render_card
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

# 空闲统计排除的被动轮询路径（前端每 1min 自动请求，不算用户操作）
_IDLE_EXCLUDE_PATHS = {"/api/update/check"}


def create_app(assets_dir: Path, static_dir: Path | None = None,
               library_dir: Path | None = None,
               loopback_guard: bool = True,
               idle_timeout: float = 7200.0,
               on_idle=None) -> FastAPI:
    assets_dir = Path(assets_dir)
    static_dir = Path(static_dir) if static_dir else _STATIC
    library_dir = Path(library_dir) if library_dir else default_library_dir()
    app = FastAPI(title="BWPDIY")
    app.state.assets_dir = assets_dir
    app.state.library_dir = library_dir
    app.state.last_activity = time.time()

    @app.middleware("http")
    async def _activity_track(request, call_next):
        if request.url.path not in _IDLE_EXCLUDE_PATHS:
            app.state.last_activity = time.time()
        return await call_next(request)

    if idle_timeout > 0:
        def _watchdog():
            interval = min(60.0, max(0.05, idle_timeout / 4))
            while True:
                time.sleep(interval)
                if time.time() - app.state.last_activity >= idle_timeout:
                    if on_idle is not None:  # 测试注入
                        on_idle()
                    else:
                        print(f"已连续 {idle_timeout / 3600:g} 小时无操作，"
                              "服务自动终止（防占用），重新启动即可继续使用。", flush=True)
                        os._exit(0)
                    return

        threading.Thread(target=_watchdog, daemon=True,
                         name="bwpdiy-idle-watchdog").start()

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

    # ---------- 自动更新（仅 frozen exe 可一键替换；检查对全模式开放） ----------

    @app.get("/api/update/check")
    def update_check():
        return JSONResponse(updater.check_update())

    @app.post("/api/update/apply")
    def update_apply():
        # 重新拉取 release 信息（不信前端传来的 URL），有更新才下载
        info = updater.check_update()
        if not info.get("has_update"):
            raise HTTPException(422, info.get("error") or "当前已是最新版本")
        try:
            latest = updater.download_and_schedule_restart(info)
        except Exception as e:
            raise HTTPException(422, f"更新失败: {e}") from e
        return {"ok": True, "latest": latest, "message": "下载完成，程序将退出并自动更新重启"}

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
                if k.startswith("_"):
                    continue  # 内部键（如 _base_dir/_duo）不接受外部注入（纵深防御）
                # 嵌套 artwork 按键合并而非整体替换（避免丢 images 列表）
                if k == "artwork" and isinstance(v, dict):
                    card["artwork"].update(v)
                else:
                    card[k] = v
        try:
            # 协战样卡勾双式神框时注入占位派系（无项目上下文）：空菱形+派系标，
            # 供布局页定位派系标（与官方示例的空槽位观感一致）
            if (card.get("type") == "协战" and card.get("duo_frame")
                    and "_duo" not in card):
                card["_duo"] = [{"faction": "苍叶"}, {"faction": "青岚"}]
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
        # save_card 返回 (path, updated)：式神卡改名时自动联动同项目卡的所属式神引用，
        # updated 为被更新卡的卡名列表（前端据此提示并刷新列表）；
        # stem 为最终文件名——无 id 卡改名时服务端已把 yaml 重命名为新卡名，前端据此切换选中
        path, updated = save_card(library_dir, project, card, request)
        return {"ok": True, "updated": updated, "stem": path.stem}

    @app.delete("/api/projects/{project}/cards/{card}")
    def remove_card(project: str, card: str):
        delete_card(library_dir, project, card)
        return {"ok": True}

    @app.post("/api/projects/{project}/cards/{card}/preview")
    async def preview_project_card(project: str, card: str, request: dict = Body(None)):
        card_data = load_card(library_dir, project, card)  # 卡牌不存在 → StoreError → 404
        override = (request or {}).get("card")
        if override is not None:
            # 编辑期实时预览：整体替换为表单数据（含未保存修改与 artwork offset/scale），
            # 卡图路径仍受 _with_artwork_fallback 的 images/ 基准目录约束，越界由渲染层拒绝
            if not isinstance(override, dict):
                raise HTTPException(400, "card 必须是对象")
            card_data = copy.deepcopy(override)
        card_data = _with_artwork_fallback(card_data, library_dir / project / "images")
        if card_data.get("type") == "协战" and card_data.get("duo_frame"):
            card_data["_duo"] = [_duo_slot(library_dir, project, card_data.get(f))
                                 for f in ("shikigami1", "shikigami2")]
        try:
            req_layout = (request or {}).get("layout")
            if req_layout is None and isinstance(card_data.get("layout"), dict):
                # 单卡布局覆盖：卡面 layout 段按键合并覆盖该类型全局布局（导出同路）
                base = get_type_layout(load_layouts(Path(assets_dir)), card_data["type"])
                req_layout = merge_card_layout(base, card_data["layout"])
            img = render_card(card_data, assets_dir, layout=req_layout, crop=False)
        except Exception as e:
            raise HTTPException(422, f"渲染失败: {e}") from e
        buf = BytesIO()
        img.save(buf, "PNG")
        return Response(buf.getvalue(), media_type="image/png")

    @app.post("/api/projects/{project}/cards/{card}/portrait_preview")
    async def portrait_preview(project: str, card: str, request: dict = Body(None)):
        """式神头像预览：双式神框单槽位（底图+头像+斜方框+派系标），按布局 2 倍渲染。

        变换取表单/落盘的 portrait 段（缺省 0/0/1/0）；派系标随式神 faction；
        缺卡图只画空槽位。布局取当前 assets/layout.json 协战 duo_frame 元素。
        """
        card_data = load_card(library_dir, project, card)
        override = (request or {}).get("card")
        if override is not None:
            if not isinstance(override, dict):
                raise HTTPException(400, "card 必须是对象")
            card_data = copy.deepcopy(override)
        if card_data.get("type") != "式神":
            raise HTTPException(400, "头像预览仅适用于式神卡")
        elem = load_layouts(Path(assets_dir)).get("协战", {}).get(
            "elements", {}).get("duo_frame")
        if elem is None:
            raise HTTPException(422, "渲染失败: 布局缺失协战 duo_frame 元素")
        # 卡图路径解析与越界防护口径同 _duo_slot；缺图 → None（空槽位）
        portrait = card_data.get("portrait")
        portrait = portrait if isinstance(portrait, dict) else {}
        art_ref = _resolve_art_ref(card_data, library_dir / project / "images",
                                   transform=portrait)
        try:
            lib = AssetLibrary(Path(assets_dir))
            # 头像框开关（portrait.frame，缺省 true）：不画斜方框与派系标，仅菱形裁剪头像
            with_frame = portrait.get("frame", True) is not False
            img = render_portrait(lib, elem, art_ref, card_data.get("faction"),
                                  faction_style=card_data.get("faction_style"),
                                  with_frame=with_frame)
        except Exception as e:
            raise HTTPException(422, f"渲染失败: {e}") from e
        buf = BytesIO()
        img.save(buf, "PNG")
        return Response(buf.getvalue(), media_type="image/png")

    _ART_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

    @app.post("/api/projects/{project}/cards/{card}/artwork")
    async def post_artwork(project: str, card: str, request: Request):
        """上传卡图：裸字节 body + filename 查询参数（只取扩展名）。

        落盘名 = <id 或卡名><ext>（id 字段可留空，留空回退卡名）：对齐 BWPro 按 id 取
        卡图的约定；同 id/卡名复用同名文件（覆盖写），不同版本不同 id 各自成文。
        修改 id 不重命名已有卡图（其他卡可能正引用该文件）；不做旧图清理（孤儿文件用户自理）。
        图片真实性/像素上限在写盘前校验；写盘后走 save_card 更新 artwork.images[0].path
        （保留已有 offset/scale），schema 不过则删图回滚（仅当本次真正写了新文件）。
        """
        ext = Path(request.query_params.get("filename", "")).suffix.lower()
        if ext not in _ART_EXTS:
            raise HTTPException(422, f"不支持的图片格式「{ext or '无扩展名'}」，支持 png/jpg/jpeg/webp")
        data = await request.body()
        if not data:
            raise HTTPException(422, "上传内容为空")
        try:
            img = Image.open(BytesIO(data))
            if img.width * img.height > ARTWORK_MAX_PIXELS:
                raise HTTPException(422, f"图片过大: {img.width}×{img.height} 超像素上限")
            img.load()  # 全量解码，拒绝伪造/截断图片
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(422, f"不是有效的图片文件: {e}") from e
        card_data = load_card(library_dir, project, card)  # 卡牌不存在 → 404；卡名合法性在此校验
        stem = card_data.get("id") or card_data.get("name", "")
        stem = "".join(c for c in str(stem) if c not in '<>:"/\\|?*').strip().rstrip(". ")
        _WIN_RESERVED = {"CON", "PRN", "AUX", "NUL",
                         *(f"COM{i}" for i in range(1, 10)),
                         *(f"LPT{i}" for i in range(1, 10))}
        if not stem or stem.upper() in _WIN_RESERVED:
            raise HTTPException(422, "卡名/id 无法用作文件名：请先填写卡名（或 id）")
        raw_artwork = card_data.get("artwork")
        artwork = dict(raw_artwork) if isinstance(raw_artwork, dict) else {}
        raw_images = artwork.get("images")
        old_images = raw_images if isinstance(raw_images, list) else []
        first = dict(old_images[0]) if old_images and isinstance(old_images[0], dict) else {}
        filename = f"{stem}{ext}"
        first["path"] = filename
        artwork["images"] = [first, *old_images[1:]]
        card_data["artwork"] = artwork
        images_dir = library_dir / project / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        target = images_dir / filename
        try:
            old_bytes = target.read_bytes() if target.is_file() else None
            if old_bytes != data:
                target.write_bytes(data)  # 同名同内容：复用跳过写盘
        except OSError as e:
            raise HTTPException(422, f"卡图写盘失败: {e}") from e
        try:
            save_card(library_dir, project, card, card_data)
        except Exception:
            if old_bytes is None:
                target.unlink(missing_ok=True)  # schema 不过：删图回滚，不留孤儿文件
            elif old_bytes != data:
                target.write_bytes(old_bytes)  # 同名覆盖：还原原文件内容
            raise
        return {"ok": True, "path": filename}

    return app


def _resolve_art_ref(card: dict, images_dir: Path,
                     transform: dict | None = None) -> dict | None:
    """首图路径解析：缺省 <id 或卡名>.png（id 留空回退卡名），相对路径基于项目 images/；
    resolve(strict)+relative_to 双重越界防护（符号链接被 strict resolve 解析后拦截）。
    缺图/越界 → None。transform 非空时按四键提取变换（缺省 0/0/1.0/0，bool 不算数）。"""
    images = card.get("artwork", {})
    images = images.get("images") if isinstance(images, dict) else None
    first = images[0] if isinstance(images, list) and images else None
    ref = dict(first) if isinstance(first, dict) else {}
    raw_path = ref.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raw_path = f"{card.get('id') or card.get('name', '')}.png"
    art_path = Path(raw_path)
    if not art_path.is_absolute():
        art_path = images_dir / art_path
    try:
        art_path = art_path.resolve(strict=True)
        art_path.relative_to(images_dir.resolve())
    except (OSError, ValueError):
        return None
    art = {"path": str(art_path)}
    if transform is not None:
        for k, default in (("offset_x", 0), ("offset_y", 0),
                           ("scale", 1.0), ("rotate", 0)):
            v = transform.get(k)
            art[k] = (v if isinstance(v, (int, float))
                      and not isinstance(v, bool) else default)
    return art


def _duo_slot(library_dir: Path, project: str, shikigami_name) -> dict | None:
    """双式神框单槽位数据：按名在项目 shikigami/ 找式神卡，取首图（缺省口径同
    pipeline._artwork_ref）与派系；缺式神（未引用/未找到）→ None（空槽位）。

    返回 {"faction": 派系, "art": {...}}：faction 可缺（渲染层无相/缺派系不画小标）；
    图缺失/越出 images/ 时 slot 保留 faction 但无 art（空菱形+派系标，便于布局定位）。
    """
    if not isinstance(shikigami_name, str) or not shikigami_name:
        return None
    pdir = library_dir / project
    entries = list_cards(library_dir, project).get("shikigami", [])
    stem = next((e["stem"] for e in entries if e["name"] == shikigami_name), None)
    if stem is None:
        return None
    shiki = load_card(library_dir, project, stem)
    slot = {}
    faction = shiki.get("faction")
    if isinstance(faction, str):
        slot["faction"] = faction
    style = shiki.get("faction_style")  # 派系标样式随式神设置（缺省渲染层回退 2）
    if isinstance(style, int) and not isinstance(style, bool):
        slot["faction_style"] = style
    images_dir = pdir / "images"
    # 头像变换取式神卡 portrait 段（缺省 0/0/1/0 自动居中填满），不复用卡图变换
    portrait = shiki.get("portrait")
    portrait = portrait if isinstance(portrait, dict) else {}
    art = _resolve_art_ref(shiki, images_dir, transform=portrait)
    if art is not None:
        slot["art"] = art
    return slot


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
        raw_path = f"{card.get('id') or card.get('name', '')}.png"  # 缺省 <id>.png，id 留空回退卡名
    art_path = Path(raw_path)
    if not art_path.is_absolute():
        art_path = images_dir / art_path
    if not art_path.is_file():
        ref = {k: ref[k] for k in ("offset_x", "offset_y", "scale", "rotate")
               if k in ref and isinstance(ref[k], (int, float))}
        # 占位图在包内、不在项目 images/ 下：基准目录随之切到占位图所在目录，
        # 以通过渲染层的「卡图必须位于基准目录内」校验
        card["_base_dir"] = str(_SAMPLE_ART.parent)
        ref["path"] = _SAMPLE_ART.name
        artwork["images"] = [ref]
    card["artwork"] = artwork
    return card
