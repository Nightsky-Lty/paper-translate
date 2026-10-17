from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from server import mineru
from server.exporter import export_zip, markdown
from server.jobs import Jobs
from server.store import Settings, Store, now
from server.translation import TranslationError, batches, parse_response, protect, restore, translate_batch

TEST_ROOT = tempfile.TemporaryDirectory()
os.environ["PAPER_TRANSLATE_DATA"] = TEST_ROOT.name
from server import app as application


def fixture(root: Path) -> Path:
    folder = root / "example"
    folder.mkdir(parents=True)
    pdf = PdfWriter()
    pdf.add_blank_page(width=600, height=800)
    pdf.add_blank_page(width=600, height=800)
    pdf.write(folder / "paper_origin.pdf")
    content = [
        {"type": "text", "text": "Example paper", "text_level": 1, "page_idx": 0, "bbox": [100,100,900,160]},
        {"type": "text", "text": "Use $x^2$ in the method [1].", "page_idx": 0, "bbox": [100,200,900,350]},
        {"type": "equation", "text": "x^2+y^2", "page_idx": 0, "bbox": [200,400,800,450]},
        {"type": "image", "img_path": "images/figure.png", "image_caption": ["Figure 1: Overview."], "page_idx": 1, "bbox": [100,100,900,350]},
        {"type": "text", "text": "References", "text_level": 1, "page_idx": 1, "bbox": [100,500,900,550]},
        {"type": "text", "text": "[1] Original reference.", "page_idx": 1, "bbox": [100,600,900,650]},
        {"type": "header", "text": "Ignore header", "page_idx": 1, "bbox": [100,0,900,30]},
    ]
    (folder / "paper_content_list.json").write_text(json.dumps(content))
    (folder / "images").mkdir()
    (folder / "images" / "figure.png").write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jAZkAAAAASUVORK5CYII="))
    return folder


class ParsingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = fixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_v1_geometry_and_preserved_blocks(self):
        doc = mineru.build_document(self.source, "test")
        self.assertEqual(len(doc["pages"]), 2)
        self.assertEqual(len(doc["blocks"]), 6)
        self.assertEqual(doc["blocks"][1]["source_locations"][0]["bbox"], [.1,.2,.9,.35])
        self.assertEqual(doc["blocks"][3]["source_locations"][0]["page_index"], 1)
        self.assertFalse(doc["blocks"][2]["translatable"])
        self.assertFalse(doc["blocks"][-1]["translatable"])
        self.assertEqual(len({b["id"] for b in doc["blocks"]}), 6)

    def test_v2_preserves_math_and_page(self):
        (self.source / "paper_content_list.json").unlink()
        content = [[{"type":"title","content":{"title_content":[{"type":"text","content":"Title"}],"level":1},"bbox":[10,20,900,100]}],[{"type":"paragraph","content":{"paragraph_content":[{"type":"text","content":"Let "},{"type":"equation_inline","content":"x"}]},"bbox":[100,200,900,300]}]]
        (self.source / "content_list_v2.json").write_text(json.dumps(content))
        doc = mineru.build_document(self.source, "test")
        self.assertEqual(doc["blocks"][1]["original"], "Let $x$")
        self.assertEqual(doc["blocks"][1]["source_locations"][0]["page_index"], 1)

    def test_invalid_page_is_rejected(self):
        path = self.source / "paper_content_list.json"
        data = json.loads(path.read_text()); data[0]["page_idx"] = 30
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            mineru.build_document(self.source, "test")

    def test_v2_rich_blocks_preserve_equation_table_list_and_algorithm(self):
        equation=mineru.normalize_item({"type":"equation_interline","content":{"math_content":"x^2", "image_source":{"path":"images/eq.jpg"}},"bbox":[0,0,500,100]},0)
        self.assertEqual(equation["original"],"$$\nx^2\n$$")
        self.assertEqual(equation["asset"],"")
        table=mineru.normalize_item({"type":"table","content":{"table_caption":[{"type":"text","content":"Caption"}],"html":"<table><tr><td>Data</td></tr></table>","table_footnote":[{"type":"text","content":"Important footnote"}],"image_source":{"path":"images/table.jpg"}}},0)
        self.assertIn("<td>Data</td>",table["original"])
        self.assertIn("Important footnote",table["original"])
        self.assertFalse(table["asset"])
        items=mineru.normalize_item({"type":"list","content":{"list_items":[{"item_content":[{"type":"text","content":"• First item"}]}]}},1)
        self.assertEqual(items["original"],"- First item")
        algorithm=mineru.normalize_item({"type":"algorithm","content":{"algorithm_content":[{"type":"text","content":"Step one"}]}},1)
        self.assertEqual(algorithm["type"],"code")
        self.assertIn("Step one",algorithm["original"])

    def test_image_only_equation_has_fallback(self):
        block=mineru.normalize_item({"type":"equation_interline","content":{"image_source":{"path":"images/equation.jpg"}}},0)
        self.assertEqual(block["asset"],"images/equation.jpg")
        self.assertFalse(block["original"])

    def test_zip_traversal_is_rejected(self):
        archive = self.root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("../escaped.txt", "bad")
        with self.assertRaises(ValueError):
            mineru.safe_extract(archive, self.root / "output")
        self.assertFalse((self.root / "escaped.txt").exists())

    def test_export_modes_and_portable_assets(self):
        doc = mineru.build_document(self.source, "test")
        doc.update(id="test", created_at=now(), updated_at=now(), source_path="private", job={})
        for b in doc["blocks"]:
            if b["translatable"]: b["translation"] = "中文：" + b["original"]
        paragraph, _ = markdown(doc, "paragraph")
        self.assertIn("Use $x^2$", paragraph)
        self.assertIn("中文：Use $x^2$", paragraph)
        self.assertIn("$$\nx^2+y^2\n$$", paragraph)
        section, _ = markdown(doc, "section")
        self.assertLess(section.index("Use $x^2$"), section.index("中文：Example paper"))
        with zipfile.ZipFile(io.BytesIO(export_zip(doc, "zh"))) as z:
            self.assertIn("assets/figure.png", z.namelist())
            self.assertIn("![](assets/figure.png)", z.read("paper.md").decode())
            exported = json.loads(z.read("paper.json"))
            self.assertNotIn("pdf_path", exported)
            self.assertNotIn("source_path", exported)
            self.assertIn("source_locations", exported["blocks"][0])


