"""启动编辑器 WebGUI：打包正式版默认 8630，源码开发版默认 8631，启动后自动打开浏览器。

启动先打印当前版本；目标端口被占用时显示占用者与 PID，仅在交互终端回车确认后
结束该进程并等待端口释放，再启动服务。非交互环境只告警退出，不自动结束进程。
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request


def _probe_running(host: str, port: int) -> str | None:
    """探测目标地址已有实例：BWPDIY 实例返回其版本；无实例返回 None；非 BWPDIY 占用返回 "?"。"""
    url_host = f"[{host}]" if ":" in host else host  # IPv6 字面量加方括号
    try:
        with urllib.request.urlopen(f"http://{url_host}:{port}/api/version",
                                    timeout=2) as resp:
            version = json.loads(resp.read()).get("version")
        return str(version) if version else "?"
    except urllib.error.HTTPError:
        return "?"  # 有 HTTP 服务但非 BWPDIY
    except Exception:
        return None  # 连接拒绝/超时：由端口所有者检测兜底


def _port_owner_pid(port: int) -> int | None:
    """Windows 下返回监听端口的 PID；查询失败/非 Windows 返回 None。"""
    if os.name != "nt":
        return None
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                                  encoding="mbcs", errors="replace", check=False)
    except OSError:
        return None
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3] == "LISTENING" \
                and parts[1].rsplit(":", 1)[-1] == str(port):
            try:
                return int(parts[4])
            except ValueError:
                continue
    return None


def _confirm_replace_owner(port: int, running: str, pid: int | None) -> bool:
    who = f"BWPDIY v{running}" if running != "?" else "其他服务"
    print(f"警告：端口 {port} 已被{who}占用。", file=sys.stderr)
    if pid is None:
        print("无法识别占用进程，请手动关闭后重试。", file=sys.stderr)
        return False
    print(f"占用进程 PID：{pid}。请先在对应界面保存工作。", file=sys.stderr)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("非交互环境不自动结束进程；请手动关闭后重试。", file=sys.stderr)
        return False
    try:
        print()
        answer = input("按回车确认关闭该进程并启动服务；输入其他内容取消：")
        print()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer == ""


def _kill_and_wait(pid: int, port: int) -> bool:
    if pid == os.getpid():
        print("拒绝结束当前进程。", file=sys.stderr)
        return False
    result = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                            capture_output=True, text=True, encoding="mbcs",
                            errors="replace", check=False)
    if result.returncode != 0:
        print(f"关闭进程失败：{result.stdout.strip()}{result.stderr.strip()}", file=sys.stderr)
        return False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if _port_owner_pid(port) is None:
            return True
        time.sleep(0.1)
    print(f"端口 {port} 仍未释放，请手动检查后重试。", file=sys.stderr)
    return False


def _pause_exit() -> None:
    """探测到已有实例时等待按键再退出（双击运行的 exe 打印完立即关窗会看不到提示）。
    stdin/stdout 任一非交互终端（测试/脚本/输出捕获）直接跳过，避免挂起。"""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return
    print()
    print("按任意键退出……", end="", flush=True)
    try:
        import msvcrt  # Windows：真·任意键
        msvcrt.getch()
    except ImportError:
        try:
            input()  # 其他平台退化为回车
        except EOFError:
            pass
    print("\n")


def _version_line() -> str:
    from bwpdiy import __version__
    line = f"BWPDIY v{__version__}"
    if not getattr(sys, "frozen", False):
        return line
    from bwpdiy.resources import resource_root
    try:
        timestamp = (resource_root() / "bwpdiy" / "build_time_utc.txt").read_text(
            encoding="utf-8").strip()
    except OSError:
        return line
    return f"{line}（打包时间：{timestamp}）" if timestamp else line


def main() -> int:
    default_port = 8630 if getattr(sys, "frozen", False) else 8631
    ap = argparse.ArgumentParser(prog="bwpdiy")
    ap.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    ap.add_argument("--port", type=int, default=default_port,
                    help=f"监听端口（正式版默认 8630，开发版默认 8631；本次 {default_port}）")
    ap.add_argument("--no-browser", action="store_true",
                    help="启动后不自动打开浏览器（测试/调试场景）")
    ap.add_argument("--no-idle-stop", action="store_true",
                    help="关闭闲置自动终止（开发用；打包 exe 默认保持 2h 防占用）")
    args = ap.parse_args()

    import threading
    import webbrowser

    import uvicorn

    from bwpdiy.resources import default_assets_dir, default_library_dir
    from bwpdiy.runlog import setup_run_logging
    from bwpdiy.web.app import create_app

    print(_version_line() + "\n", flush=True)
    log_path = setup_run_logging()
    print(f"运行日志：{log_path}（反馈问题请附上该文件）")
    logging.getLogger("bwpdiy").info("启动参数：%s", sys.argv)

    if args.host in ("127.0.0.1", "localhost", "::1"):
        owner_pid = _port_owner_pid(args.port)
        running = (_probe_running(args.host, args.port)
                   if owner_pid is not None or os.name != "nt" else None)
        if owner_pid is not None or running is not None:
            confirmed = _confirm_replace_owner(args.port, running or "?", owner_pid)
            if not confirmed or not _kill_and_wait(owner_pid, args.port):
                _pause_exit()
                return 1
            logging.getLogger("bwpdiy").warning("经回车确认，已关闭端口 %d 的占用进程 %d",
                                                args.port, owner_pid)

    if not args.no_browser:
        # uvicorn.run 阻塞：用 Timer 延迟 1 秒打开，等服务就绪；通配地址对浏览器无意义，回退回环
        host = args.host if args.host not in ("0.0.0.0", "::") else "127.0.0.1"
        timer = threading.Timer(1.0, webbrowser.open, args=(f"http://{host}:{args.port}/",))
        timer.daemon = True  # 服务被 Ctrl+C 打断时 Timer 不得拖住进程退出
        timer.start()

    # 退出时清理未使用卡图（v1.6.0）：正常退出走 atexit；闲置终止、手动按钮与一键更新
    # 用 os._exit 绕过 atexit，分别在 on_idle/on_shutdown 回调与 update_apply 中显式清理。
    # Windows 直接关窗可能绕过 atexit，尽力而为。
    import atexit

    from bwpdiy.store import cleanup_unused_images

    library_dir = default_library_dir()

    def _cleanup_images():
        try:
            deleted = cleanup_unused_images(library_dir)
            if deleted:
                logging.getLogger("bwpdiy").info("退出清理未使用卡图 %d 张：%s", len(deleted), deleted)
        except Exception:
            logging.getLogger("bwpdiy").exception("退出清理未使用卡图失败")

    atexit.register(_cleanup_images)

    def _on_idle():
        print("已连续 2 小时无操作，服务自动终止（防占用），重新启动即可继续使用。", flush=True)
        _cleanup_images()
        os._exit(0)

    def _on_shutdown():
        def _stop():
            _cleanup_images()
            os._exit(0)
        timer = threading.Timer(0.3, _stop)
        timer.daemon = True
        timer.start()

    app = create_app(default_assets_dir(), library_dir=library_dir,
                     idle_timeout=0 if args.no_idle_stop else 7200.0,
                     on_idle=None if args.no_idle_stop else _on_idle,
                     on_shutdown=_on_shutdown,
                     loopback_guard=args.host in ("127.0.0.1", "localhost", "::1"))
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        # 非回环监听：局域网内任何人可读写/删除项目（无鉴权），且 Host 校验已关闭
        print(f"警告：监听 {args.host} 非回环地址，同网络主机可完全访问本工具",
              file=sys.stderr)
    # log_config=None：uvicorn 日志走 root（runlog 文件+控制台），不另建 handler
    uvicorn.run(app, host=args.host, port=args.port, log_config=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
