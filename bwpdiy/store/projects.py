"""式神项目制卡牌库存取：文件系统即数据库，纯函数 + Path 注入（不依赖 FastAPI）。

目录结构（library/ 为用户数据，gitignore）：
    library/<项目名>/shikigami/<任意文件名>.yaml   式神卡（主要式神上限 MAX_SHIKIGAMI 组）
    library/<项目名>/cards/<任意文件名>.yaml       非式神卡，单项目上限 MAX_CARDS 组
    library/<项目名>/images/                       卡图原图
    library/mechanisms/<机制名>[@<版本日期>].yaml  机制描述框（全局共享池，不属任何项目）

多版本（v1.6.0）：每版本一个 yaml 文件，「新版本」创建的文件名为 基础stem@YYYY-MM-DD
（无 @ 的旧文件=单版本，不强制迁移命名）。version_date 保存时校验合法日期、留空填当天。
卡牌按 id+name 均相同归组（id 缺省按空串），机制按 name 归组；数量限制按组数计。
同组各版本共享 layout 与 artwork（同图同设置）：保存任一版本后同步到组内其他版本。
退出时 cleanup_unused_images 删除各项目 images/ 下无引用的图片（含缺省 <id 或卡名>.png 引用）。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import date
from pathlib import Path

import yaml

from .schema import SchemaError, validate_card, validate_mechanism, _validate_version_date

MAX_CARDS = 299  # 单项目非式神卡上限，对应 BWPro 大版本卡牌量
MAX_SHIKIGAMI = 49  # 单项目式神（主要式神）上限
MECH_DIR_NAME = "mechanisms"  # 机制全局共享池目录（保留名，项目不可占用）

_ILLEGAL_CHARS = set('<>:"/\\|?*')
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
# 式神引用字段：改名联动时统一改写
_REF_FIELDS = ("shikigami", "shikigami1", "shikigami2")


class StoreError(Exception):
    """存取层错误（项目/卡不存在、已存在、非法名等），消息为中文。

    code 为语义码，供上层（web）分派状态码，不随消息措辞/内嵌资源名变化：
    not_found（404）/ already_exists（409）/ invalid_name、invalid_data、
    forbidden、path_escape（均 422）；缺省 invalid（422）。
    """

    def __init__(self, message: str, code: str = "invalid"):
        self.code = code
        super().__init__(message)


def _check_name(name: str, kind: str) -> None:
    """项目名/卡名安全：拒绝空名、路径分隔符、..、Windows 非法字符与保留设备名，防路径注入。"""
    if not isinstance(name, str) or not name.strip():
        raise StoreError(f"{kind}不能为空", code="invalid_name")
    if name != name.strip():
        raise StoreError(f"{kind}首尾不能是空白字符：「{name}」", code="invalid_name")
    if name in (".", "..") or ".." in name.split("/") or ".." in name.split("\\"):
        raise StoreError(f"{kind}不能是 . 或 ..：「{name}」", code="invalid_name")
    bad = _ILLEGAL_CHARS & set(name)
    if bad:
        raise StoreError(f"{kind}含非法字符 {''.join(sorted(bad))}：「{name}」（不允许路径分隔符与 <>:\"|?*）",
                         code="invalid_name")
    if any(ord(c) < 32 for c in name):
        raise StoreError(f"{kind}含控制字符：「{name}」", code="invalid_name")
    if name.endswith("."):
        raise StoreError(f"{kind}不能以点结尾：「{name}」", code="invalid_name")
    if name.split(".")[0].upper() in _RESERVED_NAMES:
        raise StoreError(f"{kind}是 Windows 保留设备名：「{name}」", code="invalid_name")


def _project_dir(library: Path, project: str) -> Path:
    _check_name(project, "项目名")
    return Path(library) / project


def _require_project(library: Path, project: str) -> Path:
    pdir = _project_dir(library, project)
    if not pdir.is_dir():
        raise StoreError(f"项目不存在：{project}", code="not_found")
    return pdir


def _find_card(pdir: Path, stem: str) -> Path | None:
    """读卡分派：先在 shikigami/ 再在 cards/ 找；都找不到返回 None。"""
    _check_name(stem, "卡名")
    for sub in ("shikigami", "cards"):
        path = pdir / sub / f"{stem}.yaml"
        if path.is_file():
            return path
    return None


def _read_yaml(path: Path):
    """宽松读取：损坏/非映射返回 None（供列表与联动遍历容错）。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _norm_date(v):
    """旧版带短横线日期（YYYY-MM-DD）归一为 8 位数字（v1.6.1）；其他值原样。"""
    if isinstance(v, str) and len(v) == 10 and v[4] == "-" and v[7] == "-":
        return v.replace("-", "")
    return v


