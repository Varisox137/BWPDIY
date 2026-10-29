"""单次运行日志（bwpdiy/runlog.py）：文件落盘、幂等、保留最近 10 次。"""

import logging
import sys
import threading

import pytest

from bwpdiy import runlog


@pytest.fixture(autouse=True)
def clean_root_logger():
    """setup 会改 root handlers/excepthook 与模块幂等状态：用毕还原，不污染其他测试。"""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_pil_level = logging.getLogger("PIL").level
    saved_hooks = sys.excepthook, threading.excepthook
    runlog._LOG_PATH = None
    yield
    for h in root.handlers[:]:
        if h not in saved_handlers:
            h.close()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    logging.getLogger("PIL").setLevel(saved_pil_level)
    sys.excepthook, threading.excepthook = saved_hooks
    runlog._LOG_PATH = None


def test_run_log_writes_file_and_idempotent(tmp_path):
    path = runlog.setup_run_logging(tmp_path)
    assert path.parent == tmp_path and path.name.startswith("bwpdiy-")
    assert path.stem.endswith(f"-{runlog.os.getpid()}")  # 同秒多实例不共用日志文件
    logging.getLogger("bwpdiy.test").info("你好，单次运行记录")
    logging.getLogger("bwpdiy.gui").debug("按钮与数值调试事件")
    logging.getLogger("PIL.PngImagePlugin").debug("STREAM b'IHDR' 冗余字节流")
    for h in logging.getLogger().handlers:
        h.flush()
    text = path.read_text(encoding="utf-8")
    assert "BWPDIY v" in text and "你好，单次运行记录" in text  # 版本行 + 模块日志均落盘
    assert "DEBUG bwpdiy.gui: 按钮与数值调试事件" in text
    assert "冗余字节流" not in text
    file_handler = next(h for h in logging.getLogger().handlers
                        if getattr(h, "baseFilename", None) == str(path))
    console_handler = next(h for h in logging.getLogger().handlers
                           if type(h) is logging.StreamHandler)
    assert file_handler.level == logging.DEBUG
    assert console_handler.level == logging.INFO
    assert runlog.setup_run_logging(tmp_path) == path  # 重复调用不新建文件/不重复加 handler


def test_run_log_keeps_recent_10(tmp_path):
    for i in range(12):
        (tmp_path / f"bwpdiy-202001{i:02d}-000000.log").write_text("old", encoding="utf-8")
    path = runlog.setup_run_logging(tmp_path)
    remaining = sorted(tmp_path.glob("bwpdiy-*.log"))
    assert len(remaining) == runlog._KEEP
    assert remaining[-1] == path  # 最旧的删除，本次新文件保留


def test_run_log_deletes_files_older_than_7_days(tmp_path):
    import os
    import time
    stale = tmp_path / "bwpdiy-20200101-000000.log"
    recent = tmp_path / "bwpdiy-20200102-000000.log"
    stale.write_text("stale", encoding="utf-8")
    recent.write_text("recent", encoding="utf-8")
    old = time.time() - 8 * 86400
    os.utime(stale, (old, old))
    path = runlog.setup_run_logging(tmp_path)
    assert not stale.exists()
    assert recent.exists() and path.exists()


@pytest.mark.parametrize("level,color", [
    (logging.DEBUG, "34"), (logging.INFO, "32"), (logging.WARNING, "33"),
    (logging.ERROR, "31"), (logging.CRITICAL, "35"),
])
def test_level_color_formatter_only_colors_level(level, color):
    record = logging.LogRecord("test", level, __file__, 1, "普通文本", (), None)
    colored = runlog.LevelColorFormatter("%(levelname)s %(message)s", color=True)
    plain = runlog.LevelColorFormatter("%(levelname)s %(message)s", color=False)
    assert colored.format(record) == f"\x1b[{color}m{record.levelname}\x1b[0m 普通文本"
    assert plain.format(record) == f"{record.levelname} 普通文本"
