"""单次运行文件日志：启动时初始化，供用户提交单次运行记录排查问题。

每次启动在 <运行目录>/logs/ 写 bwpdiy-YYYYMMDD-HHMMSS-PID.log（UTF-8，exe 取 exe 所在
目录、开发取 cwd；不可写回退系统临时目录 bwpdiy-logs/），同时保留控制台输出；
最多保留最近 10 次运行日志，启动时同时删除超过 7 天的旧日志。文件记录 DEBUG
及以上（GUI 按钮/字段变更、上传/保存与本地写操作），控制台只显示 INFO 及以上；
PIL 的 PNG 字节流 DEBUG 屏蔽，PIL 自身 INFO 及以上保留。
另有版本/启动参数、uvicorn 服务日志（access 降级 WARNING）、更新全过程与未捕获异常。
纯本地工具无账号体系；文本正文不写入日志，字段文本变更只记录长度，写操作记录
资源路径与 HTTP 结果。
"""

import logging
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

_KEEP = 10  # 最多保留最近几次运行日志
_LOG_MAX_AGE_SECONDS = 7 * 86400
_LOG_PATH: Path | None = None
_LEVEL_COLORS = {
    logging.DEBUG: "34", logging.INFO: "32", logging.WARNING: "33",
    logging.ERROR: "31", logging.CRITICAL: "35",
}


class LevelColorFormatter(logging.Formatter):
    """终端级别标签着色；文件与重定向输出使用无色格式器。"""

    def __init__(self, fmt: str, color: bool):
        super().__init__(fmt)
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        color = _LEVEL_COLORS.get(record.levelno)
        if not self.color or color is None:
            return text
        level = record.levelname
        return text.replace(level, f"\x1b[{color}m{level}\x1b[0m", 1)


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
    path = log_dir / (time.strftime("bwpdiy-%Y%m%d-%H%M%S") + f"-{os.getpid()}.log")

    now = time.time()
    old = sorted(log_dir.glob("bwpdiy-*.log"))
    for stale in old:
        try:
            if now - stale.stat().st_mtime > _LOG_MAX_AGE_SECONDS:
                stale.unlink(missing_ok=True)
        except OSError:
            pass  # 多实例同时清理时文件可能已被另一进程删除
    old = [p for p in old if p.exists()]
    for stale in old[:max(0, len(old) - (_KEEP - 1))]:  # 给本次新文件留位
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            pass

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)  # 文件保留完整 DEBUG 轨迹
    file_handler.setFormatter(logging.Formatter(fmt))
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)  # 控制台不因高频 GUI/写操作事件刷屏
    console.setFormatter(LevelColorFormatter(fmt, color=console.stream.isatty()))
    root.addHandler(file_handler)
    root.addHandler(console)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # 每次预览一条，刷屏
    logging.getLogger("PIL").setLevel(logging.INFO)  # PNG 字节流 DEBUG 对排查无帮助

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
