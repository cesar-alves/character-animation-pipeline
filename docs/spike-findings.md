# P0 technical spike — direct Mesh2Motion clip transplant in Blender 5.2

## Verdict

**PROVEN.** A Mesh2Motion (M2M) animation clip's imported Blender 5.x `Action` can be
assigned directly to the model armature — with no retargeting, no bone remapping and
no NLA/bake workaround — and a skinned mesh bound to that armature deforms correctly.

With no action assigned, max world-space vertex displacement between frame 0 and
frame 10 is `0.0 m`. After direct assignment it is `0.38014192666806784 m`
(threshold `0.001 m`). The exported GLB re-imports with the `Walk` action still
assigned and still deforms (`0.3801438466976374 m`).

## Environment and exact commands

- Blender: `/usr/local/bin/blender` → `5.2.0 LTS` (hash `fbe6228777e7`, build 2026-07-14).
- Worktree: `/home/drexer/Projects/cesar-alves/character-animation-pipeline/spike-p0`
  (branch `spike-p0`).
- Script: `blender/spike.py`.

Asset download (all succeeded with `curl -fsSL`):

```sh
mkdir -p vendor/bin out docs blender
curl -fsSL -o vendor/bin/skeleton.glb https://raw.githubusercontent.com/Mesh2Motion/mesh2motion-app/main/static/assets/human/skeleton.glb
curl -fsSL -o vendor/bin/model.glb    https://raw.githubusercontent.com/Mesh2Motion/mesh2motion-app/main/static/assets/human/model.glb
curl -fsSL -o vendor/bin/walk.glb     https://raw.githubusercontent.com/Mesh2Motion/mesh2motion-app/main/static/assets/human/animations/walk.glb
```

`walk.glb` exists (no 404 fallback needed). Size and sha256:

| File | Bytes | sha256 |
| --- | --- | --- |
| `vendor/bin/model.glb` | 531504 | `bce15f56f0ca4daf4e085337b2412116ab18d3165cb51ea672d1cb9f1194b37f` |
| `vendor/bin/skeleton.glb` | 18688 | `1784d9aa20e24dee3233d97a8ac2f2e0d72cc74f0692b44fcded87d2d3e33f9c` |
| `vendor/bin/walk.glb` | 62692 | `c961d6dd99856f597ef6f4d986260b5636fb55e8132ff6d0a3765cd8a34aeef1` |
| `out/spike.glb` (result) | 595704 | `02be3c6b2fe9363393adff839e67e42768e62e0043608b8aa8d74b1c3f6355cb` |

Successful run (exit code `0`, last line `SPIKE_OK`):

```sh
/usr/local/bin/blender -b --factory-startup --python blender/spike.py -- --vendor vendor/bin --out out
```

## What was found in the files

**Armatures after importing `model.glb` then `walk.glb`:**

- `Armature` (from `model.glb`): 66 bones, no action initially.
- `Armature.001` (from `walk.glb`): 66 bones, action `Walk` assigned.
- Bone-name sets are **identical** (66/66, zero bones missing on either side).

Bone names (66, sorted):

`ball_l`, `ball_leaf_l`, `ball_leaf_r`, `ball_r`, `calf_l`, `calf_r`, `clavicle_l`,
`clavicle_r`, `foot_l`, `foot_r`, `hand_l`, `hand_r`, `head`, `head_leaf`,
`index_01_l`, `index_01_r`, `index_02_l`, `index_02_r`, `index_03_l`, `index_03_r`,
`index_04_leaf_l`, `index_04_leaf_r`, `lowerarm_l`, `lowerarm_r`, `middle_01_l`,
`middle_01_r`, `middle_02_l`, `middle_02_r`, `middle_03_l`, `middle_03_r`,
`middle_04_leaf_l`, `middle_04_leaf_r`, `neck_01`, `pelvis`, `pinky_01_l`,
`pinky_01_r`, `pinky_02_l`, `pinky_02_r`, `pinky_03_l`, `pinky_03_r`,
`pinky_04_leaf_l`, `pinky_04_leaf_r`, `ring_01_l`, `ring_01_r`, `ring_02_l`,
`ring_02_r`, `ring_03_l`, `ring_03_r`, `ring_04_leaf_l`, `ring_04_leaf_r`, `root`,
`spine_01`, `spine_02`, `spine_03`, `thumb_01_l`, `thumb_01_r`, `thumb_02_l`,
`thumb_02_r`, `thumb_03_l`, `thumb_03_r`, `thumb_04_leaf_l`, `thumb_04_leaf_r`,
`thigh_l`, `thigh_r`, `upperarm_l`, `upperarm_r`.

