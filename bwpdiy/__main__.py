"""python -m bwpdiy：启动编辑器 WebGUI（默认 http://127.0.0.1:8630），启动后自动打开浏览器。

启动时探测目标端口已有实例：同版本 → 直接开浏览器复用（不重复起服务）；
异版本 → 提示先保存工作、关闭旧程序再启动（避免 bind 崩溃报栈）。
"""

import argparse
import json
import sys
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
        return None  # 连接拒绝/超时：视为空闲（bind 失败仍由 uvicorn 报错兜底）


def main() -> int:
    ap = argparse.ArgumentParser(prog="bwpdiy")
    ap.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    ap.add_argument("--port", type=int, default=8630, help="监听端口（默认 8630）")
    ap.add_argument("--no-browser", action="store_true",
                    help="启动后不自动打开浏览器（测试/调试场景）")
    args = ap.parse_args()

    import threading
    import webbrowser

    import uvicorn

    from bwpdiy import __version__
    from bwpdiy.resources import default_assets_dir, default_library_dir
    from bwpdiy.web.app import create_app

    if args.host in ("127.0.0.1", "localhost", "::1"):
        running = _probe_running(args.host, args.port)
        if running is not None:
            url = f"http://{args.host}:{args.port}/"
            if running == __version__:
                print(f"BWPDIY v{__version__} 已在运行：{url}（直接打开浏览器复用，不重复启动）")
                if not args.no_browser:
                    webbrowser.open(url)
                return 0
            who = f"旧版本 BWPDIY v{running}" if running != "?" else "另一服务"
            print(f"端口 {args.port} 已被{who}占用，本程序（v{__version__}）未启动。",
                  file=sys.stderr)
            if running != "?":
                print("请先在旧版界面保存工作并关闭旧程序，再重新启动本程序"
                      "（旧版界面的一键更新也可直接升级）。", file=sys.stderr)
            return 1

    if not args.no_browser:
        # uvicorn.run 阻塞：用 Timer 延迟 1 秒打开，等服务就绪；通配地址对浏览器无意义，回退回环
        host = args.host if args.host not in ("0.0.0.0", "::") else "127.0.0.1"
        timer = threading.Timer(1.0, webbrowser.open, args=(f"http://{host}:{args.port}/",))
        timer.daemon = True  # 服务被 Ctrl+C 打断时 Timer 不得拖住进程退出
        timer.start()

    app = create_app(default_assets_dir(), library_dir=default_library_dir(),
                     loopback_guard=args.host in ("127.0.0.1", "localhost", "::1"))
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        # 非回环监听：局域网内任何人可读写/删除项目（无鉴权），且 Host 校验已关闭
        print(f"警告：监听 {args.host} 非回环地址，同网络主机可完全访问本工具",
              file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
