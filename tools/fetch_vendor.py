#!/usr/bin/env python3
"""Fetch and verify the pinned Mesh2Motion assets listed in vendor/index.json.

Standard library only. Downloads go to ``vendor/bin/<basename>`` by default.
A file whose sha256 already matches is left untouched, so the tool is
idempotent and performs no network access when everything is in place.

On success prints ``FETCH_OK <n>`` where n is the number of verified files.
On failure prints ``FETCH_FAILED <reason>`` and exits non-zero.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

CHUNK_SIZE = 1024 * 1024
TIMEOUT_SECONDS = 60


class FetchError(Exception):
    """A single, human-readable failure reason."""


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_index(index_path: str) -> dict:
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            index = json.load(handle)
    except OSError as exc:
        raise FetchError(f"cannot read index {index_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise FetchError(f"invalid JSON in index {index_path}: {exc}") from exc

    if not isinstance(index, dict):
        raise FetchError("index root must be an object")
    if index.get("schema_version") != 1:
        raise FetchError("unsupported index schema_version")
    files = index.get("files")
    if not isinstance(files, list) or not files:
        raise FetchError("index.files must be a non-empty list")
    for entry in files:
        if not isinstance(entry, dict):
            raise FetchError("each index.files entry must be an object")
        for field in ("path", "sha256", "size", "url"):
            if not entry.get(field):
                raise FetchError(f"index file entry missing {field}")
        if len(str(entry["sha256"])) != 64:
            raise FetchError(f"bad sha256 for {entry['path']}")
    return index


def expected_checks(entry: dict) -> None:
    """Verify a downloaded file against the index entry."""
    expected_hash = str(entry["sha256"]).lower()
    expected_size = int(entry["size"])
    actual_hash = sha256_file(entry["_temp"])
    actual_size = os.path.getsize(entry["_temp"])
    if actual_size != expected_size:
        raise FetchError(
            f"size mismatch for {entry['_basename']}: "
            f"expected {expected_size}, got {actual_size}"
        )
    if actual_hash != expected_hash:
        raise FetchError(
            f"sha256 mismatch for {entry['_basename']}: "
            f"expected {expected_hash}, got {actual_hash}"
        )


def download(entry: dict) -> None:
    request = urllib.request.Request(
        str(entry["url"]),
        headers={"User-Agent": "character-animation-pipeline/fetch_vendor"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            with open(entry["_temp"], "wb") as handle:
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
    except (urllib.error.URLError, OSError) as exc:
        raise FetchError(f"download failed for {entry['_basename']}: {exc}") from exc


def fetch(index_path: str, dest: str, force: bool) -> int:
    index = load_index(index_path)
    os.makedirs(dest, exist_ok=True)

    checked = 0
    for entry in index["files"]:
        basename = os.path.basename(str(entry["path"]))
        entry["_basename"] = basename
        target = os.path.join(dest, basename)
        entry["_temp"] = target + ".part"

        already_ok = (
            os.path.isfile(target)
            and sha256_file(target) == str(entry["sha256"]).lower()
            and os.path.getsize(target) == int(entry["size"])
        )
        if already_ok and not force:
            checked += 1
            continue

        try:
            download(entry)
            expected_checks(entry)
            os.replace(entry["_temp"], target)
        except FetchError:
            if os.path.exists(entry["_temp"]):
                os.unlink(entry["_temp"])
            raise
        checked += 1

    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default="vendor/index.json")
    parser.add_argument("--dest", default="vendor/bin")
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download and re-verify every file, even correct ones",
    )
    args = parser.parse_args()

    try:
        checked = fetch(args.index, args.dest, args.force)
    except FetchError as exc:
        reason = " ".join(str(exc).split())
        print(f"FETCH_FAILED {reason}")
        return 1
    except Exception as exc:  # defensive: keep the machine-readable contract
        reason = " ".join(f"{type(exc).__name__}: {exc}".split())
        print(f"FETCH_FAILED {reason}")
        return 1

    print(f"FETCH_OK {checked}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