def _expand_shorthand_id(pdir: Path, data: dict) -> None:
    """两位 id 简写展开（v1.6.2）：非协战卡有所属式神、且该式神 id 为 6 位数字时，
    id=两位数字 → <式神id><两位>（保存时展开，存储/卡图命名恒为全长）。
    协战（双式神前缀歧义）、无所属式神、引用不存在或式神 id 非 6 位时不展开。"""
    cid = data.get("id")
    if not isinstance(cid, str) or len(cid) != 2 or not cid.isdigit():
        return
    shiki = data.get("shikigami")
    if not shiki or data.get("type") == "协战":
        return
    sdir = pdir / "shikigami"
    for p in sorted(sdir.glob("*.yaml")) if sdir.is_dir() else []:
        other = _read_yaml(p)
        if other and other.get("name") == shiki:
            sid = other.get("id")
            if isinstance(sid, str) and len(sid) == 6 and sid.isdigit():
                data["id"] = sid + cid
            return


def _split_stem(stem: str) -> tuple[str, str]:
    """stem 拆 基础名@版本日期；无 @（或 @ 位置不合法）→ (stem, "")。"""
    base, sep, d = stem.rpartition("@")
    return (base, d) if sep and base and d else (stem, "")


def _group_key(data: dict) -> tuple[str, str]:
    """卡牌归组键：id+name 均相同才合并（id 缺省按空串）。"""
    return (data.get("id") or "", data.get("name") or "")


def _card_group(pdir: Path, sub: str, key: tuple[str, str]) -> list[tuple[Path, dict]]:
    """同组全部 (路径, 数据)（损坏/非映射文件不参与归组）。"""
    out = []
    cdir = pdir / sub
    for p in sorted(cdir.glob("*.yaml")) if cdir.is_dir() else []:
        data = _read_yaml(p)
        if data and _group_key(data) == key:
            out.append((p, data))
    return out


def _group_entries(items: list[tuple[Path, dict | None]]) -> list[dict]:
    """(路径, 数据|None) → 分组条目：stem=最新版本（date 最大、并列取 stem 大者；
    缺日期视为最旧），versions 按日期降序，count=版本数；损坏文件单列不合并。
    机制复用：_group_key 的 id 恒空、name=机制名，天然按名归组。"""
    groups: dict[tuple[str, str], list[tuple[Path, dict]]] = {}
    out = []
    for path, data in items:
        if data is None:
            out.append({"stem": path.stem, "name": None, "id": None,
                        "versions": [{"stem": path.stem, "date": ""}], "count": 1})
        else:
            groups.setdefault(_group_key(data), []).append((path, data))
    for (cid, name), versions in groups.items():
        vs = sorted(({"stem": p.stem, "date": _norm_date(d.get("version_date")) or ""}
                     for p, d in versions), key=lambda v: (v["date"], v["stem"]))
        out.append({"stem": vs[-1]["stem"], "name": name or None, "id": cid or None,
                    "versions": list(reversed(vs)), "count": len(vs)})
    out.sort(key=lambda c: (c["name"] is None, c["name"] or ""))
    return out


def _checked_new_date(value) -> str:
    """新版本日期：留空取当天；否则须合法 YYYY-MM-DD。"""
    vd = value or date.today().strftime("%Y%m%d")
    errors = _validate_version_date(vd)
    if errors:
        raise StoreError("；".join(errors), code="invalid_data")
    return vd


# ---------- 项目 CRUD ----------

def list_projects(library: Path) -> list[str]:
    """library 下全部项目名（子目录），按名排序；mechanisms/ 为机制共享池保留目录，不计入。"""
    library = Path(library)
    if not library.is_dir():
        return []
    return sorted(p.name for p in library.iterdir()
                  if p.is_dir() and p.name != MECH_DIR_NAME)


