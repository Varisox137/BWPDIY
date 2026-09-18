"""python -m bwpdiy：启动编辑器 WebGUI（默认 http://127.0.0.1:8630）。"""

import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser(prog="bwpdiy")
    ap.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    ap.add_argument("--port", type=int, default=8630, help="监听端口（默认 8630）")
    args = ap.parse_args()

    import uvicorn

    from bwpdiy.resources import default_assets_dir, default_library_dir
    from bwpdiy.web.app import create_app

    app = create_app(default_assets_dir(), library_dir=default_library_dir())
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
