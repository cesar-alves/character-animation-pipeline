# Input and output formats

## Supported in v1

- **Input:** binary glTF (`.glb`) static humanoid meshes.
- **Output:** binary glTF (`.glb`) with one skinned mesh, one skeleton and all
  selected animation clips as named actions.

## Planned (not in v1)

| Format | Work required |
|---|---|
| FBX models | `bpy.ops.import_scene.fbx`, unit/axis normalization, material-to-PBR conversion, embedded/external texture discovery and repacking into the GLB. |
| OBJ models | `bpy.ops.wm.obj_import`, no skeleton/material semantics; same texture repacking. |
| BVH animations | Sample joint rotations, remap to the M2M bone chains; `python-scripts/bvh-retarget-scripts.py` in `mesh2motion-assets` is the reference. |
