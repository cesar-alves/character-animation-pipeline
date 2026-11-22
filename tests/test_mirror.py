"""Tests for src.mirror using only temporary directories."""
import hashlib
import json
import os
import tempfile
import unittest

from src import mirror


def _sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = os.path.join(self.tmp.name, "hero.glb")
        with open(self.source, "wb") as handle:
            handle.write(b"GLB test bytes\x00\x01")
        self.files = [(self.source, "models/hero.glb")]
        self.expected_hash = _sha256(self.source)

    def test_mirror_writes_manifest_and_checksums(self):
        root = os.path.join(self.tmp.name, "drive")
        result = mirror.mirror_files(self.files, root, "2026-11-22", "hero")
        self.assertFalse(result["skipped"])
        expected_dir = os.path.join(root, "generated", "characters", "hero", "2026-11-22")
        self.assertEqual(result["dir"], expected_dir)
        self.assertTrue(os.path.isfile(os.path.join(expected_dir, "models", "hero.glb")))
        self.assertEqual(result["files"]["models/hero.glb"], self.expected_hash)

        with open(os.path.join(expected_dir, "manifest.json"), encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["name"], "hero")
        self.assertEqual(manifest["date"], "2026-11-22")
        self.assertIn("generated_at", manifest)
        self.assertEqual(manifest["files"][0]["sha256"], self.expected_hash)
        self.assertEqual(manifest["files"][0]["path"], "models/hero.glb")
        self.assertEqual(manifest["files"][0]["size"], os.path.getsize(self.source))

        with open(os.path.join(expected_dir, "CHECKSUMS.sha256"), encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertIn(f"{self.expected_hash}  models/hero.glb", lines)

    def test_nonempty_dated_folder_refuses_without_force(self):
        root = os.path.join(self.tmp.name, "drive")
        dated = os.path.join(root, "generated", "characters", "hero", "2026-11-22")
        os.makedirs(dated)
        with open(os.path.join(dated, "sentinel.txt"), "w", encoding="utf-8") as handle:
            handle.write("keep me")
        with self.assertRaises(ValueError):
            mirror.mirror_files(self.files, root, "2026-11-22", "hero")
        self.assertTrue(os.path.isfile(os.path.join(dated, "sentinel.txt")))

        result = mirror.mirror_files(self.files, root, "2026-11-22", "hero", force=True)
        self.assertEqual(result["dir"], dated)
        self.assertEqual(result["files"]["models/hero.glb"], self.expected_hash)

    def test_copy_to_godot_writes_expected_path(self):
        project = os.path.join(self.tmp.name, "godot-project")
        result = mirror.copy_to_godot(self.files, project, "hero")
        expected = os.path.join(project, "assets", "vendor", "characters", "hero")
        self.assertEqual(result["dir"], expected)
        copied = os.path.join(expected, "models", "hero.glb")
        self.assertTrue(os.path.isfile(copied))
        self.assertEqual(_sha256(copied), self.expected_hash)
        readme = os.path.join(expected, "README.md")
        self.assertTrue(os.path.isfile(readme))
        with open(readme, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("CC0", text)
        self.assertIn("gitignored", text)

    def test_custom_subdir(self):
        project = os.path.join(self.tmp.name, "godot-project")
        result = mirror.copy_to_godot(self.files, project, "hero", subdir="custom/addons")
        self.assertEqual(
            result["dir"], os.path.join(project, "custom", "addons", "hero")
        )

    def test_skip_without_drive_root(self):
        result = mirror.mirror_files(self.files, None, "2026-11-22", "hero")
        self.assertTrue(result["skipped"])
        self.assertIsNone(result["dir"])
        self.assertEqual(result["files"], {})

    def test_require_drive_without_root_raises(self):
        with self.assertRaises(ValueError):
            mirror.mirror_files(self.files, None, "2026-11-22", "hero", require=True)

    def test_bad_date_rejected(self):
        root = os.path.join(self.tmp.name, "drive")
        with self.assertRaises(ValueError):
            mirror.mirror_files(self.files, root, "22-11-2026", "hero")


if __name__ == "__main__":
    unittest.main()
