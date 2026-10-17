"""Open the remote reader through a private SSH tunnel."""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
import webbrowser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="SSH host alias or user@hostname")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.host.startswith("-"):
        parser.error("Invalid SSH host")
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 8765))
    except OSError:
        parser.exit(1, "本机 8765 端口正在使用，请先关闭本机纸间或已有隧道后重试。\n")
    process = subprocess.Popen([
        "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=10", "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3",
        "-N", "-L", "127.0.0.1:8765:127.0.0.1:8765", args.host,
    ])
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(30):
            if process.poll() is not None:
                parser.exit(1, "SSH 隧道未建立，请检查 SSH 配置和服务器连接。\n")
            try:
                with opener.open("http://localhost:8765/healthz", timeout=1) as response:
                    if json.load(response).get("application") == "paper-translate":
                        break
            except (OSError, urllib.error.URLError, ValueError):
                pass
            time.sleep(0.5)
        else:
            parser.exit(1, "服务器应用尚未就绪，请稍后重试。\n")
        print("远端纸间：http://localhost:8765\n保持此窗口打开。按 Ctrl+C 断开连接；服务器任务会继续运行。", flush=True)
        if not args.no_browser:
            webbrowser.open("http://localhost:8765")
        process.wait()
    except KeyboardInterrupt:
        print("\n正在关闭 SSH 隧道。")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
