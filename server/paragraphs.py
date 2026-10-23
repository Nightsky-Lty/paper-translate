"""Logical paragraphs retain the physical MinerU fragments and their locations."""
from __future__ import annotations

from copy import deepcopy
import re


def mergeable(left: dict, right: dict) -> bool:
    return bool(
        left.get("type") == right.get("type") == "paragraph"
        and left.get("translatable") and right.get("translatable")
        and left.get("section_id") == right.get("section_id")
        and not left.get("asset") and not right.get("asset")
        and left.get("original", "").strip() and right.get("original", "").strip()
        and len(left.get("source_parts", [left])) + len(right.get("source_parts", [right])) <= 50
        and len(left["original"]) + len(right["original"]) <= 100000
    )


def join_text(left: str, right: str) -> str:
    left, right = left.rstrip(), right.lstrip()
    # Only soft hyphens unambiguously mark a typesetting break. Preserve real
    # hyphens (e.g. "state-of-" + "the-art") rather than guessing a dictionary word.
    if left.endswith("\u00ad"):
        return left[:-1] + right
    if re.search(r"[A-Za-z]-$", left) and re.match(r"[a-z]", right):
        return left + right
    return left + " " + right


def merge_pair(left: dict, right: dict, method: str = "manual") -> dict:
    if not mergeable(left, right):
        raise ValueError("只能合并同一节中相邻的正文段落，不能跨过标题、图表、公式或参考文献。")
    merged = deepcopy(left)
    merged.update(
        original=join_text(left["original"], right["original"]),
        translation="", status="untranslated",
        revision=max(left["revision"], right["revision"]) + 1,
        source_parts=deepcopy(left.get("source_parts", [left]) + right.get("source_parts", [right])),
        merge_method=method,
        source_locations=deepcopy(left["source_locations"] + right["source_locations"]),
    )
    return merged


def split_paragraph(block: dict) -> list[dict]:
    parts = deepcopy(block.get("source_parts", []))
    if len(parts) < 2:
        raise ValueError("该段落没有可恢复的原始分段。")
    for part in parts:
        # An editor opened before a merge must not become valid again on undo.
        part["revision"] = max(block["revision"], part["revision"]) + 1
    return parts


def layout_continuation(left: dict, right: dict) -> bool:
    if not mergeable(left, right):
        return False
    before, after = left.get("source_locations", []), right.get("source_locations", [])
    if not before or not after:
        return False
    tail, head = before[-1], after[0]
    page_break = (tail["page_index"] + 1 == head["page_index"]
                  and tail["bbox"][3] >= 0.75 and head["bbox"][1] <= 0.25)
    # A column break runs from the bottom of the left column back to the top
    # of the right one. Full-width blocks and ordinary vertical neighbors fail.
    column_break = (tail["page_index"] == head["page_index"]
                    and tail["bbox"][2] <= 0.58 and head["bbox"][0] >= 0.42
                    and head["bbox"][0] >= tail["bbox"][2] - 0.02
                    and tail["bbox"][3] >= 0.7 and head["bbox"][1] <= 0.55
                    and tail["bbox"][1] - head["bbox"][1] >= 0.25)
    if (
        not (page_break or column_break)
        or tail["bbox"][2] - tail["bbox"][0] < 0.2
        or head["bbox"][2] - head["bbox"][0] < 0.2
    ):
        return False
    text = left["original"].rstrip()
    # Ignore trailing numeric citations when checking for a sentence ending.
    text = re.sub(r"(?:\s*\[\d[\d\s,;–-]*\])+\s*$", "", text)
    text = text.rstrip(" \t\n\"'”’)]}")
    next_text = right["original"].lstrip(" \t\n\"'“‘(")
    return bool(
        len(text) >= 20 and text[-1] not in ".!?。！？:;：；"
        and re.match(r"[a-z]", next_text)
    )


def merge_layout_breaks(blocks: list[dict]) -> list[dict]:
    result: list[dict] = []
    for block in blocks:
        # Never silently replace translations in an existing document.
        if (result and not result[-1].get("translation") and not block.get("translation")
                and layout_continuation(result[-1], block)):
            result[-1] = merge_pair(result[-1], block, method="layout")
        else:
            result.append(block)
    return result
