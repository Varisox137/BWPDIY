"""PyInstaller 打包入口：等价于 python -m bwpdiy（顶层 import 便于静态分析）。"""

import sys

from bwpdiy.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
