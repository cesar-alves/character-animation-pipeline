# Interactive skeleton fitting

This layer is the offline equivalent of Mesh2Motion's "drag the bones into the
model" step. It prepares a Blender session in which an artist aligns the CC0
M2M human skeleton to a static character GLB, and writes a small JSON
**fit config** that the headless batch pipeline consumes.

This document is the authoritative fit contract (the `docs/fit-contract.md`
link in `docs/pipeline.md` refers to it).

Owned files: `blender/fit_prepare.py`, `blender/fit_ui.py`, `tools/fit.py`, this
document. Nothing here imports or modifies `pipeline.py` or `src/*`.

## Artist workflow

1. Fetch the CC0 skeleton into `vendor/bin/skeleton.glb` (gitignored):

   ```bash
   curl -L -o vendor/bin/skeleton.glb \
     https://raw.githubusercontent.com/Mesh2Motion/mesh2motion-app/main/static/assets/human/skeleton.glb
   ```

2. Prepare a session (from the repo root, Blender 5.2 on `PATH` or at
   `/usr/local/bin/blender`):

   ```bash
   python3 tools/fit.py --interactive --model models/my_character.glb
   ```

   This creates `work/fit/my_character.blend` (scratch, gitignored) and
   `config/fit/my_character.json` (the file to commit). `--no-interactive`
   runs only the headless preparation. The CLI never imports `bpy`; it calls
   `blender -b --factory-startup --python blender/fit_prepare.py -- ...`. With
   `--interactive`, after the headless preparation it opens the saved `.blend`
   in a GUI Blender with `blender/fit_ui.py` registered. If no display is
   detected it prints `FIT_GUI_SKIPPED`; the panel can then be registered from
   Blender's Text Editor (open the .blend, open `blender/fit_ui.py`, Run Script).

   Equivalent direct invocation:

   ```bash
   blender -b --factory-startup --python blender/fit_prepare.py -- \
     --model models/my_character.glb \
     --skeleton vendor/bin/skeleton.glb \
     --blend work/fit/my_character.blend \
     --config config/fit/my_character.json \
     [--interactive]
   ```

   On success it prints `FIT_PREPARE_OK <blend> <config>`.

3. The `.blend` opens in a front orthographic view with the rig in **Edit
   Mode**. Move bone heads/tails to match the character's joints; adjust Roll
   in the Bone properties if you rotate a bone. Keep bone names and the
   parent/child hierarchy intact — animation transplant is by bone name.

4. In the 3D View N-panel, open the **M2M Fit** tab. Write notes in the text
   field and click **Export Fit Config**. **Reload Fit Config** discards
   unsaved edits; **Auto Fit Again** restores the pristine template and
   recomputes scale / foot alignment / X-Y centering from the current mesh.

   The operators are `m2m_fit.export_config`, `m2m_fit.reload_config`,
   `m2m_fit.auto_fit_again` and `m2m_fit.select_config`. The panel stores the
   path in `Scene.m2m_fit_config` and notes in `Scene.m2m_fit_notes`.

## The fit config schema

```json
{
  "schema_version": 1,
  "model": "models/foo.glb",
  "profile": "m2m-human",
  "global": { "uniform_scale": 1.0, "offset": [0.0, 0.0, 0.0], "yaw_degrees": 0.0 },
  "bones": {
    "pelvis":   { "head": [x,y,z], "tail": [x,y,z], "roll": 0.0 },
    "spine_01": { "head": [x,y,z], "tail": [x,y,z], "roll": 0.0 }
  },
  "notes": ""
}
```

- `schema_version`: `1`. Bump only with a coordinated pipeline change.
- `model`: the path passed to `--model`, kept verbatim (repo-relative path).
- `profile`: `m2m-human` — the skeleton template the bone names refer to.
- `global`: the auto-fit parameters that were **baked into the bone
  coordinates**: `uniform_scale` matches skeleton height to model height using
  the `pelvis -> ... -> head` chain for the top and the foot chains for the
  ground; `offset` aligns feet to Y=0 and centers X/Y on the model. `offset`
  is in model space. `yaw_degrees` is reserved (emitted as `0.0`); the UI does
  not change it. **Because bone coordinates are already final and absolute,
  do not apply `global` again to bones present in `bones`.**
