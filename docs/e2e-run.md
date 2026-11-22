# End-to-end run

Command: `python3 pipeline.py --job work/e2e_jobs.json --no-fetch --out out-e2e --vendor vendor/bin`

## Full output

```text
PIPELINE_BUILD e2e-hero
REPORT:meshopt_preload:{"ok": true, "path": "/home/drexer/Applications/blender-5.2.0-linux-x64/lib/libmeshoptimizer.so"}
REPORT:config:{"clips": ["walk", "idle-a"], "fit": null, "job": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/core/work/e2e-hero.job.json", "model": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/core/vendor/bin/model.glb", "name": "e2e-hero", "out": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/core/out-e2e", "vendor": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/core/vendor/bin"}
12:25:56 | INFO: Data are loaded, start creating Blender stuff
12:25:56 | INFO: Blender create Mesh node Mannequin.001
12:25:56 | INFO: glTF import finished in 0.07s
REPORT:model:{"bounds": {"xmax": 0.9666846990585327, "xmin": -0.966684103012085, "ymax": 0.16415409743785858, "ymin": -0.20544399321079254, "zmax": 1.8291784524917603, "zmin": -0.00038586315349675715}, "meshes": [{"name": "Mannequin", "vertices": 7399}], "old_armature_deleted": true}
12:25:56 | INFO: Data are loaded, start creating Blender stuff
12:25:56 | INFO: glTF import finished in 0.01s
REPORT:fit:{"auto_fit": {"after": {"xmax": 1.0651456117630005, "xmin": -1.0651450157165527, "ymax": 0.6241310834884644, "ymin": -0.6654210090637207, "zmax": 1.8291783332824707, "zmin": -0.00038586315349675715}, "before": {"xmax": 1.0651456117630005, "xmin": -1.0651450157165527, "ymax": 0.9834988117218018, "ymin": -0.3060533106327057, "zmax": 1.8295642137527466, "zmin": 0.0}, "model_height": 1.829564315645257, "skeleton_height": 1.7078462839126587, "uniform_scale": 1.0712698987485827}, "bone_bounds_after": {"xmax": 1.0651456117630005, "xmin": -1.0651450157165527, "ymax": 0.6241310834884644, "ymin": -0.6654210090637207, "zmax": 1.8291783332824707, "zmin": -0.00038586315349675715}, "bone_count": 66, "global": {}, "global_applied": false, "global_note": "informational: baked into per-bone head/tail; never re-applied", "mode": "auto", "overridden_bones": [], "overrides_applied": 0, "uniform_scale": 1.0712698987485827, "yaw_degrees": 0.0}
REPORT:skin:{"fallback_reason": null, "meshes": [{"mesh": "Mannequin", "unweighted_after": 0, "unweighted_before": 0, "vertex_groups": 66, "vertices": 7399}], "method": "armature_auto", "unweighted_total": 0, "vertices_limited_to_four_influences": 4531}
12:25:57 | INFO: Data are loaded, start creating Blender stuff
12:25:57 | INFO: glTF import finished in 0.07s
REPORT:deformation:{"clip": "walk", "samples": [{"frame_a": 0, "frame_b": 10, "max_displacement_m": 0.32015746197278294, "mesh": "Mannequin", "vertices": 7399}]}
REPORT:clip:{"action": "walk", "clip": "walk", "edits": {"keyframes_edited": 315, "root_translation_channels_zeroed": 6, "translation_channels_scaled": 192, "uniform_scale": 1.0712698987485827}, "file": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/core/vendor/bin/walk.glb", "frame_end": 39.0, "frame_start": 0.0, "score": {"animated_bones": 66, "paths": 198}, "slot": "OBArmature.001"}
12:25:57 | INFO: Data are loaded, start creating Blender stuff
12:25:57 | INFO: glTF import finished in 0.06s
REPORT:deformation:{"clip": "idle-a", "samples": [{"frame_a": 0, "frame_b": 10, "max_displacement_m": 0.030867512122741397, "mesh": "Mannequin", "vertices": 7399}]}
REPORT:clip:{"action": "idle-a", "clip": "idle-a", "edits": {"keyframes_edited": 201, "root_translation_channels_zeroed": 6, "translation_channels_scaled": 192, "uniform_scale": 1.0712698987485827}, "file": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/core/vendor/bin/idle-a.glb", "frame_end": 74.0, "frame_start": 0.0, "score": {"animated_bones": 66, "paths": 198}, "slot": "OBArmature.001"}
REPORT:nla:{"actions": ["walk", "idle-a"], "frame_end": 74, "frame_start": 0, "tracks": ["walk", "idle-a"]}
REPORT:mesh_validate:{"Mannequin": true}
INFO Draco is available, use library at /home/drexer/Applications/blender-5.2.0-linux-x64/5.2/scripts/addons_core/io_scene_gltf2/libbf_intern_draco_bridge.so
INFO MeshOptimizer is available, use library at /home/drexer/Applications/blender-5.2.0-linux-x64/5.2/scripts/addons_core/io_scene_gltf2/libbf_intern_meshopt_bridge.so
12:25:57 | INFO: Starting glTF 2.0 export
12:25:57 | INFO: Extracting primitive: Mannequin.001
12:25:57 | INFO: Primitives created: 1
12:25:58 | INFO: Finished glTF 2.0 export in 0.88655686378479 s

REPORT:export:{"animations": ["idle-a", "walk"], "bytes": 659000, "meshes": 1, "nodes": 68, "path": "/home/drexer/Projects/cesar-alves/character-animation-pipeline/core/out-e2e/e2e-hero.glb", "settings": {"export_anim_single_armature": false, "export_animation_mode": "ACTIONS", "export_animations": true, "export_apply": true, "export_def_bones": true, "export_format": "GLB", "export_frame_range": true, "export_nla_strips": false, "export_yup": true, "use_selection": true}, "skins": 1}
BATCH_OK /home/drexer/Projects/cesar-alves/character-animation-pipeline/core/out-e2e/e2e-hero.glb
Blender 5.2.0 LTS (hash fbe6228777e7 built 2026-07-14 01:32:04)
PIPELINE_VALIDATE e2e-hero OK
PIPELINE_OK 1 character(s)
```