**Clips found:** exactly one action, `Walk`, frame range `0.0–39.0`, 660 f-curves,
3889 keyframe points, one slot `OBArmature.001` (`OBJECT` target). F-curves are
`pose.bones["<bone>"].location / rotation_quaternion / scale` — no object-level or
custom-property channels. (M2M's `skeleton.glb` imports no actions.)

**Skinned meshes:** `Mannequin` (7399 vertices) with one `ARMATURE` modifier targeting
`Armature`. Non-skinned helper meshes `Cube` and `Icosphere` are ignored for export.

**Clip-only objects** (`Icosphere.001`, `Armature.001`) are removed from the scene
before sampling/export so only the model armature and its mesh are measured.

## Displacement measurements

World-space positions sampled from the evaluated depsgraph at frames 0 and 10,
max over all 7399 vertices:

| State | Max displacement | Result |
| --- | --- | --- |
| No action assigned (control) | `0.0 m` | static, as expected |
| Direct `action` + `action_slot` assignment | `0.38014192666806784 m` | **deformation proven** |
| Re-import of `out/spike.glb` | `0.3801438466976374 m` | action survives export/import |

The `0.001 m` threshold is exceeded by ~380x.

## Attempt log

1. **Run 1 — blocker: Meshopt decoder.** Importing `walk.glb` failed with
   `RuntimeError: Error: Failed to load Meshopt decoder library: libmeshoptimizer.so:
   cannot open shared object file`. The clip uses `EXT_meshopt_compression`; Blender's
   bridge `libbf_intern_meshopt_bridge.so` has an unresolved `libmeshoptimizer.so`.
   Fixed in `blender/spike.py::ensure_meshopt_decoder()` by preloading
   `<Blender root>/lib/libmeshoptimizer.so` with `ctypes.CDLL(..., RTLD_GLOBAL)` before
   any glTF import. Also noted: Blender returned exit code 0 despite the uncaught Python
   exception, so the script now wraps `main()` and forces `SPIKE_FAILED` + `sys.exit(1)`.
2. **Run 2 — blocker: Blender 5.x slot clearing.** All three attempts (direct action,
   NLA strip with explicit slot, `bpy.ops.nla.bake`) aborted in `clear_animation()` with
   `RuntimeError: Error: Cannot set slot without an assigned Action.` because the code
   set `ad.action_slot = None` while `ad.action` was already `None`. Fixed by assigning
   only `ad.action = None` (Blender clears the slot itself), then setting the action and
   `ad.action_slot` afterwards.
3. **Run 3 / final — success on the first attempt.** Direct assignment deformed the
   mesh by `0.38014192666806784 m`; the NLA and bake fallbacks in the script were never
   reached. No retargeting was required.

## Export / re-import verification

Export used:

```python
bpy.ops.export_scene.gltf(
    filepath=out/spike.glb,
    export_format='GLB',
    export_animations=True,
    export_animation_mode='ACTIONS',
    use_selection=True,
    export_yup=True,
)
```

with only the model armature and `Mannequin` selected.

Parsing the GLB JSON chunk directly confirms: one animation named `Walk`, one skin,
one mesh named `Mannequin.001`, 66 bone nodes, no required extensions. Re-importing it
produces an armature with the `Walk.001` action already assigned (660 f-curves, frame
0–39) and a skinned mesh that still deforms by `0.3801438466976374 m` between frames 0
and 10.

## Caveats for the implementation team

- **Slot binding is mandatory and must be done in this order** (Blender 5.x):
  `arm.animation_data.action = action`, then
  `arm.animation_data.action_slot = action.slots[0]` if the slot is still `None`.
  The slot is on `animation_data`, not on the armature object. Do **not** set
  `action_slot = None` when no action is assigned — it raises.
- **Slot identifier names do not need to match.** The clip's slot is named
  `OBArmature.001` (after the clip armature object) but binds cleanly to the model
  armature named `Armature`. No object renaming or slot remapping is needed.
- **The assumption holds only when bone-name sets match.** Here both skeletons have
  exactly the same 66 names, including `root`, `clavicle_*`, `ball_*` and `*_leaf`
  bones beyond the deform list in `RigConfig.ts`. The pipeline must enforce name-set
  equality (or an explicit name map) when fitting to a new mesh; this spike does not
  prove anything about differently named or missing bones.
- **Meshopt decoder environment issue is real.** Any headless Blender 5.2 import of M2M
  animation GLBs in this environment needs the preload (or `LD_LIBRARY_PATH` pointing
  at Blender's `lib/`). Otherwise the importer fails before actions are available.
- **Measure deformation via the evaluated depsgraph** (`obj.evaluated_get(depsgraph)`
  and `eval_obj.to_mesh()`), not `obj.data.vertices`, which are undeformed.
- **Harmless re-import artifacts:** the importer creates an `Icosphere` custom bone
  shape on the exported armature; it is generated at import time, not present in the
  GLB (GLB contains only `Mannequin.001`). The mesh vertex count changes 7399 → 7400
  on round-trip due to glTF seam splitting; this does not affect deformation.

## Full stdout of the successful run

```text
REPORT:meshopt_preload:{"ok": true, "path": "/home/drexer/Applications/blender-5.2.0-linux-x64/lib/libmeshoptimizer.so"}
REPORT:config:{"clip": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/spike-p0/vendor/bin/walk.glb", "model": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/spike-p0/vendor/bin/model.glb", "out": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/spike-p0/out", "vendor": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/spike-p0/vendor/bin"}
11:46:57 | INFO: Data are loaded, start creating Blender stuff
11:46:57 | INFO: Blender create Mesh node Mannequin.001
11:46:57 | INFO: glTF import finished in 0.07s
11:46:57 | INFO: Data are loaded, start creating Blender stuff
11:46:57 | INFO: glTF import finished in 0.05s
REPORT:import_provenance:{"clip_actions": ["Walk"], "clip_objects": ["Icosphere.001", "Armature.001"], "model_actions": [], "model_objects": ["Icosphere", "Mannequin", "Armature"]}
REPORT:scene_after_import:{"actions": [{"fcurves": 660, "frame_end": 39.0, "frame_start": 0.0, "keyframe_points": 3889, "name": "Walk", "sample_paths": ["pose.bones[\"ball_l\"].location", "pose.bones[\"ball_l\"].rotation_quaternion", "pose.bones[\"ball_l\"].scale", "pose.bones[\"ball_leaf_l\"].location", "pose.bones[\"ball_leaf_l\"].rotation_quaternion", "pose.bones[\"ball_leaf_l\"].scale", "pose.bones[\"ball_leaf_r\"].location", "pose.bones[\"ball_leaf_r\"].rotation_quaternion"], "slots": [{"identifier": "OBArmature.001", "target_id_type": "OBJECT"}]}], "armatures": [{"action": null, "bone_count": 66, "bones": ["ball_l", "ball_leaf_l", "ball_leaf_r", "ball_r", "calf_l", "calf_r", "clavicle_l", "clavicle_r", "foot_l", "foot_r", "hand_l", "hand_r", "head", "head_leaf", "index_01_l", "index_01_r", "index_02_l", "index_02_r", "index_03_l", "index_03_r", "index_04_leaf_l", "index_04_leaf_r", "lowerarm_l", "lowerarm_r", "middle_01_l", "middle_01_r", "middle_02_l", "middle_02_r", "middle_03_l", "middle_03_r", "middle_04_leaf_l", "middle_04_leaf_r", "neck_01", "pelvis", "pinky_01_l", "pinky_01_r", "pinky_02_l", "pinky_02_r", "pinky_03_l", "pinky_03_r", "pinky_04_leaf_l", "pinky_04_leaf_r", "ring_01_l", "ring_01_r", "ring_02_l", "ring_02_r", "ring_03_l", "ring_03_r", "ring_04_leaf_l", "ring_04_leaf_r", "root", "spine_01", "spine_02", "spine_03", "thigh_l", "thigh_r", "thumb_01_l", "thumb_01_r", "thumb_02_l", "thumb_02_r", "thumb_03_l", "thumb_03_r", "thumb_04_leaf_l", "thumb_04_leaf_r", "upperarm_l", "upperarm_r"], "name": "Armature"}, {"action": "Walk", "bone_count": 66, "bones": ["ball_l", "ball_leaf_l", "ball_leaf_r", "ball_r", "calf_l", "calf_r", "clavicle_l", "clavicle_r", "foot_l", "foot_r", "hand_l", "hand_r", "head", "head_leaf", "index_01_l", "index_01_r", "index_02_l", "index_02_r", "index_03_l", "index_03_r", "index_04_leaf_l", "index_04_leaf_r", "lowerarm_l", "lowerarm_r", "middle_01_l", "middle_01_r", "middle_02_l", "middle_02_r", "middle_03_l", "middle_03_r", "middle_04_leaf_l", "middle_04_leaf_r", "neck_01", "pelvis", "pinky_01_l", "pinky_01_r", "pinky_02_l", "pinky_02_r", "pinky_03_l", "pinky_03_r", "pinky_04_leaf_l", "pinky_04_leaf_r", "ring_01_l", "ring_01_r", "ring_02_l", "ring_02_r", "ring_03_l", "ring_03_r", "ring_04_leaf_l", "ring_04_leaf_r", "root", "spine_01", "spine_02", "spine_03", "thigh_l", "thigh_r", "thumb_01_l", "thumb_01_r", "thumb_02_l", "thumb_02_r", "thumb_03_l", "thumb_03_r", "thumb_04_leaf_l", "thumb_04_leaf_r", "upperarm_l", "upperarm_r"], "name": "Armature.001"}], "meshes": [{"armature_modifiers": [], "name": "Cube", "vertices": 8}, {"armature_modifiers": ["Armature"], "name": "Mannequin", "vertices": 7399}, {"armature_modifiers": [], "name": "Icosphere", "vertices": 42}, {"armature_modifiers": [], "name": "Icosphere.001", "vertices": 42}]}
REPORT:selection:{"bone_sets_equal": true, "clip_armature": "Armature.001", "clip_bone_count": 66, "missing_from_clip": [], "missing_from_model": [], "model_armature": "Armature", "model_bone_count": 66, "skinned_meshes": ["Mannequin"]}
REPORT:chosen_action:{"fcurves": 660, "frame_end": 39.0, "frame_start": 0.0, "keyframe_points": 3889, "name": "Walk", "sample_paths": ["pose.bones[\"ball_l\"].location", "pose.bones[\"ball_l\"].rotation_quaternion", "pose.bones[\"ball_l\"].scale", "pose.bones[\"ball_leaf_l\"].location", "pose.bones[\"ball_leaf_l\"].rotation_quaternion", "pose.bones[\"ball_leaf_l\"].scale", "pose.bones[\"ball_leaf_r\"].location", "pose.bones[\"ball_leaf_r\"].rotation_quaternion"], "slots": [{"identifier": "OBArmature.001", "target_id_type": "OBJECT"}]}
REPORT:sample_frames:{"action_end": 39.0, "action_start": 0.0, "f0": 0, "f1": 10}
REPORT:deformation:[{"frame_a": 0, "frame_b": 10, "max_displacement_m": 0.0, "mesh": "Mannequin", "vertices": 7399}]
REPORT:baseline_no_action:[{"frame_a": 0, "frame_b": 10, "max_displacement_m": 0.0, "mesh": "Mannequin", "vertices": 7399}]
REPORT:deformation:[{"frame_a": 0, "frame_b": 10, "max_displacement_m": 0.38014192666806784, "mesh": "Mannequin", "vertices": 7399}]
REPORT:attempts:[{"info": {"action": "Walk", "slot": "OBArmature.001"}, "kind": "direct_action", "max_displacement_m": 0.38014192666806784}]
REPORT:deformation:[{"frame_a": 0, "frame_b": 10, "max_displacement_m": 0.38014192666806784, "mesh": "Mannequin", "vertices": 7399}]
INFO Draco is available, use library at /home/drexer/Applications/blender-5.2.0-linux-x64/5.2/scripts/addons_core/io_scene_gltf2/libbf_intern_draco_bridge.so
INFO MeshOptimizer is available, use library at /home/drexer/Applications/blender-5.2.0-linux-x64/5.2/scripts/addons_core/io_scene_gltf2/libbf_intern_meshopt_bridge.so
11:46:57 | INFO: Starting glTF 2.0 export
11:46:57 | INFO: Extracting primitive: Mannequin.001
11:46:57 | INFO: Primitives created: 1
11:46:58 | INFO: Finished glTF 2.0 export in 0.3766593933105469 s

REPORT:export:{"bytes": 595704, "max_displacement_m": 0.38014192666806784, "method": "direct_action", "path": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/spike-p0/out/spike.glb"}
11:46:58 | INFO: Data are loaded, start creating Blender stuff
11:46:58 | INFO: Blender create Mesh node Mannequin.001
11:46:58 | INFO: glTF import finished in 0.10s
REPORT:deformation:[{"frame_a": 0, "frame_b": 10, "max_displacement_m": 0.0, "mesh": "Icosphere.001", "vertices": 42}, {"frame_a": 0, "frame_b": 10, "max_displacement_m": 0.3801438466976374, "mesh": "Mannequin.001", "vertices": 7400}]
REPORT:reimport_verification:{"actions": [{"fcurves": 660, "frame_end": 39.0, "frame_start": 0.0, "keyframe_points": 4626, "name": "Walk.001", "sample_paths": ["pose.bones[\"ball_l\"].location", "pose.bones[\"ball_l\"].rotation_quaternion", "pose.bones[\"ball_l\"].scale", "pose.bones[\"ball_leaf_l\"].location", "pose.bones[\"ball_leaf_l\"].rotation_quaternion", "pose.bones[\"ball_leaf_l\"].scale", "pose.bones[\"ball_leaf_r\"].location", "pose.bones[\"ball_leaf_r\"].rotation_quaternion"], "slots": [{"identifier": "OBArmature.001", "target_id_type": "OBJECT"}]}], "armatures": ["Armature.001"], "meshes": [{"name": "Icosphere.001", "vertices": 42}, {"name": "Mannequin.001", "vertices": 7400}], "objects": ["Icosphere.001", "Mannequin.001", "Armature.001"], "reimport_action_assigned": true, "reimport_deformation": [{"frame_a": 0, "frame_b": 10, "max_displacement_m": 0.0, "mesh": "Icosphere.001", "vertices": 42}, {"frame_a": 0, "frame_b": 10, "max_displacement_m": 0.3801438466976374, "mesh": "Mannequin.001", "vertices": 7400}]}
REPORT:verdict:{"baseline_no_action": [{"frame_a": 0, "frame_b": 10, "max_displacement_m": 0.0, "mesh": "Mannequin", "vertices": 7399}], "bone_count": 66, "bone_sets_equal": true, "bones": ["ball_l", "ball_leaf_l", "ball_leaf_r", "ball_r", "calf_l", "calf_r", "clavicle_l", "clavicle_r", "foot_l", "foot_r", "hand_l", "hand_r", "head", "head_leaf", "index_01_l", "index_01_r", "index_02_l", "index_02_r", "index_03_l", "index_03_r", "index_04_leaf_l", "index_04_leaf_r", "lowerarm_l", "lowerarm_r", "middle_01_l", "middle_01_r", "middle_02_l", "middle_02_r", "middle_03_l", "middle_03_r", "middle_04_leaf_l", "middle_04_leaf_r", "neck_01", "pelvis", "pinky_01_l", "pinky_01_r", "pinky_02_l", "pinky_02_r", "pinky_03_l", "pinky_03_r", "pinky_04_leaf_l", "pinky_04_leaf_r", "ring_01_l", "ring_01_r", "ring_02_l", "ring_02_r", "ring_03_l", "ring_03_r", "ring_04_leaf_l", "ring_04_leaf_r", "root", "spine_01", "spine_02", "spine_03", "thigh_l", "thigh_r", "thumb_01_l", "thumb_01_r", "thumb_02_l", "thumb_02_r", "thumb_03_l", "thumb_03_r", "thumb_04_leaf_l", "thumb_04_leaf_r", "upperarm_l", "upperarm_r"], "deformation_detected": true, "literal_frame_sample": [{"frame_a": 0, "frame_b": 10, "max_displacement_m": 0.38014192666806784, "mesh": "Mannequin", "vertices": 7399}], "max_displacement_m": 0.38014192666806784, "method": "direct_action", "threshold_m": 0.001}
SPIKE_OK
Blender 5.2.0 LTS (hash fbe6228777e7 built 2026-07-14 01:32:04)
```