def create_project(library: Path, project: str) -> Path:
    """新建空项目骨架：cards/ 与 images/（不出厂默认式神卡）。"""
    if project == MECH_DIR_NAME:
        raise StoreError(f"项目名「{MECH_DIR_NAME}」为机制共享池保留目录名", code="invalid_name")
    pdir = _project_dir(library, project)
    if pdir.exists():
        raise StoreError(f"项目已存在：{project}", code="already_exists")
    (pdir / "cards").mkdir(parents=True)
    (pdir / "images").mkdir()
    return pdir


def rename_project(library: Path, old: str, new: str) -> Path:
    if new == MECH_DIR_NAME:
        raise StoreError(f"项目名「{MECH_DIR_NAME}」为机制共享池保留目录名", code="invalid_name")
    src = _require_project(library, old)
    dst = _project_dir(library, new)
    if dst.exists():
        raise StoreError(f"项目已存在：{new}", code="already_exists")
    src.rename(dst)
    return dst


def delete_project(library: Path, project: str) -> None:
    pdir = _require_project(library, project)
    if pdir.resolve().parent != Path(library).resolve():
        raise StoreError(f"项目路径越界：{project}", code="path_escape")
    shutil.rmtree(pdir)


# ---------- 卡牌 CRUD ----------

def list_cards(library: Path, project: str) -> dict[str, list[dict]]:
    """项目内全部卡（按 id+name 归组）：{"shikigami": [...], "cards": [...]}，
    条目 {stem(最新版本), name, id, versions:[{stem,date}] 降序, count}；组按 name 排序。
    """
    pdir = _require_project(library, project)
    result: dict[str, list[dict]] = {"shikigami": [], "cards": []}
    for sub in ("shikigami", "cards"):
        cdir = pdir / sub
        items = [(p, _read_yaml(p)) for p in cdir.glob("*.yaml")] if cdir.is_dir() else []
        result[sub] = _group_entries(items)
    return result


def load_card(library: Path, project: str, card_name: str) -> dict:
    """读取卡牌 yaml；load 不做 schema 校验（校验在保存时执行）。"""
    pdir = _require_project(library, project)
    path = _find_card(pdir, card_name)
    if path is None:
        raise StoreError(f"卡牌不存在：{project}/{card_name}", code="not_found")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise StoreError(f"卡牌文件不是合法的 yaml：{project}/{card_name}（{e}）",
                         code="invalid_data") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise StoreError(f"卡牌文件内容必须是 yaml 映射：{project}/{card_name}",
                         code="invalid_data")
    if "version_date" in data:
        data["version_date"] = _norm_date(data["version_date"])  # 旧带短横线数据读取归一
    return data


