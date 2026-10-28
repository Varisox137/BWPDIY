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
- 下载带进度回报（模块级 _PROGRESS，GUI 轮询 /api/update/progress 显示 MB/百分比）、
  总时长预算 DOWNLOAD_MAX_SECONDS（低速涓流不触发单段超时，整体兜底），失败删半截文件；
  检查/下载/校验/替换全过程写运行日志（runlog），供用户提交单次运行记录排查。

安全口径：固定仓库常量；资产名必须匹配 BWPDIY-vX.Y.Z.exe；下载仅 HTTPS；
下载产物做 MZ 头与最小尺寸 sanity 检查。release 除 exe 外须附 <exe文件名>.sha256
（sha256sum 格式），下载后实算比对，缺失或不匹配一律视为失败（安全校验不降级）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from bwpdiy import __version__

log = logging.getLogger("bwpdiy.updater")

REPO = "Varisox137/BWPDIY"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_RE = re.compile(r"^BWPDIY-v\d+\.\d+\.\d+\.exe$")
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
TIMEOUT = 15  # GitHub API / 下载单段读取超时（秒）
DOWNLOAD_MAX_SECONDS = 600  # 下载总时长预算：低速涓流连接不会触发单段超时，须整体兜底
_MIN_EXE_SIZE = 5 * 1024 * 1024  # 打包产物 ~30MB+，小于 5MB 必为错误页/截断

# 下载进度（模块级单例：一键更新同时最多一个，GUI 轮询 /api/update/progress 读取）
_PROGRESS = {"active": False, "downloaded": 0, "total": 0}
_APPLY_LOCK = threading.Lock()


# 检查更新日志去重：自动轮询每 1min 一次，相同错误/相同新版本只记一次，
# 一次成功检查后重置错误去重（网络恢复后再失败会重新记录）
_LAST_CHECK_LOG = {"error": None, "latest": None}


def download_progress() -> dict:
    """当前下载进度快照：{active, downloaded, total}（字节）。"""
    return dict(_PROGRESS)


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
        _LAST_CHECK_LOG["error"] = None  # 检查成功：重置错误去重（恢复后再失败会重新记）
        tag = str(data.get("tag_name", ""))
        latest = parse_version(tag)
        current = parse_version(__version__)
        if latest is None or current is None or latest <= current:
            return result
        expected_name = f"BWPDIY-{tag}.exe"
        asset = next((a for a in data.get("assets", [])
                      if a.get("name") == expected_name), None)
        if asset is None:
            result["error"] = "最新 release 未包含与版本号对应的 exe 资产"
            return result
        sha_asset = next((a for a in data.get("assets", [])
                          if a.get("name") == asset["name"] + ".sha256"), None)
        if sha_asset is None:
            # 无校验文件视同检查失败：hash 校验是安全防线，不降级为不校验
            result["error"] = "最新 release 未包含 sha256 校验文件，已跳过本次更新"
            return result
        result.update({
            "has_update": True,
            "latest": data["tag_name"],
            "asset_name": asset["name"],
            "asset_url": asset["browser_download_url"],
            "sha256_url": sha_asset["browser_download_url"],
            "size": asset.get("size", 0),
        })
        if _LAST_CHECK_LOG["latest"] != data["tag_name"]:
            log.info("检查更新：发现新版本 %s（当前 %s），资产 %s（%d 字节）",
                     data["tag_name"], __version__, asset["name"], asset.get("size", 0))
            _LAST_CHECK_LOG["latest"] = data["tag_name"]
    except Exception as e:  # 离线/限流/格式变化：静默降级为「无更新」
        result["error"] = str(e)
        if _LAST_CHECK_LOG["error"] != str(e):
            log.info("检查更新失败（按无更新处理）：%s", e)
            _LAST_CHECK_LOG["error"] = str(e)
    return result


