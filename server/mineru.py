from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Callable

import httpx
from pypdf import PdfReader

from .paragraphs import merge_layout_breaks

SKIP = {"header", "footer", "page_number", "page_header", "page_footer", "aside_text"}


def flatten(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(flatten(v) for v in value)
    if isinstance(value, dict):
        text = flatten(value.get("content", value.get("text", value.get("item_content", ""))))
        if value.get("type") in ("equation_inline", "inline_equation"):
            return f"${text}$"
        return text
    return ""


def normalize_item(item: dict, page: int) -> dict:
    """Adapt V1 and page-grouped V2 content lists to our own contract."""
    kind = item.get("type", "text")
    payload = item.get("content", {})
    content = payload if isinstance(payload, dict) else {}
    level = item.get("text_level", content.get("level", 0)) or 0
    asset = item.get("img_path", "")
    image_source = content.get("image_source", {})
    if isinstance(image_source, dict):
        asset = asset or image_source.get("path", "")
    if kind in ("image", "chart", "table"):
        prefix = kind
        source = content.get(prefix + "_source", {})
        if isinstance(source, dict):
            asset = asset or source.get("path", "")
        caption = item.get(prefix + "_caption", content.get(prefix + "_caption", item.get("image_caption", [])))
        text = flatten(caption) if isinstance(caption, (str, list)) else ""
        body = item.get("table_body", content.get("table_body", content.get("html", "")))
        if isinstance(body, dict):
            body = body.get("html", body.get("content", ""))
        if body:
            text += "\n\n" + flatten(body)
            asset = ""  # Render structured table; image remains a fallback below.
        if not text.strip() and not asset:
            asset = item.get("img_path", "")
        footnote = flatten(item.get(prefix + "_footnote", content.get(prefix + "_footnote", [])))
        if footnote:
            text += "\n\n" + footnote
    elif kind in ("equation", "equation_interline", "interline_equation"):
        kind = "equation"
        text = item.get("text") or flatten(content.get("math_content", content.get("equation", content.get("equation_content", payload))))
        if text and not text.startswith("$$"):
            text = "$$\n" + text.strip("$ \n") + "\n$$"
        if text:
            asset = ""
    elif kind in ("code", "algorithm"):
        caption = flatten(content.get(kind + "_caption", item.get("code_caption", [])))
        body = str(item.get("code_body", flatten(content.get(kind + "_content", payload))))
        fence = "`" * max(3, max((len(x) + 1 for x in re.findall(r"`+", body)), default=3))
        text = (caption + "\n\n" if caption else "") + fence + "\n" + body + "\n" + fence
        kind = "code"
    elif kind == "list":
        items = item.get("list_items", content.get("list_items", []))
        text = "\n".join("- " + re.sub(r"^[•·]\s*", "", flatten(v)) for v in items)
    else:
        text = item.get("text")
        if text is None:
            for key in ("title_content", "paragraph_content", "page_footnote_content", "text_content"):
                if key in content:
                    text = flatten(content[key])
                    break
        text = flatten(text if text is not None else payload)
        if kind == "title" or level:
            kind = "heading"
        elif kind in ("page_footnote", "footnote"):
            kind = "footnote"
        elif kind not in SKIP:
            kind = "paragraph"
    return {
        "type": kind, "original": str(text).strip(), "level": min(int(level or 1), 6),
        "asset": asset, "page_index": int(item.get("page_idx", page)), "bbox": item.get("bbox"),
        "reference": item.get("sub_type") == "ref_text" or content.get("list_type") in ("ref_list", "reference_list"),
    }


def read_content(directory: Path) -> tuple[list[dict], str]:
    v1 = sorted(directory.glob("*_content_list.json")) + sorted(directory.glob("content_list.json"))
    v2 = sorted(directory.glob("*content_list_v2.json"))
    if not v1 and not v2:
        for child in sorted(directory.iterdir()):
            if child.is_dir() and child.name != "images":
                try:
                    return read_content(child)
                except ValueError:
                    pass
        raise ValueError("未找到 MinerU content_list JSON。请导入包含原 PDF、content_list.json 和 images 的完整结果目录。")
    source = (v1 or v2)[0]
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("不支持的内容列表格式，应为 MinerU V1 或 V2 数组。")
    result = []
    for page, entry in enumerate(data):
        for item in (entry if isinstance(entry, list) else [entry]):
            if not isinstance(item, dict):
                continue
            block = normalize_item(item, page if isinstance(entry, list) else 0)
            if block["type"] not in SKIP and (block["original"] or block["asset"]):
                result.append(block)
    return result, str(source.parent)


def build_document(directory: Path, doc_id: str, pdf: Path | None = None) -> dict:
    blocks, asset_root = read_content(directory)
    directory = Path(asset_root)
    pdfs = sorted(directory.glob("*origin.pdf")) or sorted(directory.glob("*.pdf"))
    pdf = pdf or (pdfs[0] if pdfs else None)
    if pdf is None:
        raise ValueError("解析结果中没有原 PDF。请将原 PDF 一起放入目录，或通过 ZIP 与 PDF 配对导入。")
    reader = PdfReader(pdf)
    if reader.is_encrypted:
        raise ValueError("请先解密 PDF 再导入。")
    pages = [{"width": float(p.mediabox.width), "height": float(p.mediabox.height), "rotation": int(p.get('/Rotate', 0))} for p in reader.pages]
    title = next((b["original"] for b in blocks if b["type"] == "heading"), pdf.stem)
    section_id = "front"
    references = False
    normalized = []
    for i, block in enumerate(blocks):
        page = block.pop("page_index")
        bbox = block.pop("bbox")
        if not 0 <= page < len(pages):
            raise ValueError(f"段落页码 {page} 超出原 PDF 范围，请确认 PDF 与解析结果匹配。")
        # Content lists use normalized 0..1000 boxes; do not infer scale from individual boxes.
        locations = []
        if isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(x, (int, float)) and math.isfinite(x) for x in bbox):
            box = [max(0.0, min(1.0, float(x) / 1000)) for x in bbox]
            if box[2] > box[0] and box[3] > box[1]:
                locations = [{"page_index": page, "bbox": box}]
        block_id = f"b{i:05d}_" + hashlib.sha256(block["original"].encode()).hexdigest()[:8]
        if block["type"] == "heading":
            section_id = block_id
            references = bool(re.match(r"^(?:[\d.]+\s*)?(references|bibliography)\b", block["original"], re.I))
        reference = block.pop("reference")
        eligible = bool(block["original"]) and block["type"] not in ("equation", "code") and not references and not reference
        normalized.append({
            **block, "id": block_id, "section_id": section_id, "source_locations": locations,
            "source_page": page, "translation": "", "translatable": eligible,
            "status": "untranslated" if eligible else "preserved", "revision": 0,
        })
    if not normalized:
        raise ValueError("解析结果没有可展示的内容。")
    return {"title": title, "blocks": merge_layout_breaks(normalized), "pages": pages, "pdf_path": str(pdf.resolve()), "asset_root": asset_root}


