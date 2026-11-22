"""GLB validator for the character animation pipeline.

Uses only the Python standard library. The GLB container is parsed directly
(12-byte header followed by length/type-prefixed chunks) so no ``bpy`` or
third-party glTF library is needed.

Run from the repository root::

    python3 -m src.validate models/hero.glb --clips idle,walk \
        --profile profiles/polygon_humanoid.json --report reports/hero.json
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from typing import Any

GLB_MAGIC = 0x46546C67  # b"glTF"
GLB_VERSION = 2
JSON_CHUNK = 0x4E4F534A  # b"JSON"
BIN_CHUNK = 0x004E4942  # b"BIN\0"

_COMPONENT = {
    5120: ("b", 1),  # BYTE
    5121: ("B", 1),  # UNSIGNED_BYTE
    5122: ("h", 2),  # SHORT
    5123: ("H", 2),  # UNSIGNED_SHORT
    5125: ("I", 4),  # UNSIGNED_INT
    5126: ("f", 4),  # FLOAT
}
_TYPE_COUNTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}
_ROOT_BONE_NAMES = {"Root", "pelvis", "Hips"}


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _parse_glb(path: str) -> tuple[dict, bytes]:
    """Return ``(gltf_json_dict, bin_chunk_bytes)`` from a binary glTF file."""
    with open(path, "rb") as handle:
        data = handle.read()
    if len(data) < 20:
        raise ValueError("file is too short to be a GLB")
    magic, version, total = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC:
        raise ValueError("missing glTF magic header")
    if version != GLB_VERSION:
        raise ValueError(f"unsupported glTF version {version} (expected 2)")
    if total != len(data):
        raise ValueError(f"declared length {total} does not match file size {len(data)}")

    offset = 12
    gltf: dict | None = None
    binary = b""
    while offset + 8 <= len(data):
        length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        if offset + length > len(data):
            raise ValueError("chunk length exceeds file size")
        chunk = data[offset : offset + length]
        offset += length
        if chunk_type == JSON_CHUNK:
            gltf = json.loads(chunk.decode("utf-8").rstrip(" \x00"))
        elif chunk_type == BIN_CHUNK:
            binary = chunk
    if gltf is None:
        raise ValueError("GLB contains no JSON chunk")
    return gltf, binary


def _read_accessor(gltf: dict, binary: bytes, index: int) -> list:
    """Decode a glTF accessor from the BIN chunk into a list of values."""
    accessors = gltf.get("accessors", [])
    if index is None or not isinstance(index, int) or index >= len(accessors):
        raise ValueError(f"invalid accessor index {index!r}")
    accessor = accessors[index]
    fmt_char, component_size = _COMPONENT[accessor.get("componentType", 5126)]
    n_components = _TYPE_COUNTS[accessor.get("type", "VEC3")]
    count = int(accessor.get("count", 0))
    view_index = accessor.get("bufferView")
    views = gltf.get("bufferViews", [])
    if view_index is None or view_index >= len(views):
        raise ValueError(f"accessor {index} has no valid bufferView")
    view = views[view_index]
    base = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride") or (component_size * n_components)
    width = component_size * n_components
    values = []
    for i in range(count):
        start = base + i * stride
        raw = binary[start : start + width]
        if len(raw) < width:
            raise ValueError(f"accessor {index} sample {i} is truncated")
        unpacked = struct.unpack("<" + fmt_char * n_components, raw)
        values.append(unpacked[0] if n_components == 1 else unpacked)
    return values


def _joint_names(gltf: dict) -> list[str]:
    nodes = gltf.get("nodes", [])
    names: list[str] = []
    for skin in gltf.get("skins", []):
        for node_index in skin.get("joints", []):
            if 0 <= node_index < len(nodes):
                name = nodes[node_index].get("name") or f"node_{node_index}"
                if name not in names:
                    names.append(name)
    return names


def _skinned_mesh_count(gltf: dict) -> int:
    count = 0
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            attributes = primitive.get("attributes", {})
            if "JOINTS_0" in attributes and "WEIGHTS_0" in attributes:
                count += 1
                break
    return count


def _camera_light_detail(gltf: dict) -> str:
    problems = []
    if gltf.get("cameras"):
        problems.append(f"{len(gltf['cameras'])} camera(s)")
    if any("camera" in node for node in gltf.get("nodes", [])):
        problems.append("camera referenced by a node")
    if "KHR_lights_punctual" in gltf.get("extensions", {}):
        problems.append("KHR_lights_punctual extension")
    for node in gltf.get("nodes", []):
        if "KHR_lights_punctual" in node.get("extensions", {}):
            problems.append("KHR_lights_punctual on a node")
    return ", ".join(problems)


def _close(a, b) -> bool:
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(abs(x - y) <= 1e-6 for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-6
    return a == b


def _root_translation_check(gltf: dict, binary: bytes, root_names: set[str]) -> dict:
    problems = []
    inspected = 0
    nodes = gltf.get("nodes", [])
    for animation in gltf.get("animations", []):
        samplers = animation.get("samplers", [])
        anim_name = animation.get("name", "<unnamed>")
        for channel in animation.get("channels", []):
            target = channel.get("target", {})
            if target.get("path") != "translation":
                continue
            node_index = target.get("node")
            name = ""
            if isinstance(node_index, int) and 0 <= node_index < len(nodes):
                name = nodes[node_index].get("name", "")
            if name not in root_names:
                continue
            inspected += 1
            sampler_index = channel.get("sampler")
            try:
                if sampler_index is None or sampler_index >= len(samplers):
                    raise ValueError("channel has no valid sampler")
                output = samplers[sampler_index].get("output")
                translations = _read_accessor(gltf, binary, output)
                if not translations:
                    raise ValueError("translation accessor is empty")
                first = translations[0]
                if any(not _close(value, first) for value in translations[1:]):
                    problems.append(f"{anim_name}:{name} has varying translation")
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                problems.append(f"{anim_name}:{name} could not be read ({exc})")
    if not inspected:
        return _check("root_translation_constant", True, "no Root/pelvis translation channel")
    if problems:
        return _check("root_translation_constant", False, "; ".join(problems))
    return _check("root_translation_constant", True, f"{inspected} root translation channel(s) constant")


def _profile_check(bones: list[str], profile: dict) -> dict:
    """Compare joint names against an opt-in bone profile.

    Map keys are Mesh2Motion source names (what the exported GLB is expected to
    carry), values are frozen Godot rig names. ``synthesize`` entries are Godot
    bones added in-engine, so they are allowed but not required in the GLB.
    """
    bone_map = profile.get("map", {}) or {}
    synth_names = {
        entry.get("name")
        for entry in profile.get("synthesize", [])
        if isinstance(entry, dict) and entry.get("name")
    }
    expected = set(bone_map.keys()) | synth_names
    unknown = [name for name in bones if name not in expected]
    missing = [name for name in bone_map if name not in bones]
    problems = []
    if unknown:
        problems.append("unknown bone(s): " + ", ".join(unknown))
    if missing:
        problems.append("missing source bone(s): " + ", ".join(missing))
    if problems:
        return _check("profile_bones", False, "; ".join(problems))
    return _check("profile_bones", True, f"{len(bones)} bone(s) match {profile.get('name', 'profile')}")


def validate_glb(
    path: str,
    expected_clips: list[str] | None = None,
    profile: dict | None = None,
) -> dict:
    """Validate a Godot-ready GLB and return a JSON-serialisable report."""
    report: dict[str, Any] = {
        "ok": False,
        "checks": [],
        "bones": [],
        "clips": [],
        "errors": [],
    }
    try:
        gltf, binary = _parse_glb(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        message = f"cannot parse GLB {path!r}: {exc}"
        report["errors"].append(message)
        report["checks"].append(_check("glb_parse", False, message))
        return report

    checks = report["checks"]
    skins = gltf.get("skins", [])
    checks.append(
        _check("single_skin", len(skins) == 1, f"found {len(skins)} skin(s)")
    )

    skinned = _skinned_mesh_count(gltf)
    checks.append(
        _check("skinned_mesh", skinned > 0, f"{skinned} skinned mesh primitive(s)")
    )

    bones = _joint_names(gltf)
    report["bones"] = bones
    checks.append(_check("bones_present", len(bones) > 0, f"{len(bones)} bone(s)"))

    camera_detail = _camera_light_detail(gltf)
    checks.append(
        _check("no_cameras_lights", not camera_detail, camera_detail or "none found")
    )

    clips = [animation.get("name", "") for animation in gltf.get("animations", [])]
    report["clips"] = clips
    requested = list(expected_clips or [])
    missing_clips = [clip for clip in requested if clip not in clips]
    if requested:
        checks.append(
            _check(
                "clips_present",
                not missing_clips,
                "missing clip(s): " + ", ".join(missing_clips)
                if missing_clips
                else f"{len(requested)} requested clip(s) present",
            )
        )
    else:
        checks.append(_check("clips_present", True, "no clips requested"))

    if profile is not None:
        checks.append(_profile_check(bones, profile))
    else:
        checks.append(_check("profile_bones", True, "no profile requested"))

    root_names = set(_ROOT_BONE_NAMES)
    if profile is not None:
        root_names.update(
            value
            for key, value in (profile.get("map", {}) or {}).items()
            if key == "pelvis" and isinstance(value, str) and value != "DROP"
        )
    checks.append(_root_translation_check(gltf, binary, root_names))

    report["errors"] = [check["detail"] for check in checks if not check["ok"]]
    report["ok"] = all(check["ok"] for check in checks)
    return report


def write_report(report: dict, path: str) -> str:
    """Write a validation report as 2-space-indented JSON; return the path."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Godot-ready character GLB")
    parser.add_argument("glb", help="path to the .glb file")
    parser.add_argument("--clips", default="", help="comma-separated required animation names")
    parser.add_argument("--profile", help="path to a bone profile JSON (opt-in)")
    parser.add_argument("--report", help="write the full JSON report to this path")
    args = parser.parse_args(argv)

    expected = [clip.strip() for clip in args.clips.split(",") if clip.strip()] or None
    profile = None
    if args.profile:
        with open(args.profile, encoding="utf-8") as handle:
            profile = json.load(handle)

    report = validate_glb(args.glb, expected, profile)
    if args.report:
        write_report(report, args.report)
    print("VALIDATE_OK" if report["ok"] else "VALIDATE_FAILED")
    for error in report["errors"]:
        print(f"  - {error}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
