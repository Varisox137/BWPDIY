"""PyInstaller onefile 构建脚本：生成 releases/BWPDIY-v{版本}.exe。

用法（Windows Git Bash）：
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe scripts/build_exe.py

资源内嵌策略：assets/ 全量（排除 legacy/、frames/unprocessed/、psd_export/ 与 *.psd/*.bak），
包内数据文件（default_layout.json、web/static/、web/sample_art.png）按包路径映射。
中间产物在 build/、dist/（均 gitignore），最终 exe 复制到 releases/。
"""

import hashlib
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bwpdiy import __version__  # noqa: E402

EXE_NAME = f"BWPDIY-v{__version__}"

# uvicorn 运行期按配置动态 import 的子模块（hooks-contrib 的 hook-uvicorn 已全量收集，
# 此处显式列出本应用实际用到的链路，作为双保险；均为已安装模块）
HIDDEN_IMPORTS = [
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.logging",
]

# 包内数据文件（源, 包内目标目录）
PACKAGE_DATA = [
    ("bwpdiy/render/default_layout.json", "bwpdiy/render"),
    ("bwpdiy/web/sample_art.png", "bwpdiy/web"),
]

ASSETS_EXCLUDE_SUFFIXES = {".psd", ".bak"}


def _utc_build_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _prune_releases(releases: Path, keep_minor: int = 5) -> None:
    """每个二级版本只留最新 exe，并且本地总共只留最近 keep_minor 个二级版本。"""
    candidates = []
    for path in releases.glob("BWPDIY-v*.exe"):
        match = re.fullmatch(r"BWPDIY-v(\d+)\.(\d+)\.(\d+)\.exe", path.name)
        if match:
            candidates.append((tuple(map(int, match.groups())), path))
    latest = {}
    for version, path in candidates:
        minor = version[:2]
        if minor not in latest or version > latest[minor][0]:
            latest[minor] = (version, path)
    keep = {latest[minor][1] for minor in sorted(latest)[-keep_minor:]}
    for _version, path in candidates:
        if path not in keep:
            path.unlink(missing_ok=True)


def _add_data(src: Path, dest: str) -> list[str]:
    return ["--add-data", f"{src}{os.pathsep}{dest}"]


def _datas_args() -> list[str]:
    args: list[str] = []
    for p in sorted((ROOT / "assets").rglob("*")):
        if p.is_dir() or "unprocessed" in p.parts or "psd_export" in p.parts or "legacy" in p.parts:
            continue
        if p.suffix.lower() in ASSETS_EXCLUDE_SUFFIXES:
            continue
        args += _add_data(p, str(p.relative_to(ROOT).parent))
    for src, dest in PACKAGE_DATA:
        args += _add_data(ROOT / src, dest)
    for p in sorted((ROOT / "bwpdiy/web/static").rglob("*")):
        if p.is_file():
            args += _add_data(p, str(p.relative_to(ROOT).parent))
    return args


def main() -> int:
    build_dir = ROOT / "build"
    build_dir.mkdir(exist_ok=True)
    build_time_path = build_dir / "build_time_utc.txt"
    build_time_path.write_text(_utc_build_time() + "\n", encoding="utf-8")
    args = [
        str(ROOT / "scripts" / "launcher.py"),
        "--name", EXE_NAME,
        "--onefile",
        "--noconfirm",
        "--clean",
        "--paths", str(ROOT),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]
    args += _datas_args()
    args += _add_data(build_time_path, "bwpdiy")
    for module in HIDDEN_IMPORTS:
        args += ["--hidden-import", module]

    PyInstaller.__main__.run(args)

    releases = ROOT / "releases"
    releases.mkdir(exist_ok=True)
    src = ROOT / "dist" / f"{EXE_NAME}.exe"
    dst = releases / src.name
    shutil.copy2(src, dst)
    _prune_releases(releases)
    # sha256 校验文件（sha256sum 格式）：release 必附资产，客户端下载后比对（updater._verify_download）
    digest = hashlib.sha256(dst.read_bytes()).hexdigest()
    sha_path = dst.with_name(dst.name + ".sha256")
    sha_path.write_text(f"{digest}  {dst.name}\n", encoding="utf-8")
    print(f"已输出: {dst} ({dst.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"校验文件: {sha_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
