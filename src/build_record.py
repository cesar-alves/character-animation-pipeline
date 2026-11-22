"""Build-record helpers (standard library only).

Every successful character build writes a tracked ``builds/<name>.json`` file
containing provenance, tool version, exporter settings and the validation
summary. No ``bpy`` import is involved.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from typing import Any

pipeline_version = "0.1.0"
SCHEMA_VERSION = 1
CHUNK_SIZE = 1024 * 1024


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def write_build_record(path: str, data: dict) -> str:
    """Write a 2-space-indented build record and return the path."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    return path


def scan_vendor(vendor_dir: str) -> dict:
    """Map each vendored GLB stem to its ``sha256`` and ``size``."""
    if not os.path.isdir(vendor_dir):
        raise ValueError(f"vendor directory does not exist: {vendor_dir}")
    scanned: dict[str, dict[str, Any]] = {}
    for file_name in sorted(os.listdir(vendor_dir)):
        if not file_name.lower().endswith(".glb"):
            continue
        path = os.path.join(vendor_dir, file_name)
        if not os.path.isfile(path):
            continue
        stem = os.path.splitext(file_name)[0]
        scanned[stem] = {
            "file": file_name,
            "sha256": sha256_file(path),
            "size": os.path.getsize(path),
        }
    return scanned


def make_build_record(
    *,
    name: str,
    model: str,
    profile: str,
    clips: list[str],
    clip_paths: dict[str, str],
    vendor_dir: str,
    bone_count: int | None = None,
    fit: str | None = None,
    exporter_settings: dict | None = None,
    validation: dict | None = None,
    generated_at: str | None = None,
) -> dict:
    """Construct the tracked build record for one character."""
    if generated_at is None:
        generated_at = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    clip_hashes: dict[str, dict[str, Any]] = {}
    for clip in clips:
        path = clip_paths.get(clip)
        if not path or not os.path.isfile(path):
            raise ValueError(f"cannot record missing clip {clip!r}")
        clip_hashes[clip] = {
            "path": os.path.abspath(path),
            "sha256": sha256_file(path),
            "size": os.path.getsize(path),
        }
    fit_record = None
    if fit:
        if not os.path.isfile(fit):
            raise ValueError(f"cannot record missing fit config {fit!r}")
        fit_record = {"path": os.path.abspath(fit), "sha256": sha256_file(fit)}
    if not os.path.isfile(model):
        raise ValueError(f"cannot record missing model {model!r}")
    report = validation or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": pipeline_version,
        "name": name,
        "generated_at": generated_at,
        "model": {
            "path": os.path.abspath(model),
            "sha256": sha256_file(model),
        },
        "profile": profile,
        "clips_requested": list(clips),
        "clips": clip_hashes,
        "fit": fit_record,
        "bone_count": bone_count,
        "exporter_settings": dict(exporter_settings or {}),
        "validation_summary": {
            "ok": bool(report.get("ok", False)),
            "checks": report.get("checks", []),
            "clips": report.get("clips", []),
            "bones": len(report.get("bones", [])),
            "errors": report.get("errors", []),
        },
        "vendor": {
            "dir": os.path.abspath(vendor_dir),
            "files": scan_vendor(vendor_dir),
        },
    }
