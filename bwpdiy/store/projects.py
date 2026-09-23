"""式神项目制卡牌库存取：文件系统即数据库，纯函数 + Path 注入（不依赖 FastAPI）。

目录结构（library/ 为用户数据，gitignore）：
    library/<项目名>/shikigami/<任意文件名>.yaml   式神卡，数量不限，卡名以文件内 name 字段为准
    library/<项目名>/cards/<任意文件名>.yaml       非式神卡，单项目上限 MAX_CARDS 张
    library/<项目名>/images/                       卡图原图
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import yaml

from .schema import SchemaError, validate_card

MAX_CARDS = 299  # 单项目非式神卡上限，对应 BWPro 大版本卡牌量
MAX_SHIKIGAMI = 49  # 单项目式神（主要式神）上限

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


# ---------- 项目 CRUD ----------

def list_projects(library: Path) -> list[str]:
    """library 下全部项目名（子目录），按名排序。"""
    library = Path(library)
    if not library.is_dir():
        return []
    return sorted(p.name for p in library.iterdir() if p.is_dir())


def create_project(library: Path, project: str) -> Path:
    """新建空项目骨架：cards/ 与 images/（不出厂默认式神卡）。"""
    pdir = _project_dir(library, project)
    if pdir.exists():
        raise StoreError(f"项目已存在：{project}", code="already_exists")
    (pdir / "cards").mkdir(parents=True)
    (pdir / "images").mkdir()
    return pdir


def rename_project(library: Path, old: str, new: str) -> Path:
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
    """项目内全部卡：{"shikigami": [...], "cards": [...]}，条目 {"stem", "name"}。

    name 取自文件内容（损坏/非映射时 None 仍列出）；各组按 name 排序（None 排最后）。
    """
    pdir = _require_project(library, project)
    result: dict[str, list[dict]] = {"shikigami": [], "cards": []}
    for sub in ("shikigami", "cards"):
        cdir = pdir / sub
        if not cdir.is_dir():
            continue
        for path in cdir.glob("*.yaml"):
            data = _read_yaml(path)
            name = data.get("name") if data else None
            result[sub].append({"stem": path.stem,
                                "name": name if isinstance(name, str) else None})
        result[sub].sort(key=lambda c: (c["name"] is None, c["name"] or ""))
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
    errors = validate_card(data)
    if errors:
        raise SchemaError(errors)
    sub = "shikigami" if data["type"] == "式神" else "cards"
    other = "cards" if sub == "shikigami" else "shikigami"
    if (pdir / other / f"{card_name}.yaml").is_file():
        raise StoreError(f"同名文件已存在于 {other}/ 目录（与卡牌类型不符）：{card_name}.yaml，"
                         f"请先删除或改名", code="already_exists")
    path = pdir / sub / f"{card_name}.yaml"
    is_new = not path.is_file()
    if is_new:
        existing = list((pdir / sub).glob("*.yaml")) if (pdir / sub).is_dir() else []
        limit = MAX_SHIKIGAMI if sub == "shikigami" else MAX_CARDS
        kind = "式神" if sub == "shikigami" else "卡牌"
        if len(existing) >= limit:
            raise StoreError(f"单项目{kind}上限 {limit} 张", code="forbidden")
    if sub == "shikigami":
        shiki_dir = pdir / "shikigami"
        for p in sorted(shiki_dir.glob("*.yaml")) if shiki_dir.is_dir() else []:
            if p.stem == card_name:
                continue
            other_data = _read_yaml(p)
            if other_data and other_data.get("name") == data["name"]:
                raise SchemaError([f"式神卡名「{data['name']}」与已有式神卡（{p.stem}.yaml）重复："
                                   f"引用按名关联，式神卡名必须唯一"])
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
    # 改名联动：旧盘内容（式神卡）name 变化时，改写全项目其他卡的式神引用
    if (sub == "shikigami" and isinstance(old_name, str) and old_name
            and old.get("type") == "式神" and old_name != data["name"]):
        updated = _rewrite_references(pdir, exclude=path, old=old_name, new=data["name"])
    _dump_yaml(path, data)
    if rename_to is not None:
        os.replace(path, rename_to)
        path = rename_to
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
