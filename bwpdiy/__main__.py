"""python -m bwpdiy：启动编辑器 WebGUI（默认 http://127.0.0.1:8630）。"""

import sys
from pathlib import Path


def main() -> int:
    import uvicorn

    from bwpdiy.web.app import create_app

    root = Path(__file__).resolve().parent.parent
    app = create_app(root / "assets", library_dir=root / "library")
    uvicorn.run(app, host="127.0.0.1", port=8630)
    return 0


if __name__ == "__main__":
    sys.exit(main())