def save_card(library: Path, project: str, card_name: str, data: dict) -> tuple[Path, list[str]]:
    """schema 校验通过才落盘；按 type 分派目录（式神 → shikigami/，其余 → cards/）。

    文件名任意（卡名以文件内 name 为准，方便 BWPro 按 id 命名文件）；
    请求 stem 已存在于另一目录（类型与目录不符）报错指引。非式神卡新增超 MAX_CARDS 拒绝。
    式神卡 name 全项目唯一（引用按名关联）；改名时联动改写其余卡的 shikigami/shikigami1/
    shikigami2 引用（只换名不再校验）。
    返回 (落盘路径, 联动更新了的卡的 name 列表)。
    """
    pdir = _require_project(library, project)
    _check_name(card_name, "卡名")
    data = dict(data)
    if "version_date" in data:
        data["version_date"] = _norm_date(data["version_date"])
    _expand_shorthand_id(pdir, data)
    errors = validate_card(data)
    if errors:
        raise SchemaError(errors)
    if not data.get("version_date"):
        data["version_date"] = date.today().strftime("%Y%m%d")  # 留空按当前系统日期
    sub = "shikigami" if data["type"] == "式神" else "cards"
    other = "cards" if sub == "shikigami" else "shikigami"
    if (pdir / other / f"{card_name}.yaml").is_file():
        raise StoreError(f"同名文件已存在于 {other}/ 目录（与卡牌类型不符）：{card_name}.yaml，"
                         f"请先删除或改名", code="already_exists")
    path = pdir / sub / f"{card_name}.yaml"
    is_new = not path.is_file()
    if is_new and not _card_group(pdir, sub, _group_key(data)):
        # 数量限制按组计：同 id+name 的新版本不重复占名额；损坏文件不计入
        keys = set()
        cdir = pdir / sub
        for p in cdir.glob("*.yaml") if cdir.is_dir() else []:
            d = _read_yaml(p)
            if d:
                keys.add(_group_key(d))
        limit = MAX_SHIKIGAMI if sub == "shikigami" else MAX_CARDS
        kind = "式神" if sub == "shikigami" else "卡牌"
        if len(keys) >= limit:
            raise StoreError(f"单项目{kind}上限 {limit} 组", code="forbidden")
    if sub == "shikigami":
        shiki_dir = pdir / "shikigami"
        for p in sorted(shiki_dir.glob("*.yaml")) if shiki_dir.is_dir() else []:
            if p.stem == card_name:
                continue
            other_data = _read_yaml(p)
            # 同组（id+name 相同）的多版本允许同名；跨组同名拒绝（引用按名关联）
            if (other_data and other_data.get("name") == data["name"]
                    and _group_key(other_data) != _group_key(data)):
                raise SchemaError([f"式神卡名「{data['name']}」与已有式神卡（{p.stem}.yaml）重复："
                                   f"引用按名关联，式神卡名必须唯一（同 id+卡名的多版本除外）"])
    updated: list[str] = []
    old = _read_yaml(path) if not is_new else None
    old_name = old.get("name") if isinstance(old, dict) else None
    # 无 id 且文件名是卡名回退命名（stem == 旧卡名）：改名时同步重命名 yaml。
    # 有 id 或文件名本就与卡名脱钩（如数字 stem）时不动，供 BWPro 按 id 取文件。
    # 校验必须先于引用联动落盘：冲突/非法名报错时不得留下悬空引用
    rename_to: Path | None = None
    if (not is_new and not data.get("id") and isinstance(old_name, str)
            and old_name == card_name and data["name"] != card_name):
        try:
            _check_name(data["name"], "卡名")
        except StoreError as e:
            raise SchemaError([f"无 id 的卡牌配置文件按卡名命名：{e}；"
                               f"如需保留该卡名请填写 id（文件按 id 命名、与卡名脱钩）"]) from e
        target = pdir / sub / f"{data['name']}.yaml"
        # target != path：Windows 大小写不敏感下纯大小写改名 target 即自身，不算冲突
        if target != path and (target.is_file()
                               or (pdir / other / f"{data['name']}.yaml").is_file()):
            raise SchemaError([f"卡名「{data['name']}」对应的文件 {data['name']}.yaml 已存在，"
                               f"无法重命名；请修改卡名或填写 id"])
        rename_to = target
    # 版本日期被修改（仅原 stem 带 @日期时；无 @ 旧文件永不因日期改名）：
    # 重命名为 基础stem@新日期，目标冲突拒绝
    _base, old_date = _split_stem(card_name)
    if old_date and data["version_date"] != old_date:
        cur_base = _split_stem(rename_to.stem if rename_to is not None else card_name)[0]
        target = pdir / sub / f"{cur_base}@{data['version_date']}.yaml"
        current = rename_to if rename_to is not None else path
        if target != current and target.is_file():
            raise SchemaError([f"版本日期「{data['version_date']}」对应的文件 {target.name} 已存在，"
                               f"无法重命名；请更换日期"])
        rename_to = target
    # 改名联动：旧盘内容（式神卡）name 变化时，改写全项目其他卡的式神引用
    if (sub == "shikigami" and isinstance(old_name, str) and old_name
            and old.get("type") == "式神" and old_name != data["name"]):
        updated = _rewrite_references(pdir, exclude=path, old=old_name, new=data["name"])
    _dump_yaml(path, data)
    if rename_to is not None and rename_to != path:
        os.replace(path, rename_to)
        path = rename_to
    _propagate_shared(pdir, sub, path, data)
    return path, updated


def _rewrite_references(pdir: Path, exclude: Path, old: str, new: str) -> list[str]:
    """式神改名联动：遍历项目全部其他卡，shikigami/shikigami1/shikigami2 == 旧名的改为新名。"""
    updated = []
    for sub in ("shikigami", "cards"):
        cdir = pdir / sub
        if not cdir.is_dir():
            continue
        for path in sorted(cdir.glob("*.yaml")):
            if path == exclude:
                continue
            card = _read_yaml(path)
            if card is None:
                continue
            changed = False
            for field in _REF_FIELDS:
                if card.get(field) == old:
                    card[field] = new
                    changed = True
            if changed:
                _dump_yaml(path, card)
                name = card.get("name")
                updated.append(name if isinstance(name, str) else path.stem)
    return updated


