"""Create or rotate the single-owner access password without printing it."""
from __future__ import annotations

import argparse
import getpass
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.access import hash_password


def private_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(text + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--random-password-file", type=Path, help="Generate a random password and save it only in this private file.")
    args = parser.parse_args()
    if args.random_password_file:
        if args.output.exists() or args.random_password_file.exists():
            parser.error("Password files already exist. Refusing to overwrite an existing login.")
        password = secrets.token_urlsafe(24)
        private_write(args.random_password_file, password)
    else:
        password = getpass.getpass("访问密码（至少 12 个字符）: ")
        confirm = getpass.getpass("再次输入访问密码: ")
        if not secrets.compare_digest(password.encode(), confirm.encode()):
            parser.error("两次输入的密码不一致。")
        if len(password) < 12 or len(password.encode()) > 1024:
            parser.error("密码需至少 12 个字符，且不超过 1024 字节。")
    private_write(args.output, hash_password(password))
    print("访问密码哈希已保存。已运行的应用需重启以应用新密码。")
    if args.random_password_file:
        print("初始随机密码仅保存在指定的受限文件中；不会打印到日志。")
