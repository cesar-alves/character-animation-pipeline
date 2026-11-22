"""Tests for src.build_record using temporary files only."""
import hashlib
import json
import os
import tempfile
import unittest

from src import build_record


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class BuildRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.tmp.name
        self.vendor = os.path.join(self.base, "vendor")
        os.makedirs(self.vendor, exist_ok=True)
        self.model = os.path.join(self.base, "hero.glb")
        with open(self.model, "wb") as handle:
            handle.write(b"model bytes")
        self.clips = {}
        for name in ("walk", "idle-a"):
            path = os.path.join(self.vendor, name + ".glb")
            with open(path, "wb") as handle:
                handle.write(name.encode())
            self.clips[name] = path

    def test_scan_vendor_hashes(self):
        with open(os.path.join(self.vendor, "notes.txt"), "w", encoding="utf-8") as handle:
            handle.write("not a clip")
        scanned = build_record.scan_vendor(self.vendor)
        self.assertEqual(set(scanned), {"walk", "idle-a"})
        self.assertEqual(scanned["walk"]["sha256"], sha256(b"walk"))
        self.assertEqual(scanned["idle-a"]["size"], len(b"idle-a"))
        self.assertEqual(scanned["walk"]["file"], "walk.glb")

    def test_record_round_trip(self):
        path = os.path.join(self.base, "builds", "hero.json")
        record = build_record.make_build_record(
            name="hero",
            model=self.model,
            profile="m2m-human",
            clips=["walk", "idle-a"],
            clip_paths=self.clips,
            vendor_dir=self.vendor,
            bone_count=66,
            validation={"ok": True, "checks": [], "bones": ["root"], "clips": ["walk"], "errors": []},
        )
        build_record.write_build_record(path, record)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        loaded = json.loads(text)
        self.assertEqual(loaded, record)
        self.assertIn('\n  "name": "hero"', text)
        self.assertEqual(loaded["schema_version"], 1)
        self.assertEqual(loaded["pipeline_version"], "0.1.0")
        self.assertEqual(loaded["model"]["sha256"], sha256(b"model bytes"))
        self.assertEqual(loaded["clips"]["walk"]["sha256"], sha256(b"walk"))
        self.assertEqual(loaded["clips_requested"], ["walk", "idle-a"])
        self.assertEqual(loaded["bone_count"], 66)
        self.assertTrue(loaded["validation_summary"]["ok"])
        self.assertIn("generated_at", loaded)

    def test_fit_hash_recorded(self):
        fit = os.path.join(self.base, "fit.json")
        with open(fit, "w", encoding="utf-8") as handle:
            json.dump({"bones": {}}, handle)
        record = build_record.make_build_record(
            name="hero",
            model=self.model,
            profile="m2m-human",
            clips=[],
            clip_paths={},
            vendor_dir=self.vendor,
            fit=fit,
        )
        self.assertEqual(record["fit"]["sha256"], sha256(json.dumps({"bones": {}}).encode()))


if __name__ == "__main__":
    unittest.main()
