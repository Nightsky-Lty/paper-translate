from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from server import app as application
from server.access import AccessPolicy, hash_password, parse_hash
from server.jobs import Jobs
from server.store import Settings, Store


PASSWORD = "test-only-password-安全"


def basic(username="reader", password=PASSWORD):
    return "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()


class AccessPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = hash_password(PASSWORD)

    def policy(self):
        return AccessPolicy("server", "https://papers.example.com", "reader", self.password_hash)

    def test_correct_wrong_and_unicode_credentials(self):
        policy = self.policy()
        self.assertTrue(policy.authenticate(basic()))
        self.assertFalse(policy.authenticate(basic(password="wrong-password")))
        self.assertFalse(policy.authenticate(basic(username="different")))
        self.assertTrue(policy.authenticate(basic()))

    def test_malformed_credentials_are_rejected(self):
        for value in ("", "Bearer secret", "Basic !!!", "Basic " + "A" * 5000, "Basic Zm9v", "Basic /w=="):
            self.assertFalse(self.policy().authenticate(value))

    def test_public_origin_is_exact(self):
        policy = self.policy()
        self.assertTrue(policy.allowed("papers.example.com", "https://papers.example.com"))
        self.assertFalse(policy.allowed("papers.example.com", "http://papers.example.com"))
        self.assertFalse(policy.allowed("papers.example.com.evil", None))
        self.assertFalse(policy.allowed("papers.example.com", "https://evil.example"))
        self.assertFalse(policy.allowed("user@papers.example.com", None))
        self.assertFalse(policy.allowed("papers.example.com:broken", None))

    def test_public_http_is_rejected_but_private_tunnel_is_supported(self):
        with self.assertRaises(ValueError):
            AccessPolicy("server", "http://papers.example.com", "reader", self.password_hash)
        policy = AccessPolicy("server", "http://localhost:8765", "reader", self.password_hash)
        self.assertTrue(policy.allowed("localhost:8765", "http://localhost:8765"))
        self.assertTrue(policy.authenticate(basic()))

    def test_server_mode_fails_closed_without_password_file(self):
        with patch.dict(os.environ, {"PAPER_TRANSLATE_MODE": "server", "PAPER_TRANSLATE_PASSWORD_HASH_FILE": ""}):
            with self.assertRaises(ValueError):
                AccessPolicy.from_environment()

    def test_bad_password_hash_is_rejected(self):
        for value in ("plaintext", "scrypt-v1$aa$bb", "scrypt-v2$" + "aa"*16 + "$" + "bb"*32):
            with self.assertRaises(ValueError):
                parse_hash(value)


class ServerAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        store = Store(Path(self.temp.name))
        settings = Settings(store.root)
        jobs = Jobs(store, settings)
        self.policy = AccessPolicy("server", "https://papers.example.com", "reader", hash_password(PASSWORD))
        self.patches = [patch.object(application, "access", self.policy), patch.object(application, "store", store),
                        patch.object(application, "settings", settings), patch.object(application, "jobs", jobs)]
        for item in self.patches:
            item.start()
        self.client = TestClient(application.app, base_url="https://papers.example.com")
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_pages_files_and_apis_all_require_login(self):
        paths = ["/", "/docs", "/openapi.json", "/favicon.svg", "/assets/example.js", "/api/settings",
                 "/api/documents/example/pdf", "/api/documents/example/assets/image.jpg", "/api/documents/example/export"]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertIn("Basic", response.headers["www-authenticate"])

    def test_invalid_password_and_foreign_origin_are_rejected(self):
        response = self.client.get("/api/settings", headers={"Authorization": basic(password="invalid")})
        self.assertEqual(response.status_code, 401)
        response = self.client.put("/api/settings", headers={"Authorization": basic(), "Origin": "https://evil.example"}, json={})
        self.assertEqual(response.status_code, 403)

    def test_authenticated_runtime_and_no_secret_leak(self):
        response = self.client.get("/api/health", headers={"Authorization": basic()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "server")
        response = self.client.get("/api/settings", headers={"Authorization": basic()})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("api_key", response.json())
        self.assertNotIn("password", response.text)
        self.assertEqual(response.headers["cache-control"], "private, no-store")

    def test_liveness_is_public_and_minimal(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"application": "paper-translate", "status": "ok"})


class PortableDataTests(unittest.TestCase):
    def test_database_paths_are_relative_and_survive_data_move(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = Store(root / "old")
            folder = original.root / "documents" / "paper-id"
            folder.mkdir(parents=True)
            (folder / "paper.pdf").write_bytes(b"pdf-fixture")
            (folder / "parsed").mkdir()
            original.put({"id": "paper-id", "pdf_path": str(folder / "paper.pdf"), "asset_root": str(folder / "parsed")})
            with original.connect() as con:
                raw = json.loads(con.execute("SELECT body FROM documents").fetchone()[0])
            self.assertEqual(raw["pdf_path"], "documents/paper-id/paper.pdf")
            shutil.copytree(original.root, root / "moved")
            moved = Store(root / "moved")
            self.assertEqual(Path(moved.get("paper-id")["pdf_path"]).read_bytes(), b"pdf-fixture")
            self.assertTrue(Path(moved.get("paper-id")["asset_root"]).is_relative_to(moved.root))

    def test_legacy_absolute_paths_relocate_even_when_old_copy_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "old")
            folder = store.root / "documents" / "legacy-id"
            folder.mkdir(parents=True)
            (folder / "paper.pdf").write_bytes(b"legacy")
            payload = {"id": "legacy-id", "pdf_path": str(folder / "paper.pdf"), "asset_root": str(folder)}
            with store.connect() as con:
                con.execute("INSERT INTO documents(id,body) VALUES(?,?)", ("legacy-id", json.dumps(payload)))
            shutil.copytree(store.root, root / "moved")
            moved = Store(root / "moved")
            self.assertEqual(Path(moved.get("legacy-id")["pdf_path"]), moved.root / "documents/legacy-id/paper.pdf")


if __name__ == "__main__":
    unittest.main()
