"""python -m bwpdiy：启动编辑器 WebGUI（默认 http://127.0.0.1:8630），启动后自动打开浏览器。"""

import argparse
import sys


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

    from bwpdiy.resources import default_assets_dir, default_library_dir
    from bwpdiy.web.app import create_app

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