def _propagate_shared(pdir: Path, sub: str, saved_path: Path, data: dict) -> None:
    """同组各版本共享 layout 与 artwork（同图同设置）：保存任一版本后同步到
    组内其他版本（有则覆盖、无则删除；内容相同跳过写盘）。"""
    for p, sibling in _card_group(pdir, sub, _group_key(data)):
        if p == saved_path:
            continue
        changed = False
        for field in ("layout", "artwork"):
            if field in data:
                if sibling.get(field) != data[field]:
                    sibling[field] = data[field]
                    changed = True
            elif field in sibling:
                del sibling[field]
                changed = True
        if changed:
            _dump_yaml(p, sibling)


def new_card_version(library: Path, project: str, card_name: str, version_date) -> Path:
    """复制该条目最新版本的全部内容创建新日期版本；日期留空取当天、与同组已有
    版本重复则拒绝。返回新文件路径（保存走 save_card：校验/共享同步同路）。"""
    pdir = _require_project(library, project)
    _check_name(card_name, "卡名")
    src = _find_card(pdir, card_name)
    if src is None:
        raise StoreError(f"卡牌不存在：{project}/{card_name}", code="not_found")
    sub = src.parent.name
    data = load_card(library, project, card_name)
    group = _card_group(pdir, sub, _group_key(data))
    latest_path, latest = max(group, key=lambda pd: (_norm_date(pd[1].get("version_date")) or "", pd[0].stem))
    vd = _checked_new_date(version_date)
    if any((_norm_date(d.get("version_date")) or "") == vd for _, d in group):
        raise StoreError(f"该卡牌已存在版本日期为 {vd} 的版本", code="already_exists")
    target = pdir / sub / f"{_split_stem(latest_path.stem)[0]}@{vd}.yaml"
    if target.is_file():
        raise StoreError(f"文件已存在：{target.name}", code="already_exists")
    new_data = dict(latest)
    new_data["version_date"] = vd
    path, _ = save_card(library, project, target.stem, new_data)
    return path


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def cleanup_unused_images(library: Path) -> list[str]:
    """删除各项目 images/ 下未被任何卡牌版本引用的图片（png/jpg/jpeg/webp）。

    引用=所有版本 artwork.images[].path；无显式 path 时缺省 <id 或卡名>.png 也算
    使用（与渲染回退口径一致）。返回删除文件的相对路径列表（供运行日志）。
    """
    library = Path(library)
    deleted = []
    for project in list_projects(library):
        pdir = library / project
        images_dir = pdir / "images"
        if not images_dir.is_dir():
            continue
        used: set[Path] = set()
        for sub in ("shikigami", "cards"):
            cdir = pdir / sub
            for path in cdir.glob("*.yaml") if cdir.is_dir() else []:
                data = _read_yaml(path)
                if not data:
                    continue
                artwork = data.get("artwork")
                images = artwork.get("images") if isinstance(artwork, dict) else None
                first = images[0] if isinstance(images, list) and images else None
                ref = first if isinstance(first, dict) else {}
                raw = ref.get("path")
                name = raw if isinstance(raw, str) and raw else f"{data.get('id') or data.get('name', '')}.png"
                ref_path = Path(name)
                used.add(ref_path if ref_path.is_absolute() else images_dir / ref_path)
        for img in images_dir.rglob("*"):
            if not img.is_file() or img.suffix.lower() not in _IMAGE_EXTS or img in used:
                continue
            try:
                img.unlink()
                deleted.append(str(img.relative_to(library)))
            except OSError:
                pass  # 删除失败（占用等）保留，下次退出再试
    return deleted


def delete_card(library: Path, project: str, card_name: str) -> None:
    """删除卡牌（式神卡可删；引用它的卡保留失效字符串，不级联）。"""
    pdir = _require_project(library, project)
    path = _find_card(pdir, card_name)
    if path is None:
        raise StoreError(f"卡牌不存在：{project}/{card_name}", code="not_found")
    path.unlink()


