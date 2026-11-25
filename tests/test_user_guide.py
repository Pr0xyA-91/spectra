"""Tests for the built-in illustrated SPECTRA User Guide (EN + CS) and static MIME serving."""

import http.client
import os
import pathlib
import re
import threading
import unittest
from http.server import ThreadingHTTPServer

import spectra_web.handler as sw_handler

ROOT = pathlib.Path(__file__).resolve().parent.parent
GUIDE_PUBLIC = ROOT / "web" / "public" / "guide"
GUIDE_DIST = ROOT / "web" / "dist" / "guide"


class TestBuiltInUserGuide(unittest.TestCase):
    def test_public_and_dist_guides_exist_with_all_assets(self):
        for base in (GUIDE_PUBLIC, GUIDE_DIST):
            for lang in ("en", "cs"):
                md_path = base / f"{lang}.md"
                self.assertTrue(md_path.is_file(), f"Missing baked guide: {md_path}")
                text = md_path.read_text(encoding="utf-8")
                self.assertGreater(len(text), 4000, f"Guide too short: {md_path}")

                # Must have 11 numbered chapters
                chapters = re.findall(r"^##\s+\d+\.\s+", text, flags=re.MULTILINE)
                self.assertEqual(len(chapters), 11, f"Expected 11 chapters in {md_path}, got {len(chapters)}")

                # Every embedded image must exist cleanly on disk
                imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
                self.assertGreaterEqual(len(imgs), 20, f"Expected >=20 embedded UI screenshots in {md_path}")
                for rel_img in imgs:
                    img_file = base / rel_img
                    self.assertTrue(img_file.is_file(), f"Broken guide image ref {rel_img} in {md_path}")
                    self.assertGreater(img_file.stat().st_size, 5000, f"Suspiciously small image: {img_file}")

                # Zero leaked secrets or private workstation paths
                self.assertIsNone(re.search(r"gh[pousr]_[A-Za-z0-9_]{2,}", text))
                self.assertIsNone(re.search(r"/home/[a-zA-Z0-9_-]+", text))
                self.assertNotIn("spectra" + "_" + "dev", text)

    def test_internal_markdown_guides_links_resolve(self):
        internal_dir = ROOT / "docs" / "internal"
        if not internal_dir.is_dir():
            self.skipTest("Private docs/internal directory is omitted in public builds")
        for fname in ("USER_GUIDE_EN.md", "PRIRUCKA_UZIVATELE_CS.md"):
            doc = internal_dir / fname
            self.assertTrue(doc.is_file(), f"Missing internal doc: {doc}")
            text = doc.read_text(encoding="utf-8")
            imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
            self.assertGreaterEqual(len(imgs), 20)
            for rel_img in imgs:
                resolved = (doc.parent / rel_img).resolve()
                self.assertTrue(resolved.is_file(), f"Broken relative image {rel_img} in {doc}")

    def test_help_button_and_modal_wired_in_frontend(self):
        header_src = (ROOT / "web" / "src" / "components" / "workspace" / "WorkspaceHeader.jsx").read_text(encoding="utf-8")
        workspace_src = (ROOT / "web" / "src" / "components" / "SpectraWorkspace.jsx").read_text(encoding="utf-8")
        self.assertIn("onOpenUserGuide", header_src)
        self.assertIn("t('btnHelp')", header_src)
        self.assertIn("UserGuideModal", workspace_src)
        self.assertIn("setShowUserGuideModal(true)", workspace_src)

    def test_static_server_serves_guide_md_and_webp_with_explicit_mimes(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), sw_handler.SpectraApiHandler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/guide/en.md")
            r1 = conn.getresponse()
            body1 = r1.read()
            self.assertEqual(r1.status, 200)
            self.assertIn("text/markdown", r1.getheader("Content-Type", ""))
            self.assertIn(b"SPECTRA User Guide", body1)

            conn.request("GET", "/guide/cs.md")
            r2 = conn.getresponse()
            body2 = r2.read()
            self.assertEqual(r2.status, 200)
            self.assertIn("text/markdown", r2.getheader("Content-Type", ""))
            self.assertIn("Uživatelská příručka SPECTRA".encode("utf-8"), body2)

            conn.request("GET", "/guide/images_en/01_overview.webp")
            r3 = conn.getresponse()
            body3 = r3.read()
            self.assertEqual(r3.status, 200)
            self.assertEqual(r3.getheader("Content-Type"), "image/webp")
            self.assertTrue(body3.startswith(b"RIFF") and body3[8:12] == b"WEBP")
            conn.close()
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