## Validator report (`reports/e2e-hero.json`)

```json
{
  "ok": true,
  "checks": [
    {
      "name": "single_skin",
      "ok": true,
      "detail": "found 1 skin(s)"
    },
    {
      "name": "skinned_mesh",
      "ok": true,
      "detail": "1 skinned mesh primitive(s)"
    },
    {
      "name": "bones_present",
      "ok": true,
      "detail": "66 bone(s)"
    },
    {
      "name": "no_cameras_lights",
      "ok": true,
      "detail": "none found"
    },
    {
      "name": "clips_present",
      "ok": true,
      "detail": "2 requested clip(s) present"
    },
    {
      "name": "profile_bones",
      "ok": true,
      "detail": "no profile requested"
    },
    {
      "name": "root_translation_constant",
      "ok": true,
      "detail": "2 root translation channel(s) constant"
    }
  ],
  "bones": [
    "root",
    "pelvis",
    "spine_01",
    "spine_02",
    "spine_03",
    "clavicle_l",
    "upperarm_l",
    "lowerarm_l",
    "hand_l",
    "index_01_l",
    "index_02_l",
    "index_03_l",
    "index_04_leaf_l",
    "middle_01_l",
    "middle_02_l",
    "middle_03_l",
    "middle_04_leaf_l",
    "pinky_01_l",
    "pinky_02_l",
    "pinky_03_l",
    "pinky_04_leaf_l",
    "ring_01_l",
    "ring_02_l",
    "ring_03_l",
    "ring_04_leaf_l",
    "thumb_01_l",
    "thumb_02_l",
    "thumb_03_l",
    "thumb_04_leaf_l",
    "clavicle_r",
    "upperarm_r",
    "lowerarm_r",
    "hand_r",
    "index_01_r",
    "index_02_r",
    "index_03_r",
    "index_04_leaf_r",
    "middle_01_r",
    "middle_02_r",
    "middle_03_r",
    "middle_04_leaf_r",
    "pinky_01_r",
    "pinky_02_r",
    "pinky_03_r",
    "pinky_04_leaf_r",
    "ring_01_r",
    "ring_02_r",
    "ring_03_r",
    "ring_04_leaf_r",
    "thumb_01_r",
    "thumb_02_r",
    "thumb_03_r",
    "thumb_04_leaf_r",
    "neck_01",
    "head",
    "head_leaf",
    "thigh_l",
    "calf_l",
    "foot_l",
    "ball_l",
    "ball_leaf_l",
    "thigh_r",
    "calf_r",
    "foot_r",
    "ball_r",
    "ball_leaf_r"
  ],
  "clips": [
    "idle-a",
    "walk"
  ],
  "errors": []
}
```