- `bones`: one entry per M2M bone (the pinned GLB currently has **66** bones:
  `root`, pelvis/spine/neck/head, clavicles, arms, hands, legs/feet and all
  finger/leaf chains). `head`/`tail` are **final normalized model space**
  coordinates in **metres, glTF Y-up, feet at Y=0**, rounded to 6 decimals.
  `roll` is in **radians**, exactly as Blender's `EditBone.roll`.
- `notes`: free-form artist notes; the export operator preserves the other
  top-level keys and only rewrites `bones` and `notes`.
- **Override semantics:** only bones present in `bones` override the
  auto-fit pose; omitted bones keep the pipeline's auto-fit result. The
  preparation step initially writes *every* bone, so the artist can delete
  entries for bones they did not touch.

## How the batch pipeline consumes it

1. Run the normal `prep` step to normalize a model GLB the same way (metres,
   Y-up in glTF / Z-up in Blender, feet at 0).
2. Import the pinned M2M skeleton and reproduce the auto-fit (or read
   `global` for the exact scale/offset that was baked).
3. For each bone in `bones`, set the corresponding edit bone to the config
   `head`/`tail` (converted back to Blender space: `(x, y, z)_config ->
   (x, -z, y)_blender`) and set `EditBone.roll` to the stored value in
   **radians**. Do this before bone-heat weighting and before importing M2M
   animation actions.
4. Bone names and hierarchy are unchanged, so M2M clip actions can be
   transplanted directly with no general retargeting.

### Why roll must be preserved

Roll defines each bone's twist axis. A wrong roll makes transplanted
animations twist limbs inside-out even though head/tail positions look right.
The Blender -> glTF coordinate conversion used here, `(x, y, z) -> (x, z,
-y)`, is a proper rotation (determinant +1), not a mirror, so roll is
invariant under it and is copied verbatim. Store it as a radian float; never
round it to degrees or drop it.

## Environment / implementation notes

- Blender 5.2 LTS (`/usr/local/bin/blender`). The UI uses `bpy.types.Panel`,
  `bpy.types.Operator` and `bl_property` file-path string properties.
- `tools/fit.py` is stdlib-only and never imports `bpy`.
- The prepared `.blend` contains exactly one model (static meshes, world
  transforms baked in, armature modifiers removed) and one armature. Custom
  bone-shape meshes are detected through `pose.bones[].custom_shape` and
  removed for **both** the model and skeleton GLBs. This matters: the pinned
  `human/model.glb` also ships a debug `Icosphere`, and including it in the
  mesh bounds inflates the measured height from 1.8296 m to 2.8292 m and the
  fit scale from 1.1249 to 1.7395. Armature object transform is identity;
  all fitting is baked into edit bones.
- `tests/e2e_fit.sh` covers the whole hand-off against the pinned CC0 assets:
  generate a config with `tools/fit.py`, consume it in `pipeline.py`, and
  validate the exported GLB. It reports `E2E_FIT_OK`.
- The armature carries `m2m_rest_bones_json` (the pristine template pose) so
  "Auto Fit Again" can truly reset; scene ID props `m2m_fit_config_path`,
  `m2m_fit_armature_name`, `m2m_fit_interactive` are also written.
- The `.blend` is saved in Edit Mode, which is why the UI helpers leave and
  re-enter Edit Mode safely.

## Verification (exact commands and output)

The test model is a tiny static humanoid made of boxes (~1.75 m tall),
generated with this Blender script (saved as `/tmp/make_test_humanoid.py`):

```python
import bpy, os, sys
args = sys.argv[sys.argv.index("--") + 1:]
out = os.path.abspath(args[0])
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

def box(name, loc, size):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = (size[0] / 2.0, size[1] / 2.0, size[2] / 2.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return o

box("Head",  (0.0, 0.0, 1.63), (0.20, 0.20, 0.24))
box("Neck",  (0.0, 0.0, 1.46), (0.10, 0.10, 0.10))
box("Torso", (0.0, 0.0, 1.14), (0.36, 0.20, 0.60))
box("Pelvis", (0.0, 0.0, 0.86), (0.28, 0.20, 0.20))
for s in (-1, 1):
    box("UpperArm_%s" % s, (s * 0.30, 0.0, 1.30), (0.44, 0.14, 0.14))
    box("LowerArm_%s" % s, (s * 0.60, 0.0, 1.30), (0.24, 0.12, 0.12))
    box("Thigh_%s" % s, (s * 0.09, 0.0, 0.52), (0.14, 0.16, 0.62))
    box("Shin_%s" % s, (s * 0.09, 0.0, 0.13), (0.13, 0.15, 0.26))
    box("Foot_%s" % s, (s * 0.09, -0.06, 0.04), (0.13, 0.28, 0.08))

bpy.ops.export_scene.gltf(filepath=out, export_format="GLB",
                          export_yup=True, export_apply=True)
print("TEST_HUMANOID_OK", out, os.path.getsize(out))
```

