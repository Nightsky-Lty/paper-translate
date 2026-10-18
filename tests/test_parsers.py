from __future__ import annotations

import io
import json
import signal
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from server import mineru
from server.store import DEFAULT_SETTINGS, Settings


class ParserSettingsTests(unittest.TestCase):
    def test_migrates_existing_python_worker_and_drops_old_fields_on_save(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(Path(folder))
            settings.path.write_text(json.dumps({
                "parser":"cli", "mineru_command":'"/env with space/bin/python" /app/scripts/parse_mineru4.py',
                "mineru_backend":"standard", "api_key":"test-private-key", "mineru_token":"test-token",
            }))
            migrated = settings.get()
            self.assertEqual(migrated["parser"], "python")
            self.assertEqual(migrated["mineru_python"], "/env with space/bin/python")
            self.assertEqual(migrated["mineru_tier"], "standard")
            self.assertNotIn("mineru_command", migrated)
            settings.save({"glossary":"new glossary"})
            saved = json.loads(settings.path.read_text())
            self.assertNotIn("mineru_backend", saved)
            self.assertNotIn("mineru_command", saved)
            self.assertEqual(saved["api_key"], "test-private-key")
            self.assertEqual(saved["mineru_token"], "test-token")

    def test_legacy_native_commands_are_not_used_as_python_executables(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(Path(folder))
            for command in ("mineru", "mineru -b pipeline", '"unfinished'):
                settings.path.write_text(json.dumps({"parser":"cli", "mineru_command":command, "mineru_backend":"pipeline"}))
                self.assertEqual(settings.get()["mineru_python"], DEFAULT_SETTINGS["mineru_python"])
                self.assertEqual(settings.get()["mineru_tier"], "basic")
            settings.path.write_text(json.dumps({"parser":"existing"}))
            self.assertEqual(settings.get()["parser"], "python")


class PythonParserTests(unittest.TestCase):
    def test_runtime_detects_supported_versions_and_handles_missing_dependencies(self):
        for version, available in (("4.0.12\n",True), ("2.7.6\n",False)):
            with patch("server.mineru.subprocess.run", return_value=SimpleNamespace(stdout=version)):
                self.assertEqual(mineru.python_runtime(sys.executable)["available"], available)
        with patch("server.mineru.subprocess.run", side_effect=subprocess.TimeoutExpired("python",5)):
            self.assertFalse(mineru.python_runtime(sys.executable)["available"])
        self.assertFalse(mineru.python_runtime("/missing/environment/python")["available"])

    def test_worker_arguments_keep_paths_separate_and_cancel_before_start(self):
        with tempfile.TemporaryDirectory(prefix="paper with spaces ") as folder:
            root = Path(folder)
            settings = {"mineru_python":sys.executable,"mineru_tier":"basic"}
            process = SimpleNamespace(returncode=0, poll=lambda:0)
            with patch("server.mineru.python_runtime", return_value={"available":True}), \
                 patch("server.mineru.subprocess.Popen", return_value=process) as spawn:
                mineru.run_python(root/"input paper.pdf",root/"output result",settings,lambda:False)
                args = spawn.call_args.args[0]
                self.assertEqual(args[0], sys.executable)
                self.assertEqual(args[args.index("--pdf")+1], str(root/"input paper.pdf"))
                self.assertNotIn("-b", args)
                self.assertNotIn("shell", spawn.call_args.kwargs)
                spawn.reset_mock()
                mineru.run_python(root/"input.pdf",root/"output",settings,lambda:True)
                spawn.assert_not_called()

    def test_pause_terminates_the_python_worker_process_group(self):
        with tempfile.TemporaryDirectory() as folder:
            process = SimpleNamespace(pid=12345, poll=lambda:None, wait=lambda timeout=None:0)
            cancelled = iter((False, False, True))
            with patch("server.mineru.python_runtime", return_value={"available":True}), \
                 patch("server.mineru.subprocess.Popen", return_value=process), \
                 patch("server.mineru.os.killpg") as kill:
                with self.assertRaisesRegex(ValueError, "取消"):
                    mineru.run_python(Path(folder)/"paper.pdf",Path(folder)/"output", {"mineru_python":sys.executable,"mineru_tier":"basic"},lambda:next(cancelled))
                kill.assert_called_once_with(12345, signal.SIGTERM)


class CloudParserTests(unittest.TestCase):
    def test_official_cloud_upload_poll_and_zip_download(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive,"w") as output:
            output.writestr("content_list.json", "[]")
        requests=[]
        def handler(request):
            requests.append((request.method,request.url.path))
            if request.url.path.endswith("file-urls/batch"):
                self.assertEqual(request.headers["Authorization"], "Bearer test-token")
                return httpx.Response(200,json={"code":0,"data":{"batch_id":"batch","file_urls":["https://storage.test/upload"]}})
            if request.url.path=="/upload":
                self.assertEqual(request.content,b"synthetic-pdf")
                return httpx.Response(200)
            if request.url.path.endswith("extract-results/batch/batch"):
                return httpx.Response(200,json={"code":0,"data":{"extract_result":[{"state":"done","full_zip_url":"https://storage.test/result.zip"}]}})
            return httpx.Response(200,content=archive.getvalue())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            pdf=root/"paper.pdf"
            pdf.write_bytes(b"synthetic-pdf")
            client=httpx.Client(transport=httpx.MockTransport(handler))
            with patch("server.mineru.httpx.Client", return_value=client):
                mineru.run_cloud(pdf,root/"parsed",{"mineru_token":"test-token"},lambda:False)
            self.assertEqual((root/"parsed/content_list.json").read_text(), "[]")
            self.assertEqual([method for method,path in requests],["POST","PUT","GET","GET"])


if __name__=="__main__":
    unittest.main()