def _dump_yaml(path: Path, data: dict) -> None:
    """中文不转义、键序稳定（插入序）；临时文件 + os.replace 原子写，防半截 yaml。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------- 机制 CRUD（全局共享池 library/mechanisms/，文件名=机制名[@版本日期]） ----------

def _mech_dir(library: Path) -> Path:
    return Path(library) / MECH_DIR_NAME


def list_mechanisms(library: Path) -> list[dict]:
    """全部机制（按 name 归组）：[{stem(最新版本), name, versions 降序, count}]。"""
    mdir = _mech_dir(library)
    if not mdir.is_dir():
        return []
    return _group_entries([(p, _read_yaml(p)) for p in mdir.glob("*.yaml")])


def load_mechanism(library: Path, name: str) -> dict:
    """读取机制 yaml；load 不做 schema 校验（校验在保存时执行）。"""
    _check_name(name, "机制名")
    path = _mech_dir(library) / f"{name}.yaml"
    if not path.is_file():
        raise StoreError(f"机制不存在：{name}", code="not_found")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise StoreError(f"机制文件不是合法的 yaml：{name}（{e}）",
                         code="invalid_data") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise StoreError(f"机制文件内容必须是 yaml 映射：{name}", code="invalid_data")
    data.pop("marks", None)  # marks（唯一/瞬发角标）已移除：旧文件静默迁移，保存时不再写回
    if "version_date" in data:
        data["version_date"] = _norm_date(data["version_date"])
    return data


def save_mechanism(library: Path, name: str, data: dict) -> Path:
    """schema 校验通过才落盘；version_date 留空填当天。文件名=机制名[@版本日期]：
    无 @ 的旧文件保持仅机制名（不强制加日期）；带 @ 的文件名随机制名/日期同步
    重命名（目标已存在则拒绝）。返回落盘路径。"""
    _check_name(name, "机制名")
    data = dict(data)
    if "version_date" in data:
        data["version_date"] = _norm_date(data["version_date"])
    errors = validate_mechanism(data)
    if errors:
        raise SchemaError(errors)
    if not data.get("version_date"):
        data["version_date"] = date.today().isoformat()
    mdir = _mech_dir(library)
    mdir.mkdir(parents=True, exist_ok=True)
    path = mdir / f"{name}.yaml"
    _base, old_date = _split_stem(name)
    expected = f"{data['name']}@{data['version_date']}" if old_date else data["name"]
    rename_to: Path | None = None
    if expected != name:
        _check_name(data["name"], "机制名")
        target = mdir / f"{expected}.yaml"
        # target != path：Windows 大小写不敏感下纯大小写改名 target 即自身，不算冲突
        if target != path and target.is_file():
            raise SchemaError([f"「{expected}」对应的文件 {expected}.yaml 已存在，无法重命名"])
        rename_to = target
    _dump_yaml(path, data)
    if rename_to is not None and rename_to != path:
        os.replace(path, rename_to)
        path = rename_to
    return path


def new_mechanism_version(library: Path, name: str, version_date) -> Path:
    """复制该机制最新版本的全部内容创建新日期版本（按 name 归组）；日期留空取当天、
    与同组已有版本重复则拒绝。返回新文件路径。"""
    _check_name(name, "机制名")
    current = load_mechanism(library, name)  # 不存在 → not_found
    mdir = _mech_dir(library)
    group = []
    for p in sorted(mdir.glob("*.yaml")):
        d = _read_yaml(p)
        if d and d.get("name") == current["name"]:
            group.append((p, d))
    latest_path, latest = max(group, key=lambda pd: (_norm_date(pd[1].get("version_date")) or "", pd[0].stem))
    vd = _checked_new_date(version_date)
    if any((_norm_date(d.get("version_date")) or "") == vd for _, d in group):
        raise StoreError(f"该机制已存在版本日期为 {vd} 的版本", code="already_exists")
    target = mdir / f"{_split_stem(latest_path.stem)[0]}@{vd}.yaml"
    if target.is_file():
        raise StoreError(f"文件已存在：{target.name}", code="already_exists")
    new_data = dict(latest)
    new_data["version_date"] = vd
    return save_mechanism(library, target.stem, new_data)


def delete_mechanism(library: Path, name: str) -> None:
    _check_name(name, "机制名")
    path = _mech_dir(library) / f"{name}.yaml"
    if not path.is_file():
        raise StoreError(f"机制不存在：{name}", code="not_found")
    path.unlink()
