"""exe 自动更新：检查 GitHub latest release，一键下载后退出替换重启。

方案（用户定案「检查+一键更新」）：
- 页面加载时 GET /api/update/check（服务端拉 GitHub API，避免前端跨域/限流口径分散）；
- 有新版时界面出横幅，点「一键更新」→ POST /api/update/apply：
  服务端重新拉取 release 信息（不信前端传的 URL），下载新 exe 到当前运行目录
  （目录不可写则回退临时目录 + move 覆盖），生成 updater bat
  （删旧 exe 的等待循环兼作进程退出检测 → 启动新版 → 自删），spawn 后本进程退出。
- 启动时 __main__ 探测目标端口已有实例：同版本直接打开浏览器复用；
  异版本提示先保存再关闭旧程序。
- 仅 frozen（PyInstaller 打包）模式可执行替换；开发模式只提示、不允许 apply。

安全口径：固定仓库常量；资产名必须匹配 BWPDIY-vX.Y.Z.exe；下载仅 HTTPS；
下载产物做 MZ 头与最小尺寸 sanity 检查。release 未发布 checksum，暂不校验哈希。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

from bwpdiy import __version__

REPO = "Varisox137/BWPDIY"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_RE = re.compile(r"^BWPDIY-v\d+\.\d+\.\d+\.exe$")
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
TIMEOUT = 15  # GitHub API / 下载单段读取超时（秒）
_MIN_EXE_SIZE = 5 * 1024 * 1024  # 打包产物 ~30MB+，小于 5MB 必为错误页/截断


def parse_version(tag: str) -> tuple[int, int, int] | None:
    """'v1.2.3' / '1.2.3' → (1,2,3)；不合法 → None。"""
    m = _VERSION_RE.match(tag.strip())
    return tuple(int(g) for g in m.groups()) if m else None


def is_frozen() -> bool:
    """是否 PyInstaller 打包运行（一键替换仅在该模式下有意义）。"""
    return getattr(sys, "frozen", False)


def check_update() -> dict:
    """拉 latest release 比对版本。网络/解析失败不抛异常：has_update=False + error 字段。"""
    result = {"current": __version__, "frozen": is_frozen(), "has_update": False}
    try:
        req = urllib.request.Request(API_LATEST, headers={
            "User-Agent": f"BWPDIY/{__version__}",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
        latest = parse_version(str(data.get("tag_name", "")))
        current = parse_version(__version__)
        if latest is None or current is None or latest <= current:
            return result
        asset = next((a for a in data.get("assets", []) if ASSET_RE.match(a.get("name", ""))), None)
        if asset is None:
            result["error"] = "最新 release 未包含 exe 资产"
            return result
        result.update({
            "has_update": True,
            "latest": data["tag_name"],
            "asset_name": asset["name"],
            "asset_url": asset["browser_download_url"],
            "size": asset.get("size", 0),
        })
    except Exception as e:  # 离线/限流/格式变化：静默降级为「无更新」
        result["error"] = str(e)
    return result


def _download(url: str, dest: Path) -> None:
    """流式下载 + sanity 检查（HTTPS 由 GitHub 资产 URL 保证）。"""
    req = urllib.request.Request(url, headers={"User-Agent": f"BWPDIY/{__version__}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    if dest.stat().st_size < _MIN_EXE_SIZE:
        dest.unlink(missing_ok=True)
        raise ValueError("下载产物过小，疑似截断或错误页")
    with open(dest, "rb") as f:
        if f.read(2) != b"MZ":
            dest.unlink(missing_ok=True)
            raise ValueError("下载产物不是有效的 exe")


def _write_updater_bat(old_exe: Path, new_exe: Path, inplace: bool) -> Path:
    """生成替换脚本（cmd 批处理按 ANSI 解析，路径含中文时用 gbk 编码防误码）。

    inplace=False（首选，新版与旧版同目录并存）：删除旧 exe 的等待循环兼作
    进程退出检测（运行中文件被锁删不掉）→ 启动新版 → 自删。
    inplace=True（回退，目录不可写/同名）：move 覆盖旧 exe → 启动 → 自删。
    """
    bat = Path(tempfile.gettempdir()) / f"bwpdiy_update_{os.getpid()}.bat"
    if inplace:
        body = (
            "set retries=60\r\n"
            ":loop\r\n"
            f'move /y "{new_exe}" "{old_exe}" >nul 2>&1\r\n'
            "if %errorlevel%==0 goto done\r\n"
            "timeout /t 1 /nobreak >nul\r\n"
            "set /a retries-=1\r\n"
            "if %retries% gtr 0 goto loop\r\n"
            "exit /b 1\r\n"
            ":done\r\n"
            f'start "" "{old_exe}"\r\n'
        )
    else:
        body = (
            "set retries=60\r\n"
            ":loop\r\n"
            f'del "{old_exe}" >nul 2>&1\r\n'
            f'if not exist "{old_exe}" goto done\r\n'
            "timeout /t 1 /nobreak >nul\r\n"
            "set /a retries-=1\r\n"
            "if %retries% gtr 0 goto loop\r\n"
            "exit /b 1\r\n"
            ":done\r\n"
            f'start "" "{new_exe}"\r\n'
        )
    bat.write_text("@echo off\r\n" + body + 'del "%~f0"\r\n', encoding="gbk")
    return bat


def _dir_writable(d: Path) -> bool:
    try:
        probe = d / f".bwpdiy_probe_{os.getpid()}"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def download_and_schedule_restart(info: dict) -> str:
    """下载新版 exe 并安排替换重启（仅 frozen）。返回新版本 tag。

    首选直接下载到当前运行目录（新版 exe 与旧版并存，退出后删旧启新）；
    目录不可写或与运行中 exe 同名时回退临时目录 + move 覆盖。
    非 frozen 直接 ValueError（开发模式不替换脚本自身）。退出用 Timer 延迟
    os._exit：先让 HTTP 响应发回浏览器，再杀进程放文件锁。
    """
    if not is_frozen():
        raise ValueError("开发模式（非 exe）不支持一键更新")
    old_exe = Path(sys.executable).resolve()
    dest = old_exe.parent / info["asset_name"]
    inplace = dest == old_exe or not _dir_writable(old_exe.parent)
    if inplace:
        dest = Path(tempfile.gettempdir()) / info["asset_name"]
    _download(info["asset_url"], dest)
    bat = _write_updater_bat(old_exe, dest, inplace)
    subprocess.Popen(["cmd.exe", "/c", str(bat)],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    timer = threading.Timer(0.8, os._exit, args=(0,))
    timer.daemon = True
    timer.start()
    return info["latest"]
