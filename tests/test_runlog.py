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
    saved_hooks = sys.excepthook, threading.excepthook
    runlog._LOG_PATH = None
    yield
    for h in root.handlers[:]:
        if h not in saved_handlers:
            h.close()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    sys.excepthook, threading.excepthook = saved_hooks
    runlog._LOG_PATH = None


def test_run_log_writes_file_and_idempotent(tmp_path):
    path = runlog.setup_run_logging(tmp_path)
    assert path.parent == tmp_path and path.name.startswith("bwpdiy-")
    logging.getLogger("bwpdiy.test").info("你好，单次运行记录")
    for h in logging.getLogger().handlers:
        h.flush()
    text = path.read_text(encoding="utf-8")
    assert "BWPDIY v" in text and "你好，单次运行记录" in text  # 版本行 + 模块日志均落盘
    assert runlog.setup_run_logging(tmp_path) == path  # 重复调用不新建文件/不重复加 handler


def test_run_log_keeps_recent_10(tmp_path):
    for i in range(12):
        (tmp_path / f"bwpdiy-202001{i:02d}-000000.log").write_text("old", encoding="utf-8")
    path = runlog.setup_run_logging(tmp_path)
    remaining = sorted(tmp_path.glob("bwpdiy-*.log"))
    assert len(remaining) == runlog._KEEP
    assert remaining[-1] == path  # 最旧的删除，本次新文件保留