def discover(root: Path) -> list[dict]:
    if not root.is_dir():
        return []
    results = []
    candidates = [root] + [p for p in sorted(root.iterdir()) if p.is_dir() and not p.name.startswith(".")]
    for directory in candidates:
        sources = list(directory.glob("*content_list.json")) or list(directory.glob("*content_list_v2.json"))
        pdfs = list(directory.glob("*origin.pdf")) or list(directory.glob("*.pdf"))
        if sources and pdfs:
            results.append({"path": str(directory), "name": directory.name.split(".pdf-")[0], "pdf_name": pdfs[0].name})
    return results


def safe_extract(source: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as z:
        if sum(i.file_size for i in z.infolist()) > 1024 * 1024 * 1024 or len(z.infolist()) > 20000:
            raise ValueError("ZIP 解压体积或文件数量超出限制。")
        for info in z.infolist():
            target = (destination / info.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("ZIP 包含不安全的文件路径。")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("ZIP 不允许包含符号链接。")
        z.extractall(destination)


def python_executable(value: str) -> str:
    executable = str(Path(value).expanduser())
    if not value.strip() or not (shutil.which(executable) or Path(executable).is_file()):
        raise ValueError("未找到 Python 解释器，请在解析设置中填写已安装 MinerU 4 的 Python 可执行文件。")
    return executable


def python_runtime(value: str) -> dict:
    try:
        executable = python_executable(value)
        result = subprocess.run([executable, "-c", "from importlib.metadata import version; print(version('mineru'))"],
                                capture_output=True, text=True, timeout=5, check=True)
        version = result.stdout.strip()
        return {"available": version.startswith("4."), "version": version or None}
    except (ValueError, OSError, subprocess.SubprocessError):
        return {"available": False, "version": None}


def run_python(pdf: Path, output: Path, settings: dict, cancelled: Callable[[], bool]):
    if cancelled():
        return
    executable = python_executable(settings["mineru_python"])
    if settings["mineru_tier"] not in ("basic", "standard", "advanced", "flash"):
        raise ValueError("未知 MinerU 解析档位。")
    if not python_runtime(executable)["available"]:
        raise ValueError("该 Python 环境尚未安装受支持的 MinerU 4，请安装 MinerU 4 或切换到云端 API。")
    if cancelled():
        return
    worker = Path(__file__).resolve().parent.parent / "scripts" / "parse_mineru4.py"
    args = [executable, str(worker), "--pdf", str(pdf), "--output", str(output), "--tier", settings["mineru_tier"]]
    # A dedicated process keeps model dependencies isolated and permits cancellation.
    log = output.parent / "mineru.log"
    with log.open("w") as handle:
        process = subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
        started = time.monotonic()
        while process.poll() is None:
            if cancelled() or time.monotonic() - started > 3600:
                import signal
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise ValueError("解析已取消或超时。")
            time.sleep(0.5)
        if process.returncode:
            raise ValueError("MinerU Python API 解析失败，请查看文档目录下的 mineru.log。")


def run_cloud(pdf: Path, output: Path, settings: dict, cancelled: Callable[[], bool]):
    if cancelled():
        raise ValueError("解析已取消。")
    token = settings.get("mineru_token")
    if not token:
        raise ValueError("请先在设置中填写 MinerU API Token，或使用已有解析结果。")
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        r = client.post("https://mineru.net/api/v4/file-urls/batch", headers=headers,
                        json={"files": [{"name": "paper.pdf", "data_id": "paper"}], "model_version": "vlm"})
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise ValueError("MinerU 拒绝解析请求，请检查 Token 和解析额度。")
        batch = data["data"]["batch_id"]
        if cancelled():
            raise ValueError("解析已取消，尚未上传 PDF。")
        with pdf.open("rb") as f:
            client.put(data["data"]["file_urls"][0], content=f).raise_for_status()
        for _ in range(720):
            if cancelled():
                raise ValueError("已停止等待解析；云端已提交的解析任务可能继续运行。")
            r = client.get(f"https://mineru.net/api/v4/extract-results/batch/{batch}", headers=headers)
            r.raise_for_status()
            result = r.json()
            if result.get("code") != 0:
                raise ValueError("获取 MinerU 任务状态失败。")
            entry = result["data"]["extract_result"][0]
            if entry["state"] == "failed":
                raise ValueError("MinerU 云端解析失败，请检查 PDF。")
            if entry["state"] == "done":
                archive = output.parent / "result.zip"
                size = 0
                with client.stream("GET", entry["full_zip_url"]) as response:
                    response.raise_for_status()
                    with archive.open("wb") as f:
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > 400 * 1024 * 1024:
                                raise ValueError("解析结果下载体积超出限制。")
                            f.write(chunk)
                safe_extract(archive, output)
                return
            for _ in range(10):
                if cancelled():
                    raise ValueError("解析等待已取消。")
                time.sleep(0.5)
    raise ValueError("MinerU 云端解析等待超时。")
