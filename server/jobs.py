from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .mineru import build_document, run_python, run_cloud
from .store import Settings, Store, now
from .translation import batches, translate_batch


class Jobs:
    def __init__(self, store: Store, settings: Settings):
        self.store, self.settings = store, settings
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="paper")
        self.events: dict[str, threading.Event] = {}
        self.lock = threading.RLock()
        self.parse_lock = threading.Lock()

    def start(self, doc_id: str, kind: str, block_ids: list[str] | None = None):
        with self.lock:
            doc = self.store.get(doc_id)
            if doc_id in self.events:
                raise ValueError("该论文已有运行中的任务，请等待结束或先暂停。")
            if kind == "translate":
                if not self.settings.get()["model"] or not self.settings.get()["base_url"]:
                    raise ValueError("请先配置翻译接口地址和模型。")
                valid = {b["id"] for b in doc["blocks"] if b["translatable"]}
                if block_ids is not None and (not block_ids or not set(block_ids) <= valid):
                    raise ValueError("选中的段落不存在或不需要翻译。")
                if not valid:
                    raise ValueError("没有可翻译的段落，请先完成 PDF 解析。")
            event = threading.Event()
            self.events[doc_id] = event
            self.store.update(doc_id, lambda d: d.update(job={"kind": kind, "state": "running", "message": "正在解析 PDF…" if kind == "parse" else "正在翻译…", "started_at": now()}))
            self.pool.submit(self.run, doc_id, kind, block_ids, event)

    def pause(self, doc_id: str):
        with self.lock:
            if doc_id in self.events:
                self.events[doc_id].set()
                self.store.update(doc_id, lambda d: d["job"].update(state="stopping", message="等待当前请求结束后暂停…"))

    def run(self, doc_id: str, kind: str, block_ids: list[str] | None, event: threading.Event):
        try:
            if not event.is_set():
                if kind == "parse":
                    self.parse(doc_id, event)
                else:
                    self.translate(doc_id, block_ids, event)
            if event.is_set():
                self.store.update(doc_id, lambda d: d["job"].update(state="paused", message="已暂停，已完成的内容已保存。"))
            else:
                self.store.update(doc_id, lambda d: d["job"].update(state="done", message="解析完成，可以开始翻译。" if kind == "parse" else "翻译完成。"))
        except Exception as exc:
            # Only curated validation errors are shown; provider bodies / headers never are.
            text = str(exc) if isinstance(exc, ValueError) else "任务失败，请检查本地文件或服务配置后重试。"
            state = "paused" if event.is_set() else "error"
            self.store.update(doc_id, lambda d: d["job"].update(state=state, message=text))
        finally:
            with self.lock:
                self.events.pop(doc_id, None)

    def parse(self, doc_id: str, event: threading.Event):
        self.store.update(doc_id, lambda d: d["job"].update(message="等待解析资源…"))
        while not self.parse_lock.acquire(timeout=0.5):
            if event.is_set():
                return
        try:
            if not event.is_set():
                self.store.update(doc_id, lambda d: d["job"].update(message="正在解析 PDF…"))
                self._parse(doc_id, event)
        finally:
            self.parse_lock.release()

    def _parse(self, doc_id: str, event: threading.Event):
        doc, settings = self.store.get(doc_id), self.settings.get()
        output = self.store.root / "documents" / doc_id / "parsed"
        output.mkdir(parents=True, exist_ok=True)
        if settings["parser"] == "cloud":
            run_cloud(Path(doc["pdf_path"]), output, settings, event.is_set)
        elif settings["parser"] == "python":
            run_python(Path(doc["pdf_path"]), output, settings, event.is_set)
        else:
            raise ValueError("请在设置中选择 MinerU Python API 或 MinerU 云端 API。")
        if event.is_set():
            return
        parsed = build_document(output, doc_id, Path(doc["pdf_path"]))
        self.store.update(doc_id, lambda d: d.update(parsed))

    def translate(self, doc_id: str, block_ids: list[str] | None, event: threading.Event):
        doc, settings = self.store.get(doc_id), self.settings.get()
        selected = [b for b in doc["blocks"] if b["translatable"] and ((b["id"] in block_ids) if block_ids is not None else not b.get("translation"))]
        chunks = list(batches(selected, int(settings["batch_chars"])))
        for index, chunk in enumerate(chunks):
            if event.is_set():
                return
            # Do not overwrite a revision edited after this job started.
            revisions = {b["id"]: b["revision"] for b in chunk}
            section = next((b["original"] for b in doc["blocks"] if b["id"] == chunk[0]["section_id"]), "")
            first_index = next(i for i, b in enumerate(doc["blocks"]) if b["id"] == chunk[0]["id"])
            context = f"Paper: {doc['title']}\nSection: {section}\nPrevious paragraph: " + (doc["blocks"][first_index - 1]["original"] if first_index else "")
            self.store.update(doc_id, lambda d: d["job"].update(message=f"正在翻译第 {index + 1} / {len(chunks)} 批…"))
            result = translate_batch(chunk, settings, context, event.is_set)
            def save(d):
                for block in d["blocks"]:
                    if block["id"] in result and block["revision"] == revisions[block["id"]]:
                        block.update(translation=result[block["id"]], status="translated", revision=block["revision"] + 1)
            self.store.update(doc_id, save)

    def shutdown(self):
        with self.lock:
            for event in self.events.values():
                event.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
