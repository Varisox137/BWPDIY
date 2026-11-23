"""在线静态服务的日志提取码、轮换与只读文件访问。"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path

PREVIEW_BYTES = 512 * 1024
AUTH_FAILURE_WINDOW = 60.0
AUTH_FAILURE_LIMIT = 5
LOG_PATTERN = "bwpdiy-*.log"


def write_terminal_secret(text: str) -> bool:
    target = "CON" if os.name == "nt" else "/dev/tty"
    try:
        with open(target, "w", encoding="utf-8") as terminal:
            terminal.write(text + "\n")
            terminal.flush()
        return True
    except OSError:
        return False


def private_permissions(path: Path, *, directory: bool = False) -> None:
    try:
        os.chmod(path, 0o700 if directory else 0o600)
    except OSError as error:
        logging.getLogger("bwpdiy.online").warning("无法收紧 %s 的私有权限：%s", path, error)


def valid_log_filename(name: str) -> bool:
    if not isinstance(name, str) or Path(name).name != name:
        return False
    if not name.startswith("bwpdiy-") or not name.endswith(".log"):
        return False
    return not any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in name)


class OnlineLogService:
    def __init__(self, log_dir: Path, current_log: Path, rotate_seconds: float = 1800.0):
        self.log_dir = log_dir
        self.current_log = current_log
        self.rotate_seconds = rotate_seconds
        self._token = ""
        self._auth_failures: dict[str, list[float]] = {}
        self._auth_lock = threading.Lock()
        self._stop = threading.Event()
        self._rotation_thread = None
        self.rotate()

    @property
    def token(self) -> str:
        return self._token

    def authenticate(self, header: str | None, client: str) -> bool:
        now = time.monotonic()
        with self._auth_lock:
            failures = [stamp for stamp in self._auth_failures.get(client, [])
                        if now - stamp < AUTH_FAILURE_WINDOW]
            if len(failures) >= AUTH_FAILURE_LIMIT:
                self._auth_failures[client] = failures
                return False
            valid = False
            if header is not None:
                try:
                    valid = hmac.compare_digest(header, f"Bearer {self._token}")
                except TypeError:
                    pass
            if valid:
                self._auth_failures.pop(client, None)
            else:
                failures.append(now)
                self._auth_failures[client] = failures
            return valid

    def rotate(self) -> str:
        candidate = secrets.token_hex(8)
        path = self.log_dir / ".log-access-token"
        fd, temporary_name = tempfile.mkstemp(prefix=".log-access-token.", dir=self.log_dir)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="ascii") as temporary:
                private_permissions(temporary_path)
                temporary.write(candidate + "\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
        self._token = candidate
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        if not write_terminal_secret(f"[{timestamp}]日志提取码更新：{candidate}"):
            print(f"日志提取码已写入：{path}", flush=True)
        logging.getLogger("bwpdiy.online").info("日志提取码已轮换；文件=%s", path)
        return candidate

    def start(self) -> None:
        if self._rotation_thread is not None:
            return
        self._rotation_thread = threading.Thread(target=self._rotation_loop,
                                                  name="log-token-rotation", daemon=True)
        self._rotation_thread.start()

    def _rotation_loop(self) -> None:
        while not self._stop.wait(self.rotate_seconds):
            try:
                self.rotate()
            except Exception:
                logging.getLogger("bwpdiy.online").exception("日志提取码轮换失败")

    def close(self) -> None:
        self._stop.set()

    def _log_files(self) -> list[Path]:
        root = self.log_dir.resolve()
        files = {}
        for path in self.log_dir.glob(LOG_PATTERN):
            if (not valid_log_filename(path.name) or not path.is_file()
                    or path.resolve().parent != root):
                continue
            files[path.name] = path
        return [files[name] for name in sorted(files)]

    def list_logs(self) -> list[dict]:
        logs = []
        for path in self._log_files():
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            logs.append({"name": path.name, "mtime": stat.st_mtime,
                         "size": stat.st_size, "current": path == self.current_log})
        return logs

    def log_path(self, name: str) -> Path:
        if not valid_log_filename(name):
            raise ValueError("日志文件名无效")
        for path in self._log_files():
            if path.name == name:
                return path
        raise ValueError("日志文件不存在或不允许访问")

    def preview(self, name: str) -> tuple[str, bool]:
        with self.log_path(name).open("rb") as source:
            data = source.read(PREVIEW_BYTES + 1)
        truncated = len(data) > PREVIEW_BYTES
        text = data[:PREVIEW_BYTES].decode("utf-8", errors="replace")
        encoded = text.encode("utf-8")
        if len(encoded) > PREVIEW_BYTES:
            truncated = True
            text = encoded[:PREVIEW_BYTES].decode("utf-8", errors="ignore")
        return text, truncated