def _download(url: str, dest: Path, on_progress=None) -> None:
    """流式下载 + sanity 检查（HTTPS 由 GitHub 资产 URL 保证）。

    on_progress(本次字节数) 每段回调（进度回报）；总时长超过 DOWNLOAD_MAX_SECONDS
    抛 TimeoutError（单段超时不覆盖低速涓流）；失败删除半截文件。
    """
    if not url.lower().startswith("https://"):
        raise ValueError("更新下载地址必须使用 HTTPS")
    log.info("开始下载：%s → %s", url, dest)
    started = time.monotonic()
    downloaded = 0
    next_log = 8 << 20  # 每 8MB 记一次进度（卡死/低速排查用）
    req = urllib.request.Request(url, headers={"User-Agent": f"BWPDIY/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp, open(dest, "wb") as f:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if on_progress:
                    on_progress(len(chunk))
                elapsed = time.monotonic() - started
                if elapsed > DOWNLOAD_MAX_SECONDS:
                    raise TimeoutError(
                        f"下载超过 {DOWNLOAD_MAX_SECONDS // 60} 分钟仍未完成，"
                        "请检查网络或点击「前往下载」手动更新")
                if downloaded >= next_log:
                    log.info("下载中：%.1f MB，已用 %.0fs", downloaded / 1e6, elapsed)
                    next_log += 8 << 20
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    log.info("下载完成：%.1f MB，耗时 %.1fs", downloaded / 1e6, time.monotonic() - started)
    if dest.stat().st_size < _MIN_EXE_SIZE:
        dest.unlink(missing_ok=True)
        raise ValueError("下载产物过小，疑似截断或错误页")
    with open(dest, "rb") as f:
        if f.read(2) != b"MZ":
            dest.unlink(missing_ok=True)
            raise ValueError("下载产物不是有效的 exe")


def _download_text(url: str) -> str:
    """下载小文本资产（sha256 校验文件）。"""
    if not url.lower().startswith("https://"):
        raise ValueError("更新校验文件地址必须使用 HTTPS")
    req = urllib.request.Request(url, headers={"User-Agent": f"BWPDIY/{__version__}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8")


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _expected_sha256(text: str, asset_name: str) -> str:
    """解析 sha256sum 格式（<64位hex>  <文件名>），并核对文件名对应。"""
    line = next((l for l in text.splitlines() if l.strip()), "")
    parts = line.split()
    if len(parts) < 2 or not _SHA256_RE.match(parts[0]):
        raise ValueError("sha256 校验文件格式非法")
    if parts[1].lstrip("*") != asset_name:
        raise ValueError("sha256 校验文件与 exe 资产不对应")
    return parts[0].lower()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_download(dest: Path, sha256_text: str, asset_name: str) -> None:
    """下载产物 sha256 比对；不一致或校验文件非法时删除下载文件并报错。"""
    try:
        expected = _expected_sha256(sha256_text, asset_name)
        actual = _file_sha256(dest)
        if actual != expected:
            raise ValueError(
                f"下载校验失败：sha256 不匹配（预期 {expected[:12]}…，实际 {actual[:12]}…）")
    except Exception:
        dest.unlink(missing_ok=True)
        raise


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
    """同一进程内更新任务互斥，防止重复请求并发写同一 exe/进度状态。"""
    if not _APPLY_LOCK.acquire(blocking=False):
        raise ValueError("已有更新任务正在进行，请勿重复点击")
    try:
        return _download_and_schedule_restart_locked(info)
    finally:
        _APPLY_LOCK.release()


def _download_and_schedule_restart_locked(info: dict) -> str:
    """下载新版 exe 并安排替换重启（仅 frozen）。返回新版本 tag。

    首选直接下载到当前运行目录（新版 exe 与旧版并存，退出后删旧启新）；
    目录不可写或与运行中 exe 同名时回退临时目录 + move 覆盖。
    非 frozen 直接 ValueError（开发模式不替换脚本自身）。退出用 Timer 延迟
    os._exit：先让 HTTP 响应发回浏览器，再杀进程放文件锁。
    下载后与 release 附带的 sha256 校验文件比对，不一致删临时文件并报错。
    """
    if not is_frozen():
        raise ValueError("开发模式（非 exe）不支持一键更新")
    old_exe = Path(sys.executable).resolve()
    dest = old_exe.parent / info["asset_name"]
    inplace = dest == old_exe or not _dir_writable(old_exe.parent)
    if inplace:
        dest = Path(tempfile.gettempdir()) / info["asset_name"]
    log.info("一键更新开始：目标版本 %s，运行 exe=%s，下载到 %s（inplace=%s）",
             info["latest"], old_exe, dest, inplace)
    _PROGRESS.update(active=True, downloaded=0, total=info.get("size", 0))
    try:
        _download(info["asset_url"], dest,
                  on_progress=lambda n: _PROGRESS.update(downloaded=_PROGRESS["downloaded"] + n))
        log.info("sha256 校验文件下载与比对")
        _verify_download(dest, _download_text(info["sha256_url"]), info["asset_name"])
        log.info("sha256 校验通过")
    except Exception:
        _PROGRESS["active"] = False
        log.exception("一键更新失败")
        raise
    _PROGRESS["active"] = False
    bat = _write_updater_bat(old_exe, dest, inplace)
    log.info("生成替换脚本 %s，启动后本进程退出", bat)
    subprocess.Popen(["cmd.exe", "/c", str(bat)],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    timer = threading.Timer(0.8, os._exit, args=(0,))
    timer.daemon = True
    timer.start()
    return info["latest"]
