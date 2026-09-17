"""式神项目制卡牌库存取：文件系统即数据库，纯函数 + Path 注入（不依赖 FastAPI）。

目录结构（library/ 为用户数据，gitignore）：
    library/<项目名>/shikigami.yaml   式神卡（固定文件名，保留卡名 shikigami）
    library/<项目名>/cards/<卡名>.yaml  8 卡 + 衍生物
    library/<项目名>/images/           卡图原图
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import yaml

from .schema import SchemaError, validate_card

SHIKIGAMI_STEM = "shikigami"  # 保留卡名：项目的式神卡，固定存于 shikigami.yaml

_ILLEGAL_CHARS = set('<>:"/\\|?*')
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class StoreError(Exception):
    """存取层错误（项目/卡不存在、已存在、非法名等），消息为中文。"""


def _check_name(name: str, kind: str) -> None:
    """项目名/卡名安全：拒绝空名、路径分隔符、..、Windows 非法字符与保留设备名，防路径注入。"""
    if not isinstance(name, str) or not name.strip():
        raise StoreError(f"{kind}不能为空")
    if name != name.strip():
        raise StoreError(f"{kind}首尾不能是空白字符：「{name}」")
    if name in (".", "..") or ".." in name.split("/") or ".." in name.split("\\"):
        raise StoreError(f"{kind}不能是 . 或 ..：「{name}」")
    bad = _ILLEGAL_CHARS & set(name)
    if bad:
        raise StoreError(f"{kind}含非法字符 {''.join(sorted(bad))}：「{name}」（不允许路径分隔符与 <>:\"|?*）")
    if any(ord(c) < 32 for c in name):
        raise StoreError(f"{kind}含控制字符：「{name}」")
    if name.endswith("."):
        raise StoreError(f"{kind}不能以点结尾：「{name}」")
    if name.split(".")[0].upper() in _RESERVED_NAMES:
        raise StoreError(f"{kind}是 Windows 保留设备名：「{name}」")


def _project_dir(library: Path, project: str) -> Path:
    _check_name(project, "项目名")
    return Path(library) / project


def _require_project(library: Path, project: str) -> Path:
    pdir = _project_dir(library, project)
    if not pdir.is_dir():
        raise StoreError(f"项目不存在：{project}")
    return pdir


def _card_path(pdir: Path, card_name: str) -> Path:
    _check_name(card_name, "卡名")
    if card_name == SHIKIGAMI_STEM:
        return pdir / "shikigami.yaml"
    return pdir / "cards" / f"{card_name}.yaml"


# ---------- 项目 CRUD ----------

def list_projects(library: Path) -> list[str]:
    """library 下全部项目名（子目录），按名排序。"""
    library = Path(library)
    if not library.is_dir():
        return []
    return sorted(p.name for p in library.iterdir() if p.is_dir())


def create_project(library: Path, project: str) -> Path:
    """新建项目骨架：cards/、images/ 与默认式神卡（name=项目名，红莲 3/4）。"""
    pdir = _project_dir(library, project)
    if pdir.exists():
        raise StoreError(f"项目已存在：{project}")
    (pdir / "cards").mkdir(parents=True)
    (pdir / "images").mkdir()
    shikigami = {"type": "式神", "name": project, "faction": "红莲", "power": 3, "health": 4}
    _dump_yaml(pdir / "shikigami.yaml", shikigami)
    return pdir


def rename_project(library: Path, old: str, new: str) -> Path:
    src = _require_project(library, old)
    dst = _project_dir(library, new)
    if dst.exists():
        raise StoreError(f"项目已存在：{new}")
    src.rename(dst)
    return dst


def delete_project(library: Path, project: str) -> None:
    pdir = _require_project(library, project)
    if pdir.resolve().parent != Path(library).resolve():
        raise StoreError(f"项目路径越界：{project}")
    shutil.rmtree(pdir)


# ---------- 卡牌 CRUD ----------

def list_cards(library: Path, project: str) -> list[str]:
    """项目内全部卡名（文件 stem）：shikigami 居首（若存在），其余按名排序。"""
    pdir = _require_project(library, project)
    names = []
    if (pdir / "shikigami.yaml").is_file():
        names.append(SHIKIGAMI_STEM)
    cards_dir = pdir / "cards"
    if cards_dir.is_dir():
        names += sorted(p.stem for p in cards_dir.glob("*.yaml"))
    return names


def load_card(library: Path, project: str, card_name: str) -> dict:
    """读取卡牌 yaml；load 不做 schema 校验（校验在保存时执行）。"""
    path = _card_path(_require_project(library, project), card_name)
    if not path.is_file():
        raise StoreError(f"卡牌不存在：{project}/{card_name}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise StoreError(f"卡牌文件不是合法的 yaml：{project}/{card_name}（{e}）") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise StoreError(f"卡牌文件内容必须是 yaml 映射：{project}/{card_name}")
    return data


def save_card(library: Path, project: str, card_name: str, data: dict) -> Path:
    """schema 校验通过才落盘；cards/ 下不允许 type=式神，shikigami.yaml 必须是式神卡。"""
    pdir = _require_project(library, project)
    path = _card_path(pdir, card_name)
    errors = validate_card(data)
    if not errors:
        if card_name == SHIKIGAMI_STEM and data["type"] != "式神":
            errors.append(f"卡名 {SHIKIGAMI_STEM} 为保留名：shikigami.yaml 必须是式神卡（type: 式神）")
        elif card_name != SHIKIGAMI_STEM and data["type"] == "式神":
            errors.append("式神卡固定存于 shikigami.yaml，cards/ 下不允许 type: 式神")
        elif card_name != SHIKIGAMI_STEM and data["name"] != card_name:
            errors.append(f"字段 name（{data['name']}）必须与文件名（{card_name}）一致")
    if errors:
        raise SchemaError(errors)
    _dump_yaml(path, data)
    return path


def delete_card(library: Path, project: str, card_name: str) -> None:
    path = _card_path(_require_project(library, project), card_name)
    if card_name == SHIKIGAMI_STEM:
        raise StoreError("式神卡（shikigami.yaml）不可删除，可覆盖保存")
    if not path.is_file():
        raise StoreError(f"卡牌不存在：{project}/{card_name}")
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
