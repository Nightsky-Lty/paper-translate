"""Host and Origin restrictions for local browsers and private SSH tunnels."""
from __future__ import annotations

import os
from urllib.parse import urlparse

LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class AccessPolicy:
    def __init__(self, mode: str = "local"):
        if mode not in ("local", "server"):
            raise ValueError("PAPER_TRANSLATE_MODE 仅支持 local 或 server。")
        self.mode = mode
        self.hosts = LOOPBACK | ({"testserver"} if mode == "local" else set())
        ports = (5173, 8765) if mode == "local" else (8765,)
        self.origins = {f"http://{host}:{port}" for host in ("localhost", "127.0.0.1", "[::1]") for port in ports}

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get("PAPER_TRANSLATE_MODE", "local"))

    def allowed(self, host_header: str, origin: str | None) -> bool:
        try:
            host = urlparse("//" + host_header)
            if (not host.hostname or host.username or host.password or host.hostname not in self.hosts
                    or host.path or host.query or host.fragment):
                return False
            # Accessing .port also validates malformed / out-of-range ports.
            host.port
        except ValueError:
            return False
        return origin is None or origin in self.origins
