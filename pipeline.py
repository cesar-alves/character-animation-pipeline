#!/usr/bin/env python3
"""Headless character build CLI (standard library only; never imports bpy).

    python3 pipeline.py --job config/jobs.json [--in models] [--out out]
        [--vendor vendor/bin] [--no-fetch] [--drive-root ...]
        [--godot-project ...] [--date YYYY-MM-DD] [--force]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import subprocess
import sys

from src import build_record, job as job_module, mirror, validate

ROOT = os.path.dirname(os.path.abspath(__file__))
BLENDER = os.environ.get("CHARACTER_PIPELINE_BLENDER", "/usr/local/bin/blender")


def _absolute(path: str) -> str:
    return path if os.path.isabs(path) else os.path.abspath(os.path.join(os.getcwd(), path))


def _run_blender(character: dict, vendor_dir: str, out_dir: str, work_dir: str) -> list[str]:
    tmp_job = job_module.write_tmp_job(
        character, os.path.join(work_dir, character["name"] + ".job.json")
    )
    command = [
        BLENDER,
        "-b",
        "--factory-startup",
        "--python",
        os.path.join(ROOT, "blender", "batch.py"),
        "--",
        "--job",
        tmp_job,
        "--vendor",
        vendor_dir,
        "--out",
        out_dir,
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    lines: list[str] = []
    for line in process.stdout:
        print(line, end="")
        lines.append(line)
        sys.stdout.flush()
    return_code = process.wait()
    if return_code != 0 or not any("BATCH_OK" in line for line in lines):
        reason = next(
            (line.strip() for line in reversed(lines) if "BATCH_FAILED" in line),
            f"blender exited {return_code} without BATCH_OK",
        )
        raise RuntimeError(f"character {character['name']!r}: {reason}")
    return lines


def _fetch_vendor(vendor_dir: str) -> None:
    command = [
        sys.executable,
        os.path.join(ROOT, "tools", "fetch_vendor.py"),
        "--index",
        os.path.join(ROOT, "vendor", "index.json"),
        "--dest",
        vendor_dir,
    ]
    result = subprocess.run(
        command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    print(result.stdout, end="")
    sys.stdout.flush()
    if result.returncode != 0 or "FETCH_OK" not in result.stdout:
        raise RuntimeError(
            "vendor fetch failed: "
            + next(
                (line.strip() for line in result.stdout.splitlines() if "FETCH_FAILED" in line),
                f"exit {result.returncode}",
            )
        )


def build(args: argparse.Namespace) -> int:
    jobs_path = _absolute(args.job)
    vendor_dir = _absolute(args.vendor)
    out_dir = _absolute(args.out)
    model_dir = _absolute(args.in_dir) if args.in_dir else None
    base_dir = ROOT
    for directory in (out_dir, os.path.join(ROOT, "work"), os.path.join(ROOT, "builds"),
                      os.path.join(ROOT, "reports")):
        os.makedirs(directory, exist_ok=True)

    try:
        jobs = job_module.load_jobs(jobs_path)
        if not args.no_fetch:
            _fetch_vendor(vendor_dir)
    except ValueError as exc:
        print(f"PIPELINE_FAILED {exc}")
        return 1
    except RuntimeError as exc:
        print(f"PIPELINE_FAILED {exc}")
        return 1

    date = args.date or _dt.date.today().isoformat()
    drive_root = args.drive_root or os.environ.get(mirror.DRIVE_ROOT_ENV)
    completed = 0
    failures: list[str] = []

    for raw_character in jobs["characters"]:
        name = raw_character["name"]
        try:
            character = job_module.resolve_character(
                raw_character,
                base_dir,
                vendor_dir,
                out_dir,
                os.path.join(ROOT, "config", "fit"),
                model_dir=model_dir,
            )
            print(f"PIPELINE_BUILD {name}", flush=True)
            _run_blender(character, vendor_dir, out_dir, os.path.join(ROOT, "work"))

            report = validate.validate_glb(character["out_glb"], expected_clips=character["clips"])
            report_path = validate.write_report(report, os.path.join(ROOT, "reports", name + ".json"))
            print(f"PIPELINE_VALIDATE {name} {'OK' if report['ok'] else 'FAILED'}", flush=True)
            for error in report["errors"]:
                print(f"  - {error}", flush=True)

            record = build_record.make_build_record(
                name=name,
                model=character["model"],
                profile=character["profile"],
                clips=character["clips"],
                clip_paths=character["clip_paths"],
                vendor_dir=vendor_dir,
                bone_count=len(report.get("bones", [])),
                fit=character["fit"],
                exporter_settings={
                    "export_animation_mode": "ACTIONS",
                    "export_nla_strips": False,
                    "export_anim_single_armature": False,
                    "export_def_bones": True,
                    "export_yup": True,
                    "use_selection": True,
                    "export_apply": True,
                },
                validation=report,
            )
            record_path = build_record.write_build_record(
                os.path.join(ROOT, "builds", name + ".json"), record
            )

            if not report["ok"]:
                failures.append(f"{name}: validation failed: {'; '.join(report['errors'])}")
                continue

            files = [
                (character["out_glb"], name + ".glb"),
                (record_path, os.path.join("builds", name + ".json")),
                (report_path, os.path.join("reports", name + ".json")),
            ]
            if drive_root:
                result = mirror.mirror_files(
                    files, drive_root, date, name, force=args.force
                )
                print(f"PIPELINE_MIRROR {name} {result['dir']}", flush=True)
            if args.godot_project:
                result = mirror.copy_to_godot(files, args.godot_project, name)
                print(f"PIPELINE_GODOT {name} {result['dir']}", flush=True)
            completed += 1
        except (OSError, ValueError, RuntimeError) as exc:
            failures.append(f"{name}: {exc}")
            print(f"PIPELINE_CHARACTER_FAILED {name}: {exc}", file=sys.stderr, flush=True)

    if failures:
        print("PIPELINE_FAILED " + "; ".join(failures))
        return 1
    print(f"PIPELINE_OK {completed} character(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, help="jobs JSON file")
    parser.add_argument("--in", dest="in_dir", default="models", help="model input directory")
    parser.add_argument("--out", default="out", help="output directory for GLBs")
    parser.add_argument("--vendor", default="vendor/bin", help="vendored M2M asset directory")
    parser.add_argument("--no-fetch", action="store_true", help="skip tools/fetch_vendor.py")
    parser.add_argument("--drive-root", help="dated Drive mirror root")
    parser.add_argument("--godot-project", help="also copy the GLB into this Godot project")
    parser.add_argument("--date", help="mirror date YYYY-MM-DD (default: today)")
    parser.add_argument("--force", action="store_true", help="allow overwriting a dated folder")
    args = parser.parse_args(argv)
    return build(args)


if __name__ == "__main__":
    sys.exit(main())
