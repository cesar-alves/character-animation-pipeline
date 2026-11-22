# Batch pipeline usage

## Exact CLI

Fetch/verify the pinned Mesh2Motion assets once (idempotent):

```bash
python3 tools/fetch_vendor.py --index vendor/index.json --dest vendor/bin
# FETCH_OK 6
```

Run the whole pipeline from the repository root:

```bash
python3 pipeline.py --job config/jobs.json \
    [--in models] [--out out] [--vendor vendor/bin] [--no-fetch] \
    [--drive-root /mnt/drive/characters] [--godot-project /path/to/godot] \
    [--date 2026-11-22] [--force]
```

`--in` only changes where a bare model filename is looked up; model paths in the
job are still resolved relative to the repository root first. `--force` is only
passed to the dated Drive mirror. The CLI never imports `bpy`; only the Blender
worker does. A missing fetch or any failed character prints `PIPELINE_FAILED
<reason>` and exits 1; success prints `PIPELINE_OK <n> character(s)`.

Internally the worker is invoked once per character:

```bash
/usr/local/bin/blender -b --factory-startup --python blender/batch.py -- \
    --job work/<name>.job.json --vendor vendor/bin --out out
```

It prints `REPORT:<tag>:<json>` progress lines (including `REPORT:fit:`,
`REPORT:skin:`, `REPORT:deformation:` and `REPORT:export:`), then `BATCH_OK
<output_glb>` or `BATCH_FAILED`. Blender can exit 0 on an uncaught Python error,
so the worker wraps everything, prints `BATCH_FAILED` and forces exit 1; the
CLI treats a run without `BATCH_OK` as a hard failure.

## Job schema

`config/jobs.example.json` is a template. `config/jobs.json` is the file you
edit; it is ignored by git.

```json
{
  "schema_version": 1,
  "characters": [
    {
      "name": "hero",
      "model": "models/hero.glb",
      "clips": ["idle-a", "walk", "run-anime", "jump-2"],
      "profile": "m2m-human",
      "fit": "config/fit/hero.json"
    }
  ]
}
```

| Field | Required | Meaning |
|---|---|---|
| `schema_version` | yes | Must be `1`. |
| `characters` | yes | Non-empty list; names must be unique and safe as file names. |
| `name` | yes | Output stem: `out/<name>.glb`, `builds/<name>.json`, `reports/<name>.json`. |
| `model` | yes | Input GLB path (absolute or relative to the repo root). |
| `clips` | yes | Logical M2M clip names (`.glb` suffix optional); files must exist under `--vendor`. Duplicates are dropped, order is preserved. |
| `profile` | no | Defaults to `m2m-human`; the Blender build always keeps the 66 M2M bone names. The profile is only an opt-in validation/Godot renaming concern. |
| `fit` | no | Optional fit-config JSON path (absolute or repo-relative). |

Unknown top-level or per-character fields are rejected. Inspect a jobs file
without building anything with `python3 -m src.job config/jobs.json`.

### Fit config semantics

A generated `config/fit/<name>.json` follows the interactive-fit schema:

```json
{
  "schema_version": 1,
  "model": "...",
  "profile": "m2m-human",
  "global": {"uniform_scale": 1.0, "offset": [0, 0, 0], "yaw_degrees": 0.0},
  "bones": {"pelvis": {"head": [x, y, z], "tail": [x, y, z], "roll": 0.0}},
  "notes": ""
}
```

- `head`/`tail` are **Y-up metres in glTF space, feet at Y=0**. The worker
  converts each to Blender coordinates with `(x, y, z) -> (x, -z, y)`.
- `roll` is a Blender `EditBone.roll` in **radians** and is copied verbatim —
  never converted to degrees, never omitted when present. The inverse mapping
  is a proper rotation, so roll is invariant.
- `global.uniform_scale`/`offset` are **informational only**: the interactive
  fitter has already baked them into the per-bone head/tail values, so they are
  never re-applied to the bones. `yaw_degrees` is reserved and always `0.0`.
- Bones absent from `bones` keep the auto-fit pose. With no `fit`, auto-fit
  scales the skeleton so its height matches the model's world bounds, puts its
  lowest point at model min-Z and its X/Y centre at the model's X/Y centre,
  then applies the object transform.

## Tracked vs gitignored

| Path | Status | Contents |
|---|---|---|
| `out/<name>.glb` | gitignored | The built skinned model with all selected actions. |
| `vendor/bin/*.glb`, `work/` | gitignored | Pinned downloads and temporary per-character job JSON. |
| `builds/<name>.json` | tracked | Provenance: tool version, UTC timestamp, model/clip/fit hashes, bone count, exporter settings, validation summary. |
| `reports/<name>.json` | tracked | Validator checks (`ok`, `checks`, `bones`, `clips`, `errors`). |
| `docs/e2e-run.md` | tracked | Captured output of `tests/e2e.sh`. |

## Skinning and export

The model's own armature (and any meshes bound to it) is discarded; the mesh is
unbound and re-skinned to the fitted 66-bone M2M skeleton. Blender's bone-heat
`ARMATURE_AUTO` is the primary method; if it raises or leaves any vertex with
no weight, a proximity fallback assigns the four nearest bone segments with
normalised inverse-distance weights. Every vertex is asserted to have a
non-zero influence, and influences are capped at four for glTF.

Each clip GLB is imported, the action animating the most bones on our skeleton
is chosen by the spike's scoring rule, copied, renamed to the logical clip
name, and bound to the armature. All imported clip objects are deleted before
export. One NLA track per clip holds its own action; the scene frame range
covers every action, and the export uses `export_animation_mode='ACTIONS'`,
`export_nla_strips=False`, `export_anim_single_armature=False`,
`export_def_bones=True`, `export_yup=True`, `use_selection=True` and
`export_apply=True`. The worker reparses the exported GLB JSON and fails unless
every requested clip appears as an animation.

## How root motion is stripped

For every copied action, each keyframe on
`pose.bones["root"].location`, `pose.bones["pelvis"].location` or
`pose.bones["Hips"].location` is set to zero — including its Bezier handles, so
interpolation cannot reintroduce drift. Rotations are untouched. All remaining
`pose.bones["*"].location` values are multiplied by the fit uniform scale so
translations stay in metres. A flat zero channel (or no channel) passes
`src.validate`'s `root_translation_constant` check. The default build keeps
the M2M names `root` and `pelvis`; the `polygon_humanoid` profile is not applied
inside Blender.

## Tests

```bash
python3 -m unittest discover -s tests -v
bash tests/e2e.sh      # writes docs/e2e-run.md, prints E2E_OK
```
