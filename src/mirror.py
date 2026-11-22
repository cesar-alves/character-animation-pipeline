"""Dated Drive mirror and Godot drop-in copy for generated character GLBs.

Standard library only; this module never imports ``bpy``. Nothing is written
outside paths the caller explicitly supplies (or the ``CHARACTER_PIPELINE_DRIVE_ROOT``
environment variable).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import shutil
import sys
from typing import Iterable

DRIVE_ROOT_ENV = "CHARACTER_PIPELINE_DRIVE_ROOT"
SCHEMA_VERSION = 1

_GODOT_README = """# Vendored character assets

These GLB files are **CC0-derived build artifacts** produced by the
character-animation-pipeline. Do not hand-edit them: regenerate the build and
re-run the dated Drive mirror instead.

This folder (`assets/vendor/characters/`) is **gitignored by the Godot project**.
The files are local drop-ins and are not committed to the project repository.
Reapply the `polygon_humanoid` bone map when importing them.
"""


def _date_string(date) -> str:
    if hasattr(date, "strftime"):
        return date.strftime("%Y-%m-%d")
    text = str(date)
    try:
        _dt.date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"date must be YYYY-MM-DD, got {text!r}") from exc
    return text


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _iter_files(files: Iterable) -> Iterable[tuple[str, str]]:
    for item in files:
        if isinstance(item, (tuple, list)):
            if len(item) != 2:
                raise ValueError(f"file entry must be (source, relative_dest), got {item!r}")
            source, relative = item
        else:
            source, relative = item, os.path.basename(item)
        relative = str(relative).replace("\\", "/").lstrip("/")
        if not relative or relative.startswith("../"):
            raise ValueError(f"unsafe relative destination {relative!r}")
        yield str(source), relative


def _join_root(root: str, *parts: str) -> str:
    return os.path.join(root, *[part for part in parts if part])


def mirror_files(
    files: list[tuple[str, str]],
    root: str,
    date: str,
    name: str,
    require: bool = False,
    force: bool = False,
) -> dict:
    """Copy build artifacts into an immutable, dated Drive folder.

    The layout is ``root/generated/characters/<name>/<YYYY-MM-DD>/``. A
    ``manifest.json`` and a ``CHECKSUMS.sha256`` file are written alongside the
    copied artifacts. A non-empty existing dated folder is refused unless
    ``force`` is true.

    With no ``root`` and ``require=False`` the call is a no-op and returns a
    result with ``skipped=True``. With ``require=True`` a missing root raises
    ``ValueError``.
    """
    result: dict = {
        "ok": True,
        "skipped": False,
        "dir": None,
        "files": {},
        "manifest": None,
        "checksums": None,
    }
    if not root:
        if require:
            raise ValueError(f"no Drive root (set {DRIVE_ROOT_ENV} or pass --drive-root)")
        result.update(reason="no drive root")
        result["skipped"] = True
        return result

    date_text = _date_string(date)
    output_dir = _join_root(root, "generated", "characters", name, date_text)
    if os.path.isdir(output_dir) and os.listdir(output_dir) and not force:
        raise ValueError(
            f"refusing to write into non-empty dated folder: {output_dir} "
            "(pass force=True to overwrite)"
        )
    os.makedirs(output_dir, exist_ok=True)

    manifest_files = []
    for source, relative in _iter_files(files):
        destination = _join_root(output_dir, *relative.split("/"))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copyfile(source, destination)
        digest = _sha256(destination)
        size = os.path.getsize(destination)
        result["files"][relative] = digest
        manifest_files.append({"path": relative, "size": size, "sha256": digest})

    now = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "date": date_text,
        "generated_at": now,
        "files": manifest_files,
    }
    manifest_path = _join_root(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")

    checksum_lines = [f"{entry['sha256']}  {entry['path']}" for entry in manifest_files]
    checksum_lines.append(f"{_sha256(manifest_path)}  manifest.json")
    checksums_path = _join_root(output_dir, "CHECKSUMS.sha256")
    with open(checksums_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(checksum_lines) + "\n")

    result.update(
        dir=output_dir,
        manifest=manifest_path,
        checksums=checksums_path,
        manifest_data=manifest,
    )
    return result


def copy_to_godot(
    files: list[tuple[str, str]],
    godot_project: str,
    character_name: str,
    subdir: str = "assets/vendor/characters",
) -> dict:
    """Drop the same GLBs into an explicitly named Godot project."""
    parts = [part for part in subdir.replace("\\", "/").split("/") if part]
    target_dir = _join_root(godot_project, *parts, character_name)
    os.makedirs(target_dir, exist_ok=True)
    copied = {}
    for source, relative in _iter_files(files):
        destination = _join_root(target_dir, *relative.split("/"))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copyfile(source, destination)
        copied[relative] = destination

    readme_path = _join_root(target_dir, "README.md")
    with open(readme_path, "w", encoding="utf-8") as handle:
        handle.write(_GODOT_README)
    return {"dir": target_dir, "files": copied, "readme": readme_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mirror character GLBs to dated storage")
    parser.add_argument(
        "--files",
        nargs="+",
        default=[],
        metavar="SRC[::REL]",
        help="source files; SRC::REL overrides the relative destination name",
    )
    parser.add_argument(
        "--drive-root",
        default=os.environ.get(DRIVE_ROOT_ENV),
        help=f"mirror root (default: ${DRIVE_ROOT_ENV})",
    )
    parser.add_argument("--date", help="build date YYYY-MM-DD (default: today)")
    parser.add_argument("--name", required=True, help="character name")
    parser.add_argument("--godot-project", help="also copy into this Godot project")
    parser.add_argument("--require-drive", action="store_true", help="fail if no drive root")
    parser.add_argument("--force", action="store_true", help="allow overwriting a dated folder")
    args = parser.parse_args(argv)

    entries = []
    for item in args.files:
        if "::" in item:
            source, relative = item.split("::", 1)
        else:
            source, relative = item, os.path.basename(item)
        entries.append((source, relative))

    if not args.drive_root and not args.require_drive:
        print("MIRROR_SKIP")
        return 0

    date_text = args.date or _dt.date.today().isoformat()
    try:
        result = mirror_files(
            entries,
            args.drive_root,
            date_text,
            args.name,
            require=args.require_drive,
            force=args.force,
        )
        if args.godot_project:
            copy_to_godot(entries, args.godot_project, args.name)
        print(f"MIRROR_OK {result['dir']}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"MIRROR_FAILED {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
