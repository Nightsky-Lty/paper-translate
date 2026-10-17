"""Local launcher. Opening a browser is optional for development / headless use."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
URL = "http://127.0.0.1:8765"


def ready() -> bool:
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=1) as response:
            body = json.load(response)
            return body.get("application") == "paper-translate" and body.get("status") == "ok"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def open_when_ready():
    for _ in range(50):
        if ready():
            webbrowser.open(URL)
            return
        time.sleep(.2)


if __name__ == "__main__":
    if ready():
        print("纸间已在运行：" + URL)
        if not os.environ.get("PAPER_TRANSLATE_NO_BROWSER"):
            webbrowser.open(URL)
        sys.exit(0)
    if not os.environ.get("PAPER_TRANSLATE_NO_BROWSER"):
        threading.Thread(target=open_when_ready, daemon=True).start()
    import uvicorn
    uvicorn.run("server.app:app", host="127.0.0.1", port=8765)
