"""Tests for src.validate using a hand-built GLB fixture (no external asset)."""
import json
import os
import struct
import tempfile
import unittest

from src import validate


def _pad(data: bytes, fill: bytes = b"\x00") -> bytes:
    return data + fill * ((4 - len(data) % 4) % 4)


def build_glb(
    path,
    *,
    clips=("idle",),
    camera=False,
    light=False,
    translations=None,
    with_skin=True,
    skinned_mesh=True,
    bone_names=("pelvis", "spine_01"),
):
    """Write a minimal but well-formed GLB with one skin, mesh and clip."""
    binary = bytearray()
    views = []
    accessors = []
    animations = []

    for clip_index, name in enumerate(clips):
        times = struct.pack("<2f", 0.0, 1.0)
        time_offset = len(binary)
        binary += times
        views.append({"buffer": 0, "byteOffset": time_offset, "byteLength": len(times)})
        time_accessor = len(accessors)
        accessors.append(
            {"bufferView": len(views) - 1, "componentType": 5126, "count": 2, "type": "SCALAR"}
        )

        samples = translations[clip_index] if translations else ((0.0, 0.0, 0.0),) * 2
        translation_data = struct.pack("<6f", *(samples[0] + samples[1]))
        translation_offset = len(binary)
        binary += translation_data
        views.append(
            {"buffer": 0, "byteOffset": translation_offset, "byteLength": len(translation_data)}
        )
        translation_accessor = len(accessors)
        accessors.append(
            {"bufferView": len(views) - 1, "componentType": 5126, "count": 2, "type": "VEC3"}
        )

        animations.append(
            {
                "name": name,
                "samplers": [
                    {
                        "input": time_accessor,
                        "output": translation_accessor,
                        "interpolation": "LINEAR",
                    }
                ],
                "channels": [{"sampler": 0, "target": {"node": 0, "path": "translation"}}],
            }
        )

    nodes = []
    for index, bone in enumerate(bone_names):
        node = {"name": bone}
        if index + 1 < len(bone_names):
            node["children"] = [index + 1]
        nodes.append(node)
    mesh_node = {"name": "CharacterMesh", "mesh": 0}
    if with_skin:
        mesh_node["skin"] = 0
    if camera:
        mesh_node["camera"] = 0
    nodes.append(mesh_node)

    attributes = {"POSITION": 0}
    if skinned_mesh:
        attributes.update({"JOINTS_0": 1, "WEIGHTS_0": 2})

    gltf = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": [{"primitives": [{"attributes": attributes}]}],
        "animations": animations,
        "bufferViews": views,
        "accessors": accessors,
        "buffers": [{"byteLength": len(binary)}],
    }
    if with_skin:
        gltf["skins"] = [{"joints": list(range(len(bone_names)))}]
    if camera:
        gltf["cameras"] = [{"type": "perspective", "perspective": {"yfov": 0.7, "zfar": 100}}]
    if light:
        gltf["extensions"] = {"KHR_lights_punctual": {"lights": [{"type": "directional"}]}}

    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_chunk = _pad(json_bytes, b" ")
    bin_chunk = _pad(bytes(binary))
    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    header = struct.pack("<III", 0x46546C67, 2, total)
    json_header = struct.pack("<II", len(json_chunk), 0x4E4F534A)
    bin_header = struct.pack("<II", len(bin_chunk), 0x004E4942)
    with open(path, "wb") as handle:
        handle.write(header + json_header + json_chunk + bin_header + bin_chunk)
    return path


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.glb = os.path.join(self.tmp.name, "hero.glb")

    def test_valid_fixture_passes(self):
        build_glb(self.glb)
        report = validate.validate_glb(self.glb)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["bones"], ["pelvis", "spine_01"])
        self.assertEqual(report["clips"], ["idle"])
        self.assertTrue(all(check["ok"] for check in report["checks"]))

    def test_missing_clip_fails(self):
        build_glb(self.glb, clips=("idle",))
        report = validate.validate_glb(self.glb, expected_clips=["idle", "walk"])
        self.assertFalse(report["ok"])
        clips_check = next(c for c in report["checks"] if c["name"] == "clips_present")
        self.assertFalse(clips_check["ok"])
        self.assertIn("walk", clips_check["detail"])

    def test_camera_in_file_fails(self):
        build_glb(self.glb, camera=True)
        report = validate.validate_glb(self.glb)
        self.assertFalse(report["ok"])
        camera_check = next(c for c in report["checks"] if c["name"] == "no_cameras_lights")
        self.assertFalse(camera_check["ok"])

    def test_light_extension_fails(self):
        build_glb(self.glb, light=True)
        report = validate.validate_glb(self.glb)
        self.assertFalse(report["ok"])

    def test_missing_skin_fails(self):
        build_glb(self.glb, with_skin=False)
        report = validate.validate_glb(self.glb)
        self.assertFalse(report["ok"])
        self.assertFalse(report["bones"])

    def test_root_translation_must_be_constant(self):
        build_glb(self.glb, translations=(((0, 0, 0), (1, 2, 3)),))
        report = validate.validate_glb(self.glb)
        self.assertFalse(report["ok"])
        translation_check = next(
            c for c in report["checks"] if c["name"] == "root_translation_constant"
        )
        self.assertFalse(translation_check["ok"])

    def test_profile_bone_match(self):
        build_glb(self.glb)
        profile = {"name": "test", "map": {"pelvis": "Hips", "spine_01": "Spine_01"},
                   "synthesize": [{"name": "Root"}]}
        report = validate.validate_glb(self.glb, profile=profile)
        self.assertTrue(report["ok"], report["errors"])

        bad_profile = {"name": "bad", "map": {"hips": "Hips"}}
        report = validate.validate_glb(self.glb, profile=bad_profile)
        self.assertFalse(report["ok"])

    def test_write_report_uses_two_space_indent(self):
        build_glb(self.glb)
        report = validate.validate_glb(self.glb)
        out = os.path.join(self.tmp.name, "reports", "hero.json")
        validate.write_report(report, out)
        with open(out, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn('\n  "ok": true', text)
        self.assertEqual(json.loads(text), report)

    def test_malformed_glb_returns_error_report(self):
        with open(self.glb, "wb") as handle:
            handle.write(b"not a glb at all")
        report = validate.validate_glb(self.glb)
        self.assertFalse(report["ok"])
        self.assertTrue(report["errors"])


if __name__ == "__main__":
    unittest.main()
