from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "papers.sqlite3"
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        os.chmod(self.db, 0o600)

    def connect(self):
        con = sqlite3.connect(self.db, timeout=30)
        return con

    def get(self, doc_id: str) -> dict:
        with self.connect() as con:
            row = con.execute("SELECT body FROM documents WHERE id=?", (doc_id,)).fetchone()
        if row is None:
            raise KeyError(doc_id)
        return self._read_document(row[0])

    def all(self) -> list[dict]:
        with self.connect() as con:
            return [self._read_document(row[0]) for row in con.execute("SELECT body FROM documents")]

    def put(self, doc: dict):
        with self.connect() as con:
            con.execute("INSERT INTO documents(id,body) VALUES(?,?)", (doc["id"], self._write_document(doc)))

    def update(self, doc_id: str, change: Callable[[dict], None]) -> dict:
        # Read/modify/write in one transaction, including edits during translation.
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT body FROM documents WHERE id=?", (doc_id,)).fetchone()
            if row is None:
                raise KeyError(doc_id)
            doc = self._read_document(row[0])
            change(doc)
            doc["updated_at"] = now()
            con.execute("UPDATE documents SET body=? WHERE id=?", (self._write_document(doc), doc_id))
        return doc

    def _write_document(self, doc: dict) -> str:
        result = dict(doc)
        for field in ("pdf_path", "asset_root"):
            if result.get(field):
                path = Path(result[field]).resolve()
                if path.is_relative_to(self.root):
                    result[field] = str(path.relative_to(self.root))
        return json.dumps(result, ensure_ascii=False)

    def _read_document(self, body: str) -> dict:
        doc = json.loads(body)
        for field in ("pdf_path", "asset_root"):
            value = doc.get(field)
            if not value:
                continue
            path = Path(value)
            if not path.is_absolute():
                doc[field] = str(self.root / path)
            else:
                # Relocate older absolute records after copying the complete data directory.
                parts = path.parts
                marker = ("documents", doc["id"])
                for index in range(len(parts) - 1):
                    if parts[index:index + 2] == marker:
                        candidate = self.root.joinpath(*parts[index:])
                        if candidate.exists():
                            doc[field] = str(candidate)
                        break
        return doc

    def delete(self, doc_id: str):
        with self.connect() as con:
            con.execute("DELETE FROM documents WHERE id=?", (doc_id,))


DEFAULT_SETTINGS = {
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "",
    "json_mode": True,
    "batch_chars": 5500,
    "glossary": "Large Language Model = 大语言模型\nagent = 智能体",
    "mineru_command": "mineru",
    "mineru_backend": "pipeline",
    "parser": "existing",
    "mineru_token": "",
    "library_path": os.environ.get("PAPER_TRANSLATE_LIBRARY", str(Path.home() / "MinerU")),
}


class Settings:
    def __init__(self, root: Path):
        self.path = root / "settings.json"

    def get(self) -> dict:
        values = dict(DEFAULT_SETTINGS)
        if self.path.exists():
            values.update(json.loads(self.path.read_text()))
        values["api_key"] = values["api_key"] or os.environ.get("PAPER_TRANSLATE_API_KEY", "")
        return values

    def public(self) -> dict:
        values = self.get()
        for key in ("api_key", "mineru_token"):
            values[key + "_set"] = bool(values.pop(key, ""))
        return values

    def save(self, values: dict):
        current = self.get()
        for key in DEFAULT_SETTINGS:
            if key in values:
                current[key] = values[key]
        # Omitted secrets are retained. Explicit empty values clear them.
        temp = self.path.with_suffix(".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        temp.replace(self.path)


def summary(doc: dict) -> dict:
    fields = {key: value for key, value in doc.items() if key not in ("blocks", "pdf_path", "asset_root")}
    blocks = doc.get("blocks", [])
    eligible = [b for b in blocks if b["translatable"]]
    fields.update(
        block_count=len(blocks),
        total=len(eligible),
        translated=sum(bool(b.get("translation")) for b in eligible),
    )
    return fields
