from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

MODES = {"zh", "paragraph", "section", "en"}


def render_block(block: dict, language: str, assets: set[str]) -> str:
    source = block["original"]
    text = source if language == "en" or not block["translatable"] else block.get("translation") or f"[待翻译]\n\n{source}"
    if block["type"] == "heading":
        text = "#" * block.get("level", 1) + " " + text
    if block.get("asset"):
        path = Path(block["asset"])
        asset = "assets/" + path.name
        assets.add(block["asset"])
        text = f"![]({asset})\n\n" + text
    return text.strip()


def markdown(doc: dict, mode: str) -> tuple[str, set[str]]:
    if mode not in MODES:
        raise ValueError("不支持的导出格式。")
    assets: set[str] = set()
    output = []
    if mode == "section":
        groups = []
        for block in doc["blocks"]:
            if not groups or groups[-1][0]["section_id"] != block["section_id"]:
                groups.append([])
            groups[-1].append(block)
        for group in groups:
            output.append("<!-- English -->\n\n" + "\n\n".join(render_block(b, "en", assets) for b in group))
            output.append("<!-- 中文 -->\n\n" + "\n\n".join(render_block(b, "zh", assets) for b in group))
            output.append("---")
    else:
        for block in doc["blocks"]:
            if mode == "paragraph" and block["translatable"]:
                output.extend([render_block(block, "en", assets), render_block(block, "zh", assets)])
            else:
                output.append(render_block(block, "en" if mode == "en" else "zh", assets))
    return "\n\n".join(filter(None, output)).strip() + "\n", assets


def portable_document(doc: dict) -> dict:
    # Machine-specific paths and job internals do not belong in portable exports.
    return {k: v for k, v in doc.items() if k not in ("pdf_path", "asset_root", "source_path", "job")}


def export_zip(doc: dict, mode: str) -> bytes:
    md, assets = markdown(doc, mode)
    buffer = io.BytesIO()
    root = Path(doc["asset_root"]).resolve()
    names = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("paper.md", md)
        portable = portable_document(doc)
        portable["blocks"] = [{**block, "asset": "assets/" + Path(block["asset"]).name if block.get("asset") else ""} for block in doc["blocks"]]
        archive.writestr("paper.json", json.dumps(portable, ensure_ascii=False, indent=2))
        for asset in sorted(assets):
            path = (root / asset).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError("导出所需图片缺失，请检查导入的 MinerU 结果是否完整。")
            name = "assets/" + path.name
            if name in names:
                raise ValueError("图片名称冲突，无法安全打包。")
            names.add(name)
            archive.write(path, name)
    return buffer.getvalue()
