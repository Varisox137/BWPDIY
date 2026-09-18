"""运行期资源路径解析：兼容 PyInstaller onefile（sys._MEIPASS）。

frozen 时内嵌资源（assets/、包内数据文件）解包到 _MEIPASS 临时目录；
用户数据（library/）不内嵌，放 exe 同级目录。
"""

import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_root() -> Path:
    """内嵌资源根：frozen 时为 PyInstaller 解包目录，否则为项目根。"""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def default_assets_dir() -> Path:
    return resource_root() / "assets"


def default_library_dir() -> Path:
    """用户卡牌库：frozen 时为 exe 同级 library/（不存在则创建），否则为项目根 library/。"""
    if is_frozen():
        path = Path(sys.executable).resolve().parent / "library"
    else:
        path = resource_root() / "library"
    path.mkdir(parents=True, exist_ok=True)
    return path
