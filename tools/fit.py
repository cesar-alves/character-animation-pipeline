#!/usr/bin/env python3
"""Stdlib-only CLI for preparing an interactive skeleton-fit session.

    python3 tools/fit.py --model models/foo.glb --interactive \
        [--config config/fit/foo.json] [--skeleton vendor/bin/skeleton.glb]

It resolves the pinned CC0 M2M skeleton, creates work/ and config/fit/ if
needed, runs Blender 5.2 headlessly with blender/fit_prepare.py, and prints the
resulting .blend and fit JSON paths.  With --interactive it then opens the
saved .blend in a GUI Blender with blender/fit_ui.py already registered (when
a display is available).  --no-interactive performs only the headless step.

This file never imports bpy -- Blender is always a separate subprocess.
"""

import argparse
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BLENDER = "/usr/local/bin/blender"
DEFAULT_SKELETON = "vendor/bin/skeleton.glb"


def build_parser():
    p = argparse.ArgumentParser(
        description="Prepare an interactive Mesh2Motion skeleton fit session.",
    )
    p.add_argument("--model", required=True, help="target GLB (path recorded in the fit config)")
    p.add_argument("--config", default=None, help="fit JSON to write (default: config/fit/<model>.json)")
    p.add_argument("--blend", default=None, help="scratch .blend to write (default: work/fit/<model>.blend)")
    p.add_argument("--skeleton", default=DEFAULT_SKELETON, help="M2M human skeleton GLB")
    p.add_argument("--blender", default=DEFAULT_BLENDER, help="Blender 5.2 executable")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--interactive", dest="interactive", action="store_true",
                      help="open the prepared .blend in the GUI with the M2M Fit panel")
    mode.add_argument("--no-interactive", dest="interactive", action="store_false",
                      help="headless only (default)")
    p.set_defaults(interactive=False)
    return p


def stem_of(model):
    return os.path.splitext(os.path.basename(model))[0] or "model"


def main(argv=None):
    args = build_parser().parse_args(argv)
    model_arg = args.model  # keep exactly as given: this is config["model"]
    stem = stem_of(model_arg)
    cfg_rel = args.config or os.path.join("config", "fit", stem + ".json")
    blend_rel = args.blend or os.path.join("work", "fit", stem + ".blend")
    skel_rel = args.skeleton

    for d in ("work", os.path.dirname(cfg_rel), os.path.dirname(blend_rel)):
        if d:
            os.makedirs(os.path.join(ROOT, d), exist_ok=True)

    model_abs = os.path.join(ROOT, model_arg) if not os.path.isabs(model_arg) else model_arg
    skel_abs = os.path.join(ROOT, skel_rel) if not os.path.isabs(skel_rel) else skel_rel
    if not os.path.isfile(model_abs):
        print("FIT_ERROR model not found: " + model_abs, file=sys.stderr)
        return 2
    if not os.path.isfile(skel_abs):
        print("FIT_ERROR skeleton not found: " + skel_abs +
              " (download the CC0 M2M skeleton into " + DEFAULT_SKELETON + ")", file=sys.stderr)
        return 2

    cmd = [
        args.blender, "-b", "--factory-startup", "--python", "blender/fit_prepare.py", "--",
        "--model", model_arg,
        "--skeleton", skel_rel,
        "--blend", blend_rel,
        "--config", cfg_rel,
    ]
    if args.interactive:
        cmd.append("--interactive")

    print("FIT_RUN " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.returncode != 0:
        print("FIT_ERROR Blender failed with exit code %d" % proc.returncode, file=sys.stderr)
        return proc.returncode

    ok = None
    for line in proc.stdout.splitlines():
        if line.startswith("FIT_PREPARE_OK "):
            parts = line.split()
            if len(parts) >= 3:
                ok = (parts[1], parts[2])
    if ok is None:
        print("FIT_ERROR no FIT_PREPARE_OK marker in Blender output", file=sys.stderr)
        return 1
    blend_path, config_path = ok

    if args.interactive:
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        if has_display:
            gui_cmd = [args.blender, blend_rel, "--python", "blender/fit_ui.py"]
            subprocess.Popen(gui_cmd, cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("FIT_GUI_LAUNCHED " + blend_path)
        else:
            print("FIT_GUI_SKIPPED no display detected; open the .blend manually and run "
                  "blender/fit_ui.py from the Text Editor")
    else:
        print("FIT_HEADLESS no GUI (--no-interactive)")

    print("FIT_BLEND " + blend_path)
    print("FIT_CONFIG " + config_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