All commands were run from the repository root. Paths under `local/` and
`vendor/bin/` are gitignored scratch data.

```console
$ python3 -m py_compile blender/fit_prepare.py blender/fit_ui.py tools/fit.py
PY_COMPILE_OK

$ /usr/local/bin/blender -b --factory-startup --python /tmp/make_test_humanoid.py -- local/test-humanoid.glb
TEST_HUMANOID_OK /home/drexer/Projects/cesar-alves/character-animation-pipeline/interactive/local/test-humanoid.glb 21120

$ /usr/local/bin/blender -b --factory-startup --python blender/fit_prepare.py -- --model local/test-humanoid.glb --skeleton vendor/bin/skeleton.glb --blend local/test-humanoid.blend --config local/test-humanoid.fit.json
FIT_PREPARE_START {"blend": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/interactive/local/test-humanoid.blend", "config": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/interactive/local/test-humanoid.fit.json", "interactive": false, "model": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/interactive/local/test-humanoid.glb", "skeleton": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/interactive/vendor/bin/skeleton.glb"}
FIT_NOTE normalized model bounds min=(-0.72, -0.2, 0.0) max=(0.72, 0.1, 1.75) (metres (glTF units))
FIT_NOTE auto_fit scale=1.075980 offset=(-0.0, 0.0457, -0.0125) (skeleton h=1.6264 model h=1.7500)
FIT_PREPARE_OK /home/drexer/Projects/cesar-alves/character-animation-pipeline/interactive/local/test-humanoid.blend /home/drexer/Projects/cesar-alves/character-animation-pipeline/interactive/local/test-humanoid.fit.json

$ python3 - <<'PY'
import json, math, os
p = "local/test-humanoid.fit.json"
c = json.load(open(p))
bones = c["bones"]
required = ["pelvis","spine_01","spine_02","spine_03","neck_01","head","upperarm_l","lowerarm_l","hand_l","upperarm_r","lowerarm_r","hand_r","thigh_l","calf_l","foot_l","thigh_r","calf_r","foot_r"]
finite = all(math.isfinite(v) for b in bones.values() for k in ("head","tail") for v in b[k]) and all(math.isfinite(b["roll"]) for b in bones.values())
print("schema_version:", c["schema_version"])
print("model:", c["model"], "profile:", c["profile"])
print("global:", c["global"])
print("bone count:", len(bones))
print("all M2M core bones present:", all(b in bones for b in required))
print("all numbers finite:", finite)
print("head tail (Y-up):", bones["head"]["tail"], "foot_l tail:", bones["foot_l"]["tail"])
print("blend exists:", os.path.isfile("local/test-humanoid.blend"), "bytes:", os.path.getsize("local/test-humanoid.blend"))
assert len(bones) == 66 and all(b in bones for b in required) and finite and os.path.isfile("local/test-humanoid.blend")
print("VERIFY_OK")
PY
schema_version: 1
model: local/test-humanoid.glb profile: m2m-human
global: {'uniform_scale': 1.07598, 'offset': [-0.0, -0.012497, -0.045742], 'yaw_degrees': 0.0}
bone count: 66
all M2M core bones present: True
all numbers finite: True
head tail (Y-up): [-0.0, 1.75, -0.026947] foot_l tail: [0.095762, 0.003858, 0.076058]
blend exists: True bytes: 121482
VERIFY_OK
```

The panel operators were also exercised headlessly by opening the saved
`.blend`, registering `fit_ui.py`, and calling export / mutate-a-bone /
reload / auto-fit-again. Notable lines:

```console
MODE_AT_START EDIT
EXPORT {'FINISHED'}
EXPORT_NOTES artist note BONES 66
RELOAD {'FINISHED'}
RESTORED (0.0, 0.03344999998807907, 1.6751680374145508)
AUTOFIT {'FINISHED'}
AUTOFIT_GLOBAL {'uniform_scale': 1.07598, 'offset': [-0.0, -0.012497, -0.045742], 'yaw_degrees': 0.0}
UI_TEST_DONE
```

`AUTOFIT_GLOBAL` returning the original scale confirms "Auto Fit Again"
resets to the pristine template rather than re-fitting an already-fitted rig.
