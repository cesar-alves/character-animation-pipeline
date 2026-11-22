"""Tests for src.job using temporary files only."""
import json
import os
import tempfile
import unittest

from src import job as job_module


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    return path


class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.tmp.name
        self.vendor = os.path.join(self.base, "vendor")
        self.out = os.path.join(self.base, "out")
        self.fit_dir = os.path.join(self.base, "config", "fit")
        for directory in (self.vendor, self.out, self.fit_dir):
            os.makedirs(directory, exist_ok=True)
        self.model = os.path.join(self.base, "models", "hero.glb")
        os.makedirs(os.path.dirname(self.model), exist_ok=True)
        with open(self.model, "wb") as handle:
            handle.write(b"GLB")
        for clip in ("walk", "idle-a"):
            with open(os.path.join(self.vendor, clip + ".glb"), "wb") as handle:
                handle.write(clip.encode())
        self.fit = os.path.join(self.fit_dir, "hero.json")
        write_json(self.fit, {"schema_version": 1, "bones": {}})

    def jobs_data(self):
        return {
            "schema_version": 1,
            "characters": [
                {
                    "name": "hero",
                    "model": "models/hero.glb",
                    "clips": ["idle-a.glb", "walk", "idle-a"],
                    "profile": "m2m-human",
                    "fit": "hero.json",
                }
            ],
        }

    def test_valid_jobs_load_and_normalize(self):
        path = write_json(os.path.join(self.base, "jobs.json"), self.jobs_data())
        jobs = job_module.load_jobs(path)
        self.assertEqual(jobs["schema_version"], 1)
        character = jobs["characters"][0]
        self.assertEqual(character["name"], "hero")
        self.assertEqual(character["clips"], ["idle-a", "walk"])
        self.assertEqual(character["profile"], "m2m-human")
        self.assertEqual(character["fit"], "hero.json")

    def test_duplicate_names_rejected(self):
        data = self.jobs_data()
        data["characters"].append(dict(data["characters"][0]))
        path = write_json(os.path.join(self.base, "jobs-dup.json"), data)
        with self.assertRaises(ValueError) as caught:
            job_module.load_jobs(path)
        self.assertIn("duplicate character name", str(caught.exception))

    def test_missing_clip_file_detected(self):
        jobs = job_module.load_jobs(write_json(os.path.join(self.base, "jobs.json"), self.jobs_data()))
        character = dict(jobs["characters"][0], clips=["walk", "run-anime"])
        with self.assertRaises(ValueError) as caught:
            job_module.resolve_character(
                character, self.base, self.vendor, self.out, self.fit_dir
            )
        self.assertIn("run-anime", str(caught.exception))

    def test_resolve_character_returns_absolute_paths(self):
        jobs = job_module.load_jobs(write_json(os.path.join(self.base, "jobs.json"), self.jobs_data()))
        resolved = job_module.resolve_character(
            jobs["characters"][0], self.base, self.vendor, self.out, self.fit_dir
        )
        self.assertEqual(resolved["model"], os.path.abspath(self.model))
        self.assertEqual(resolved["fit"], os.path.abspath(self.fit))
        self.assertEqual(
            resolved["clip_paths"]["walk"], os.path.join(self.vendor, "walk.glb")
        )
        for path in [resolved["model"], resolved["fit"], *resolved["clip_paths"].values()]:
            self.assertTrue(os.path.isabs(path))
            self.assertTrue(os.path.isfile(path))
        self.assertEqual(resolved["out_glb"], os.path.join(self.out, "hero.glb"))

    def test_unknown_fields_and_bad_schema_rejected(self):
        data = self.jobs_data()
        data["oops"] = 1
        path = write_json(os.path.join(self.base, "jobs-unknown.json"), data)
        with self.assertRaises(ValueError):
            job_module.load_jobs(path)
        data.pop("oops")
        data["schema_version"] = 2
        path = write_json(os.path.join(self.base, "jobs-schema.json"), data)
        with self.assertRaises(ValueError):
            job_module.load_jobs(path)

    def test_write_tmp_job_contract(self):
        jobs = job_module.load_jobs(write_json(os.path.join(self.base, "jobs.json"), self.jobs_data()))
        resolved = job_module.resolve_character(
            jobs["characters"][0], self.base, self.vendor, self.out, self.fit_dir
        )
        path = job_module.write_tmp_job(resolved, os.path.join(self.base, "work", "hero.json"))
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertEqual(set(payload), {"name", "model", "clips", "profile", "fit"})
        self.assertTrue(os.path.isabs(payload["model"]))
        self.assertEqual(payload["clips"], ["idle-a", "walk"])


if __name__ == "__main__":
    unittest.main()
