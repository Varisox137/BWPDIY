"""python -m bwpdiy：启动编辑器 WebGUI（默认 http://127.0.0.1:8630）。"""

import sys


def main() -> int:
    import uvicorn

    from bwpdiy.web.app import create_app

    app = create_app("assets")
    uvicorn.run(app, host="127.0.0.1", port=8630)
    return 0


if __name__ == "__main__":
    sys.exit(main())
