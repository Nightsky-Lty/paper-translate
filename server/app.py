from __future__ import annotations

import json
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader

from . import mineru
from .exporter import export_zip, markdown, portable_document
from .jobs import Jobs
from .store import Settings, Store, now, summary
from .translation import translate_batch

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("PAPER_TRANSLATE_DATA", str(ROOT / "data")))
store = Store(DATA)
settings = Settings(store.root)
jobs = Jobs(store, settings)


@asynccontextmanager
async def lifespan(app):
    # Interrupted work is never silently billed again after a restart.
    for doc in store.all():
        if doc.get("job", {}).get("state") in ("running", "stopping"):
            store.update(doc["id"], lambda d: d["job"].update(state="paused", message="应用重启，任务已暂停。可继续未完成的翻译。"))
    yield
    jobs.shutdown()


app = FastAPI(title="纸间 · Paper Translate", lifespan=lifespan)


@app.middleware("http")
async def local_only(request: Request, call_next):
    # Prevent drive-by cross-origin requests to a local app with saved credentials.
    if request.url.path.startswith("/api"):
        host = urlparse("//" + request.headers.get("host", "")).hostname
        if host not in ("127.0.0.1", "localhost", "testserver", "::1"):
            return JSONResponse({"detail": "仅允许本机访问。"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin not in ("http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8765", "http://localhost:8765"):
            return JSONResponse({"detail": "不允许跨站访问本地应用。"}, status_code=403)
    return await call_next(request)


@app.exception_handler(KeyError)
async def missing(request, exc):
    return JSONResponse({"detail": "论文或段落不存在。"}, status_code=404)


@app.exception_handler(ValueError)
async def bad_value(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


def get_doc(doc_id: str):
    return store.get(doc_id)


def doc_response(doc):
    return {**summary(doc), "blocks": doc["blocks"], "pdf_url": f"/api/documents/{doc['id']}/pdf"}


def new_document(doc_id: str, title: str) -> dict:
    return {"id": doc_id, "title": title, "created_at": now(), "updated_at": now(), "blocks": [], "pages": [], "job": {"state": "idle", "kind": "parse", "message": ""}}


@app.get("/api/health")
def health():
    import shlex
    command = shlex.split(settings.get()["mineru_command"])
    return {"application": "paper-translate", "status": "ok", "mineru_desktop": Path("/Applications/MinerU.app").exists(), "mineru_cli": bool(command and (shutil.which(command[0]) or Path(command[0]).is_file()))}


@app.get("/api/settings")
def read_settings():
    return settings.public()


class SettingsBody(BaseModel):
    base_url: str = Field(min_length=1, max_length=1000)
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=4000)
    json_mode: bool = True
    batch_chars: int = Field(default=5500, ge=500, le=15000)
    glossary: str = Field(default="", max_length=30000)
    parser: str = "existing"
    mineru_command: str = Field(default="mineru", max_length=2000)
    mineru_backend: str = "pipeline"
    mineru_token: str | None = Field(default=None, max_length=4000)
    library_path: str = Field(default=str(Path.home() / "MinerU"), max_length=2000)


@app.put("/api/settings")
def save_settings(body: SettingsBody):
    url = urlparse(body.base_url)
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("接口地址需为有效的 HTTP(S) Base URL，不包含账号密码或查询参数。")
    if body.parser not in ("existing", "cli", "cloud"):
        raise ValueError("未知解析模式。")
    if body.mineru_backend not in ("pipeline", "vlm-auto-engine", "hybrid-auto-engine", "vlm-http-client"):
        raise ValueError("未知 MinerU backend。")
    values = body.model_dump(exclude_none=True)
    settings.save(values)
    return settings.public()


@app.post("/api/settings/test")
def test_connection():
    values = settings.get()
    result = translate_batch([{"id": "test", "original": "This is a connection test."}], values)
    return {"ok": True, "translation": result["test"]}


@app.get("/api/library")
def library():
    entries = mineru.discover(Path(settings.get()["library_path"]).expanduser())
    imported = {d.get("source_path"): d["id"] for d in store.all()}
    return [{**entry, "imported_id": imported.get(entry["path"])} for entry in entries]


class ImportBody(BaseModel):
    path: str


@app.post("/api/import/local")
def import_local(body: ImportBody):
    source = Path(body.path).expanduser().resolve()
    root = Path(settings.get()["library_path"]).expanduser().resolve()
    if not source.is_relative_to(root) or not source.is_dir():
        raise ValueError("请选择配置的 MinerU 论文库中的结果目录。")
    existing = next((d for d in store.all() if d.get("source_path") == str(source)), None)
    if existing:
        return doc_response(existing)
    doc_id = uuid.uuid4().hex
    destination = store.root / "documents" / doc_id / "parsed"
    destination.mkdir(parents=True)
    try:
        # Copy only parse artifacts and assets, not scripts, caches, or other user files.
        for file in source.iterdir():
            if file.is_file() and not file.is_symlink() and (file.suffix.lower() in (".json", ".pdf", ".md")):
                shutil.copy2(file, destination / file.name)
            elif file.is_dir() and file.name == "images":
                for image in file.rglob("*"):
                    if image.is_file() and not image.is_symlink() and image.resolve().is_relative_to(source):
                        target = destination / image.relative_to(source)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(image, target)
        parsed = mineru.build_document(destination, doc_id)
        doc = {**new_document(doc_id, source.name), **parsed, "source_path": str(source)}
        store.put(doc)
        return doc_response(doc)
    except Exception:
        shutil.rmtree(destination.parent, ignore_errors=True)
        raise


async def save_upload(upload: UploadFile, target: Path, limit: int):
    size = 0
    with target.open("wb") as f:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise ValueError(f"文件超过 {limit // 1024 // 1024} MB 限制。")
            f.write(chunk)
    if not size:
        raise ValueError("不能导入空文件。")


@app.post("/api/import/files")
async def import_files(pdf: UploadFile | None = File(default=None), archive: UploadFile | None = File(default=None)):
    if not pdf and not archive:
        raise ValueError("请选择 PDF 或 MinerU 结果 ZIP。")
    if not archive and settings.get()["parser"] == "existing":
        raise ValueError("只有 PDF 时需要解析器。请先选择本地 CLI / 云端解析，或同时导入 MinerU 结果 ZIP。")
    doc_id = uuid.uuid4().hex
    directory = store.root / "documents" / doc_id
    directory.mkdir(parents=True)
    try:
        pdf_path = None
        if pdf:
            pdf_path = directory / "original.pdf"
            await save_upload(pdf, pdf_path, 200 * 1024 * 1024)
            with pdf_path.open("rb") as f:
                prefix = f.read(1024)
            if not prefix.lstrip().startswith(b"%PDF-"):
                raise ValueError("文件不是有效的 PDF。")
            PdfReader(pdf_path)
        doc = new_document(doc_id, Path(pdf.filename or "Paper").stem if pdf else "Paper")
        if archive:
            archive_path = directory / "input.zip"
            await save_upload(archive, archive_path, 400 * 1024 * 1024)
            mineru.safe_extract(archive_path, directory / "parsed")
            doc.update(mineru.build_document(directory / "parsed", doc_id, pdf_path))
        else:
            doc["pdf_path"] = str(pdf_path)
            doc["asset_root"] = str(directory / "parsed")
        store.put(doc)
        if not archive:
            jobs.start(doc_id, "parse")
        return doc_response(store.get(doc_id))
    except (ValueError, HTTPException):
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(directory, ignore_errors=True)
        raise ValueError("无法读取 PDF 或结果 ZIP，请确认文件有效且包含完整解析结果。") from exc


@app.get("/api/documents")
def documents():
    return [summary(d) for d in sorted(store.all(), key=lambda d: d["updated_at"], reverse=True)]


@app.get("/api/documents/{doc_id}")
def document(doc_id: str):
    return doc_response(get_doc(doc_id))


@app.get("/api/documents/{doc_id}/pdf")
def pdf_file(doc_id: str):
    return FileResponse(get_doc(doc_id)["pdf_path"], media_type="application/pdf", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/documents/{doc_id}/assets/{asset_path:path}")
def asset_file(doc_id: str, asset_path: str):
    root = Path(get_doc(doc_id)["asset_root"]).resolve()
    path = (root / asset_path).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        raise HTTPException(404, "图片不存在。")
    return FileResponse(path)


class TranslateBody(BaseModel):
    block_ids: list[str] | None = None


@app.post("/api/documents/{doc_id}/translate")
def translate(doc_id: str, body: TranslateBody):
    jobs.start(doc_id, "translate", body.block_ids)
    return doc_response(store.get(doc_id))


@app.post("/api/documents/{doc_id}/parse")
def parse(doc_id: str):
    doc = get_doc(doc_id)
    if doc["blocks"]:
        raise ValueError("该论文已有解析结果，重新导入可创建新的解析版本。")
    jobs.start(doc_id, "parse")
    return doc_response(store.get(doc_id))


@app.post("/api/documents/{doc_id}/pause")
def pause(doc_id: str):
    get_doc(doc_id)
    jobs.pause(doc_id)
    return doc_response(store.get(doc_id))


class EditBody(BaseModel):
    translation: str = Field(max_length=100000)
    revision: int


@app.patch("/api/documents/{doc_id}/blocks/{block_id}")
def edit_block(doc_id: str, block_id: str, body: EditBody):
    def change(doc):
        block = next((b for b in doc["blocks"] if b["id"] == block_id), None)
        if block is None:
            raise KeyError(block_id)
        if not block["translatable"]:
            raise ValueError("公式、代码和参考文献保留原文，无需翻译。")
        if block["revision"] != body.revision:
            raise HTTPException(409, "段落已更新，请重新打开编辑器后保存。")
        block.update(translation=body.translation.strip(), revision=block["revision"] + 1,
                     status="edited" if body.translation.strip() else "untranslated")
    return doc_response(store.update(doc_id, change))


@app.get("/api/documents/{doc_id}/export")
def export(doc_id: str, mode: str = "paragraph", format: str = "zip"):
    doc = get_doc(doc_id)
    if mode not in ("zh", "paragraph", "section", "en"):
        raise ValueError("未知阅读格式。")
    if format == "json":
        data, media, filename = json.dumps(portable_document(doc), ensure_ascii=False, indent=2).encode(), "application/json", "paper.json"
    elif format == "md":
        data, media, filename = markdown(doc, mode)[0].encode(), "text/markdown; charset=utf-8", "paper.md"
    elif format == "zip":
        data, media, filename = export_zip(doc, mode), "application/zip", "paper.zip"
    else:
        raise ValueError("未知导出格式。")
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.delete("/api/documents/{doc_id}")
def delete(doc_id: str):
    doc = get_doc(doc_id)
    if doc.get("job", {}).get("state") in ("running", "stopping"):
        raise ValueError("请先暂停任务，等待任务停止后再移除。")
    store.delete(doc_id)
    shutil.rmtree(store.root / "documents" / doc_id, ignore_errors=True)
    return {"ok": True}


dist = ROOT / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
