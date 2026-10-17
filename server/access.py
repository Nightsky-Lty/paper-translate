"""Single-owner access policy for local use and an HTTPS reverse proxy."""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

LOOPBACK = {"localhost", "127.0.0.1", "::1"}
LOCAL_ORIGINS = {f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (5173, 8765)}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt-v1${salt.hex()}${derived.hex()}"


def parse_hash(value: str) -> tuple[bytes, bytes]:
    try:
        version, salt, digest = value.strip().split("$")
        salt_bytes, digest_bytes = bytes.fromhex(salt), bytes.fromhex(digest)
        if version != "scrypt-v1" or len(salt_bytes) != 16 or len(digest_bytes) != 32:
            raise ValueError()
        return salt_bytes, digest_bytes
    except ValueError as exc:
        raise ValueError("访问密码哈希无效，请重新运行 create_access_password.py。") from exc


class AccessPolicy:
    def __init__(self, mode: str = "local", public_url: str = "", username: str = "reader", password_hash: str = ""):
        if mode not in ("local", "server"):
            raise ValueError("PAPER_TRANSLATE_MODE 仅支持 local 或 server。")
        self.mode, self.public_url, self.username = mode, public_url.rstrip("/"), username
        self.hosts = LOOPBACK | ({"testserver"} if mode == "local" else set())
        self.origins = LOCAL_ORIGINS if mode == "local" else set()
        self.salt, self.digest = b"", b""
        if mode == "server":
            url = urlparse(public_url)
            if (not url.hostname or url.username or url.password or url.query or url.fragment
                    or url.path not in ("", "/") or url.scheme not in ("http", "https")):
                raise ValueError("服务器模式需设置有效的 PAPER_TRANSLATE_PUBLIC_URL，不能包含路径或查询参数。")
            if url.scheme != "https" and url.hostname not in LOOPBACK:
                raise ValueError("公网访问地址必须使用 HTTPS；HTTP 仅允许 localhost SSH 隧道验收。")
            if not username or ":" in username:
                raise ValueError("访问用户名不能为空或包含冒号。")
            self.hosts = self.hosts | {url.hostname}
            self.origins = {self.public_url}
            self.salt, self.digest = parse_hash(password_hash)
        self._accepted: dict[bytes, float] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls):
        mode = os.environ.get("PAPER_TRANSLATE_MODE", "local")
        value = ""
        if mode == "server":
            filename = os.environ.get("PAPER_TRANSLATE_PASSWORD_HASH_FILE", "")
            if not filename:
                raise ValueError("服务器模式必须配置 PAPER_TRANSLATE_PASSWORD_HASH_FILE，拒绝无密码启动。")
            try:
                value = Path(filename).read_text(encoding="utf-8")
            except OSError as exc:
                raise ValueError("无法读取访问密码哈希，请先创建访问密码文件。") from exc
        return cls(mode, os.environ.get("PAPER_TRANSLATE_PUBLIC_URL", ""),
                   os.environ.get("PAPER_TRANSLATE_ACCESS_USER", "reader"), value)

    def allowed(self, host_header: str, origin: str | None) -> bool:
        try:
            host = urlparse("//" + host_header)
            if not host.hostname or host.username or host.password or host.hostname not in self.hosts:
                return False
            # Accessing .port also validates malformed / out-of-range ports.
            host.port
        except ValueError:
            return False
        return not origin or origin in self.origins

    def authenticate(self, header: str) -> bool:
        if self.mode == "local":
            return True
        if len(header) > 4096:
            return False
        # Cache only fingerprints of successful headers, never plaintext credentials.
        fingerprint = hashlib.sha256(header.encode("utf-8")).digest()
        now = time.monotonic()
        with self._lock:
            if self._accepted.get(fingerprint, 0) > now:
                return True
        try:
            scheme, token = header.split(" ", 1)
            if scheme.lower() != "basic":
                return False
            username, password = base64.b64decode(token, validate=True).decode("utf-8").split(":", 1)
            if not password or len(password.encode("utf-8")) > 1024:
                return False
        except (ValueError, UnicodeError, binascii.Error):
            return False
        derived = hashlib.scrypt(password.encode("utf-8"), salt=self.salt, n=16384, r=8, p=1, dklen=32)
        user_ok = secrets.compare_digest(username.encode("utf-8"), self.username.encode("utf-8"))
        password_ok = secrets.compare_digest(derived, self.digest)
        if not (user_ok and password_ok):
            return False
        with self._lock:
            self._accepted = {key: expiry for key, expiry in self._accepted.items() if expiry > now}
            if len(self._accepted) >= 128:
                self._accepted.pop(next(iter(self._accepted)))
            self._accepted[fingerprint] = now + 300
        return True