class TranslationTests(unittest.TestCase):
    def test_protection_roundtrip(self):
        text = 'Keep $x^2$, $$y$$, `code`, [1, 2], https://example.com and <td>A</td>.'
        masked, values = protect(text)
        self.assertNotIn("$x^2$", masked)
        self.assertEqual(restore(masked, values), text)

    def test_literal_placeholder_collision(self):
        text = 'Literal ⟦KEEP_0⟧ and $x$.'
        masked, values = protect(text)
        self.assertEqual(restore(masked, values), text)

    def test_missing_duplicate_or_unknown_placeholder(self):
        masked, values = protect("Test $x$.")
        for broken in ("Test.", masked + masked, masked + " ⟦KEEP_999⟧"):
            with self.assertRaises(TranslationError): restore(broken, values)

    def test_ids_must_be_complete_unique_and_nonempty(self):
        for items in ([{"id":"a","text":"译文"}], [{"id":"a","text":"译文"},{"id":"a","text":"重复"}], [{"id":"a","text":""},{"id":"b","text":"译文"}]):
            with self.assertRaises(TranslationError): parse_response(json.dumps({"translations":items}), ["a","b"])

    def test_table_tags_cannot_be_reordered(self):
        masked, values = protect("<table><tr><td>Hello</td></tr></table>")
        self.assertEqual(restore(masked,values),"<table><tr><td>Hello</td></tr></table>")
        broken=masked.replace("⟦KEEP_0⟧","TEMP").replace("⟦KEEP_1⟧","⟦KEEP_0⟧").replace("TEMP","⟦KEEP_1⟧")
        with self.assertRaises(TranslationError):restore(broken,values)

    def test_batch_respects_section_boundaries(self):
        blocks = [{"id":str(i),"original":"x"*300,"section_id":str(i//2)} for i in range(5)]
        chunks = list(batches(blocks, 1000))
        self.assertEqual([len(c) for c in chunks], [2,2,1])

    def test_provider_receives_only_ids_text_and_context(self):
        with patch("server.translation.httpx.Client") as client:
            response = httpx.Response(200, request=httpx.Request("POST","https://provider.test/v1/chat/completions"), json={"choices":[{"finish_reason":"stop","message":{"content":json.dumps({"translations":[{"id":"a","text":"使用 ⟦KEEP_0⟧。"}]})}}]})
            client.return_value.__enter__.return_value.post.return_value = response
            settings = {"model":"test","base_url":"https://provider.test/v1","api_key":"secret","json_mode":True,"glossary":""}
            result = translate_batch([{"id":"a","original":"Use $x$.","source_locations":[{"page_index":20}]}],settings)
            self.assertEqual(result["a"],"使用 $x$。")
            call = client.return_value.__enter__.return_value.post.call_args
            payload = json.loads(call.kwargs["json"]["messages"][1]["content"])
            self.assertEqual(set(payload["blocks"][0]), {"id","text"})
            self.assertNotIn("source_locations", str(call.kwargs["json"]))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = fixture(self.root / "library")
        self.store = Store(self.root / "data")
        self.settings = Settings(self.store.root)
        self.settings.save({"library_path":str(self.root / "library")})
        self.jobs = Jobs(self.store,self.settings)
        self.patches = [patch.object(application,"store",self.store),patch.object(application,"settings",self.settings),patch.object(application,"jobs",self.jobs)]
        for p in self.patches:p.start()
        self.client = TestClient(application.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None)
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def import_doc(self):
        response = self.client.post("/api/import/local",json={"path":str(self.source)})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_import_is_snapshot_and_idempotent(self):
        doc = self.import_doc()
        self.assertEqual(self.import_doc()["id"], doc["id"])
        self.assertNotIn("pdf_path", doc)
        (self.source / "paper_origin.pdf").unlink()
        self.assertEqual(self.client.get(doc["pdf_url"]).status_code,200)
        self.assertEqual(self.client.get(f"/api/documents/{doc['id']}/assets/images/figure.png").status_code,200)

    def test_import_outside_library_is_rejected(self):
        self.assertEqual(self.client.post("/api/import/local",json={"path":str(self.root)}).status_code,400)

    def test_edit_revision_and_export(self):
        doc = self.import_doc(); block = doc["blocks"][1]
        url = f"/api/documents/{doc['id']}/blocks/{block['id']}"
        response = self.client.patch(url,json={"translation":"人工修改 $x^2$ [1]。","revision":0})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()["blocks"][1]["status"],"edited")
        self.assertEqual(self.client.patch(url,json={"translation":"stale","revision":0}).status_code,409)
        export = self.client.get(f"/api/documents/{doc['id']}/export?format=zip&mode=paragraph")
        self.assertEqual(export.status_code,200)
        with zipfile.ZipFile(io.BytesIO(export.content)) as z:self.assertIn("人工修改",z.read("paper.md").decode())

    def test_secrets_are_not_returned(self):
        values = self.settings.get();values.update(api_key="private-key",mineru_token="private-token")
        self.assertEqual(self.client.put("/api/settings",json=values).status_code,200)
        public = self.client.get("/api/settings").json()
        self.assertNotIn("api_key",public)
        self.assertNotIn("mineru_token",public)
        self.assertTrue(public["api_key_set"])
        self.client.put("/api/settings",json=public)
        self.assertEqual(self.settings.get()["api_key"],"private-key")
        self.client.put("/api/settings",json={**public,"api_key":""})
        self.assertFalse(self.settings.get()["api_key"])

    def test_host_and_origin_protection(self):
        self.assertEqual(self.client.get("/api/settings",headers={"Origin":"https://untrusted.example"}).status_code,403)
        self.assertEqual(self.client.get("/api/settings",headers={"Host":"untrusted.example"}).status_code,403)

    def test_pdf_requires_parser_or_results(self):
        response = self.client.post("/api/import/files",files={"pdf":("test.pdf",(self.source/"paper_origin.pdf").read_bytes(),"application/pdf")})
        self.assertEqual(response.status_code,400)
        self.assertIn("解析器",response.json()["detail"])

    def test_zip_import_with_pdf(self):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,"w") as z:
            for p in self.source.rglob("*"):
                if p.is_file():z.write(p,"nested/"+str(p.relative_to(self.source)))
        response=self.client.post("/api/import/files",files={"archive":("result.zip",buffer.getvalue(),"application/zip")})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len(response.json()["blocks"]),6)

    def test_translation_job_preserves_manual_edits(self):
        doc = self.import_doc(); doc_id=doc["id"]
        changed_id = doc["blocks"][1]["id"]
        def fake_translate(chunk,*args):
            def edit(current):
                for b in current["blocks"]:
                    if b["id"]==changed_id:b.update(translation="人工译文",status="edited",revision=b["revision"]+1)
            self.store.update(doc_id,edit)
            return {b["id"]:"模型译文" for b in chunk}
        with patch("server.jobs.translate_batch",side_effect=fake_translate):
            self.jobs.translate(doc_id,None,threading.Event())
        saved=self.store.get(doc_id)
        self.assertEqual(next(b for b in saved["blocks"] if b["id"]==changed_id)["translation"],"人工译文")
        self.assertEqual(saved["blocks"][2]["translation"],"")
        self.assertTrue(saved["blocks"][0]["translation"])

    def test_resume_skips_completed_and_cancel_sends_no_request(self):
        doc=self.import_doc(); doc_id=doc["id"]
        self.store.update(doc_id,lambda d:d["blocks"][0].update(translation="已完成",revision=1))
        seen=[]
        def fake_translate(chunk,*args):
            seen.extend(b["id"] for b in chunk)
            return {b["id"]:"译文" for b in chunk}
        with patch("server.jobs.translate_batch",side_effect=fake_translate):
            self.jobs.translate(doc_id,None,threading.Event())
        self.assertNotIn(doc["blocks"][0]["id"],seen)
        event=threading.Event();event.set()
        with patch("server.jobs.translate_batch") as mocked:
            self.jobs.translate(doc_id,[doc["blocks"][1]["id"]],event)
            mocked.assert_not_called()

    def test_async_job_pause_rejects_duplicate_and_resumes(self):
        doc=self.import_doc(); doc_id=doc["id"]
        entered=threading.Event(); release=threading.Event()
        def delayed(chunk,*args):
            entered.set()
            release.wait(timeout=3)
            return {b["id"]:"已完成批次" for b in chunk}
        with patch("server.jobs.translate_batch",side_effect=delayed):
            start=self.client.post(f"/api/documents/{doc_id}/translate",json={})
            self.assertEqual(start.status_code,200)
            self.assertTrue(entered.wait(timeout=2))
            self.assertEqual(self.client.post(f"/api/documents/{doc_id}/translate",json={}).status_code,400)
            paused=self.client.post(f"/api/documents/{doc_id}/pause")
            self.assertEqual(paused.json()["job"]["state"],"stopping")
            release.set()
            for _ in range(100):
                if self.store.get(doc_id)["job"]["state"]=="paused":break
                time.sleep(.01)
            saved=self.store.get(doc_id)
            self.assertEqual(saved["job"]["state"],"paused")
            self.assertTrue(any(b["translation"] for b in saved["blocks"]))
        with patch("server.jobs.translate_batch",side_effect=lambda chunk,*args:{b["id"]:"后续译文" for b in chunk}):
            self.assertEqual(self.client.post(f"/api/documents/{doc_id}/translate",json={}).status_code,200)
            for _ in range(100):
                if self.store.get(doc_id)["job"]["state"]=="done":break
                time.sleep(.01)
            self.assertEqual(self.store.get(doc_id)["job"]["state"],"done")

    def test_model_failure_is_reported_without_overwriting(self):
        doc=self.import_doc(); doc_id=doc["id"]
        self.store.update(doc_id,lambda d:d["blocks"][0].update(translation="保留译文",revision=1))
        with patch("server.jobs.translate_batch",side_effect=TranslationError("译文段落 ID 不完整。")):
            self.jobs.run(doc_id,"translate",None,threading.Event())
        saved=self.store.get(doc_id)
        self.assertEqual(saved["job"]["state"],"error")
        self.assertEqual(saved["blocks"][0]["translation"],"保留译文")

    def test_cancelled_queued_parse_never_starts_parser(self):
        doc=self.import_doc()
        event=threading.Event();event.set()
        with patch.object(self.jobs,"parse") as parser:
            self.jobs.run(doc["id"],"parse",None,event)
            parser.assert_not_called()
        self.assertEqual(self.store.get(doc["id"])["job"]["state"],"paused")


if __name__=="__main__":
    unittest.main()
