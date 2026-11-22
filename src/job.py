"""Job-file loading and per-character path resolution (standard library only).

A jobs file lists characters, each of which produces one output GLB. This
module never imports ``bpy``. Run ``python3 -m src.job config/jobs.json`` to
print a human-readable summary of a jobs file.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_PROFILE = "m2m-human"

_TOP_LEVEL_FIELDS = {"schema_version", "characters"}
_CHARACTER_FIELDS = {"name", "model", "clips", "profile", "fit"}


def _read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise ValueError(f"cannot read job file {path!r}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in job file {path!r}: {exc}") from exc


def _clip_logical_name(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where} must be a non-empty string")
    name = value.strip().replace("\\", "/")
    if "/" in name:
        name = os.path.basename(name)
    if name.lower().endswith(".glb"):
        name = name[:-4]
    if not name or name in (".", ".."):
        raise ValueError(f"{where} has an invalid clip name: {value!r}")
    return name


def load_jobs(path: str) -> dict:
    """Load and validate a jobs JSON file.

    Returns a normalized dict with ``schema_version`` and ``characters``. Clip
    names are reduced to logical stems (``walk.glb`` -> ``walk``) and
    deduplicated while preserving order.
    """
    data = _read_json(path)
    if not isinstance(data, dict):
        raise ValueError("job file root must be a JSON object")

    unknown = sorted(set(data) - _TOP_LEVEL_FIELDS)
    if unknown:
        raise ValueError("unknown top-level field(s): " + ", ".join(unknown))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version {data.get('schema_version')!r} "
            f"(expected {SCHEMA_VERSION})"
        )
    characters = data.get("characters")
    if not isinstance(characters, list) or not characters:
        raise ValueError("characters must be a non-empty list")

    normalized = []
    seen: set[str] = set()
    for index, character in enumerate(characters):
        where = f"characters[{index}]"
        if not isinstance(character, dict):
            raise ValueError(f"{where} must be a JSON object")
        unknown = sorted(set(character) - _CHARACTER_FIELDS)
        if unknown:
            raise ValueError(f"{where} has unknown field(s): " + ", ".join(unknown))

        name = character.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{where}.name must be a non-empty string")
        name = name.strip()
        if name in (".", "..") or "/" in name or "\\" in name or os.path.isabs(name):
            raise ValueError(f"{where}.name must be a safe file name, got {name!r}")
        if name in seen:
            raise ValueError(f"duplicate character name: {name!r}")
        seen.add(name)

        model = character.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ValueError(f"{where}.model must be a non-empty path string")

        clips_value = character.get("clips")
        if not isinstance(clips_value, list) or not clips_value:
            raise ValueError(f"{where}.clips must be a non-empty list of clip names")
        clips: list[str] = []
        for clip_index, raw_clip in enumerate(clips_value):
            clip = _clip_logical_name(raw_clip, f"{where}.clips[{clip_index}]")
            if clip not in clips:
                clips.append(clip)

        profile = character.get("profile", DEFAULT_PROFILE)
        if profile is None:
            profile = DEFAULT_PROFILE
        if not isinstance(profile, str) or not profile.strip():
            raise ValueError(f"{where}.profile must be a non-empty string")

        fit = character.get("fit")
        if fit is not None and (not isinstance(fit, str) or not fit.strip()):
            raise ValueError(f"{where}.fit must be a path string or null")

        normalized.append(
            {
                "name": name,
                "model": model.strip(),
                "clips": clips,
                "profile": profile.strip(),
                "fit": fit.strip() if isinstance(fit, str) else None,
            }
        )

    return {"schema_version": SCHEMA_VERSION, "characters": normalized}


def _first_existing(candidates: list[str]) -> str | None:
    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def resolve_character(
    job: dict,
    base_dir: str,
    vendor_dir: str,
    out_dir: str,
    fit_dir: str,
    *,
    model_dir: str | None = None,
) -> dict:
    """Resolve one character's paths to absolute locations.

    ``base_dir`` is the repository root; ``vendor_dir`` and ``out_dir`` are the
    absolute asset/output directories; ``fit_dir`` is the default directory for
    bare fit file names. The optional ``model_dir`` is the directory given by
    the CLI ``--in`` flag and is used as a fallback when a model path cannot be
    found relative to ``base_dir``.
    """
    if not isinstance(job, dict):
        raise ValueError("character must be a JSON object")
    name = job.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("character.name is required")
    name = name.strip()

    model = job.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError(f"character {name!r}: model is required")
    model = model.strip()
    model_candidates = [model] if os.path.isabs(model) else [
        os.path.join(base_dir, model),
        os.path.join(base_dir, os.path.basename(model)),
    ]
    if model_dir:
        model_candidates.append(os.path.join(model_dir, os.path.basename(model)))
        model_candidates.append(os.path.join(model_dir, model))
    model_path = _first_existing(model_candidates)
    if model_path is None:
        raise ValueError(
            f"character {name!r}: model not found (tried: "
            + ", ".join(model_candidates)
            + ")"
        )

    clips_value = job.get("clips")
    if not isinstance(clips_value, list) or not clips_value:
        raise ValueError(f"character {name!r}: clips must be a non-empty list")
    clips: list[str] = []
    clip_paths: dict[str, str] = {}
    for raw_clip in clips_value:
        clip = _clip_logical_name(raw_clip, f"character {name!r} clip")
        if clip in clips:
            continue
        file_name = clip if clip.lower().endswith(".glb") else clip + ".glb"
        clip_path = os.path.join(vendor_dir, file_name)
        if not os.path.isfile(clip_path):
            raise ValueError(
                f"character {name!r}: clip {clip!r} not found in vendor dir "
                f"{vendor_dir!r} (expected {clip_path})"
            )
        clips.append(clip)
        clip_paths[clip] = os.path.abspath(clip_path)

    fit_path = None
    fit_value = job.get("fit")
    if fit_value:
        fit_candidates = [fit_value] if os.path.isabs(fit_value) else [
            os.path.join(base_dir, fit_value),
            os.path.join(fit_dir, fit_value),
            os.path.join(fit_dir, os.path.basename(fit_value)),
        ]
        fit_path = _first_existing(fit_candidates)
        if fit_path is None:
            raise ValueError(
                f"character {name!r}: fit config not found (tried: "
                + ", ".join(fit_candidates)
                + ")"
            )

    profile = job.get("profile") or DEFAULT_PROFILE
    return {
        "name": name,
        "model": os.path.abspath(model_path),
        "clips": clips,
        "clip_paths": clip_paths,
        "profile": profile,
        "fit": fit_path,
        "vendor": os.path.abspath(vendor_dir),
        "out_glb": os.path.join(out_dir, name + ".glb"),
    }


def write_tmp_job(character: dict, path: str) -> str:
    """Write the per-character JSON consumed by ``blender/batch.py``."""
    payload = {
        "name": character["name"],
        "model": character["model"],
        "clips": list(character["clips"]),
        "profile": character.get("profile") or DEFAULT_PROFILE,
        "fit": character.get("fit"),
    }
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect a character pipeline jobs file")
    parser.add_argument("job", help="path to config/jobs.json")
    args = parser.parse_args(argv)
    try:
        jobs = load_jobs(args.job)
    except ValueError as exc:
        print(f"JOB_FAILED {exc}")
        return 1
    print(f"JOB_OK schema_version={jobs['schema_version']} characters={len(jobs['characters'])}")
    for character in jobs["characters"]:
        fit = character["fit"] or "-"
        print(
            f"  {character['name']}: model={character['model']} "
            f"clips={','.join(character['clips'])} "
            f"profile={character['profile']} fit={fit}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
