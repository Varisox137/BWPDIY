"""单次运行文件日志：启动时初始化，供用户提交单次运行记录排查问题。

每次启动在 <运行目录>/logs/ 写 bwpdiy-YYYYMMDD-HHMMSS.log（UTF-8，exe 取 exe 所在
目录、开发取 cwd；不可写回退系统临时目录 bwpdiy-logs/），同时保留控制台输出；
最多保留最近 10 次运行日志。内容：版本/启动参数、uvicorn 服务日志（access 降级
WARNING 防刷屏）、更新全过程（updater 模块日志）、未捕获异常。纯本地工具无账号
体系，日志不含卡牌/项目内容，仅路径与事件。
"""

import logging
import sys
import tempfile
import threading
import time
from pathlib import Path

_KEEP = 10  # 最多保留最近几次运行日志
_LOG_PATH: Path | None = None


def setup_run_logging(log_dir: Path | None = None) -> Path:
    """初始化 root 日志（文件+控制台），返回本次日志路径；重复调用幂等。

    log_dir 可注入（测试）；缺省按 frozen/cwd 推导，不可写回退临时目录。
    """
    global _LOG_PATH
    if _LOG_PATH is not None:
        return _LOG_PATH
    if log_dir is None:
        base = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                else Path.cwd())
        log_dir = base / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            probe = log_dir / ".probe"
            probe.write_bytes(b"")
            probe.unlink()
        except OSError:
            log_dir = Path(tempfile.gettempdir()) / "bwpdiy-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / time.strftime("bwpdiy-%Y%m%d-%H%M%S.log")

    old = sorted(log_dir.glob("bwpdiy-*.log"))
    for stale in old[:max(0, len(old) - (_KEEP - 1))]:  # 给本次新文件留位
        stale.unlink(missing_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    for handler in (logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler()):
        handler.setFormatter(fmt)
        root.addHandler(handler)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # 每次预览一条，刷屏

    def log_exception(exc_type, exc, tb, hook):
        logging.getLogger("bwpdiy").critical("未捕获异常", exc_info=(exc_type, exc, tb))
        hook(exc_type, exc, tb)  # 保留原控制台栈输出

    sys.excepthook = lambda t, v, tb: log_exception(t, v, tb, sys.__excepthook__)
    threading.excepthook = lambda a: log_exception(a.exc_type, a.exc_value,
                                                   a.exc_traceback, lambda *x: None)

    from bwpdiy import __version__
    logging.getLogger("bwpdiy").info(
        "BWPDIY v%s 启动；frozen=%s；可执行文件=%s；日志=%s",
        __version__, getattr(sys, "frozen", False), sys.executable, path)
    _LOG_PATH = path
    return path
