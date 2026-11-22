"""Blender 5.2 batch worker for the character animation pipeline.

Invoked headlessly by ``pipeline.py``::

    blender -b --factory-startup --python blender/batch.py -- \
        --job <tmp-job.json> --vendor <vendor/bin> --out <out>

The job JSON is the per-character contract::

    {"name": "hero", "model": "/abs/model.glb", "clips": ["idle-a", "walk"],
     "profile": "m2m-human", "fit": "/abs/config/fit/hero.json" or null}

The worker fits the pinned Mesh2Motion skeleton to the visual mesh, skins it,
transplants one action per clip (with root translation stripped) and exports a
single GLB containing every requested clip as a named animation. It prints
``BATCH_OK <output_glb>`` on success and ``BATCH_FAILED`` on any failure.
"""
from __future__ import annotations

import ctypes
import json
import os
import struct
import sys
import traceback

import bpy
from mathutils import Vector

# Sorted bone names from the P0 spike's ``verdict.bones`` (docs/spike-findings.md).
EXPECTED_BONES = sorted(
    [
        "ball_l", "ball_leaf_l", "ball_leaf_r", "ball_r",
        "calf_l", "calf_r", "clavicle_l", "clavicle_r",
        "foot_l", "foot_r", "hand_l", "hand_r", "head", "head_leaf",
        "index_01_l", "index_01_r", "index_02_l", "index_02_r",
        "index_03_l", "index_03_r", "index_04_leaf_l", "index_04_leaf_r",
        "lowerarm_l", "lowerarm_r",
        "middle_01_l", "middle_01_r", "middle_02_l", "middle_02_r",
        "middle_03_l", "middle_03_r", "middle_04_leaf_l", "middle_04_leaf_r",
        "neck_01", "pelvis",
        "pinky_01_l", "pinky_01_r", "pinky_02_l", "pinky_02_r",
        "pinky_03_l", "pinky_03_r", "pinky_04_leaf_l", "pinky_04_leaf_r",
        "ring_01_l", "ring_01_r", "ring_02_l", "ring_02_r",
        "ring_03_l", "ring_03_r", "ring_04_leaf_l", "ring_04_leaf_r",
        "root", "spine_01", "spine_02", "spine_03",
        "thumb_01_l", "thumb_01_r", "thumb_02_l", "thumb_02_r",
        "thumb_03_l", "thumb_03_r", "thumb_04_leaf_l", "thumb_04_leaf_r",
        "thigh_l", "thigh_r", "upperarm_l", "upperarm_r",
    ]
)

ROOT_TRANSLATION_PATHS = {
    'pose.bones["root"].location',
    'pose.bones["pelvis"].location',
    'pose.bones["Hips"].location',
}

EXPORT_SETTINGS = {
    "export_format": "GLB",
    "export_animations": True,
    "export_animation_mode": "ACTIONS",
    "export_nla_strips": False,
    "export_anim_single_armature": False,
    "export_def_bones": True,
    "export_yup": True,
    "use_selection": True,
    "export_apply": True,
    "export_frame_range": True,
}


def report(tag: str, payload: dict) -> None:
    print("REPORT:" + tag + ":" + json.dumps(payload, sort_keys=True), flush=True)


def ensure_meshopt_decoder() -> None:
    """Preload libmeshoptimizer.so the same way the P0 spike does.

    Blender 5.2's glTF Meshopt bridge links libmeshoptimizer.so without an
    rpath in some installs; a global ctypes preload makes CDLL(bridge) resolve.
    """
    binary = bpy.app.binary_path or sys.executable or ""
    binary = os.path.realpath(binary)
    root = os.path.dirname(binary)
    candidates = [
        os.path.join(root, "lib", "libmeshoptimizer.so"),
        os.path.join(os.path.dirname(root), "lib", "libmeshoptimizer.so"),
        "/home/drexer/Applications/blender-5.2.0-linux-x64/lib/libmeshoptimizer.so",
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
                report("meshopt_preload", {"path": path, "ok": True})
                return
            except Exception as exc:
                report("meshopt_preload", {"path": path, "ok": False, "error": repr(exc)})
    report("meshopt_preload", {"ok": False, "note": "no library found"})


def parse_args(argv: list[str]) -> dict:
    opts = {"job": "", "vendor": "vendor/bin", "out": "out"}
    args = argv[argv.index("--") + 1 :] if "--" in argv else []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg.startswith("--") and index + 1 < len(args):
            opts[arg[2:]] = args[index + 1]
            index += 2
        else:
            index += 1
    return opts


def object_names() -> set[str]:
    return set(obj.name for obj in bpy.data.objects)


def import_glb(path: str) -> tuple[list, list]:
    before = object_names()
    actions_before = set(action.name for action in bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=path)
    new_objects = [bpy.data.objects[name] for name in (object_names() - before)]
    new_actions = [
        bpy.data.actions[name]
        for name in (set(action.name for action in bpy.data.actions) - actions_before)
    ]
    return new_objects, new_actions


def remove_object(obj) -> None:
    if obj is None:
        return
    try:
        if obj.name not in bpy.data.objects:
            return
    except ReferenceError:
        return  # already removed (possibly as a side effect of unlinking)
    bpy.data.objects.remove(obj, do_unlink=True)


def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        remove_object(obj)


def select_only(obj) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def is_bone_shape(obj) -> bool:
    for armature in bpy.data.objects:
        if armature.type != "ARMATURE" or not armature.pose:
            continue
        for pose_bone in armature.pose.bones:
            if pose_bone.custom_shape == obj:
                return True
    return False


def world_bounds(objects: list) -> dict:
    points = []
    for obj in objects:
        matrix = obj.matrix_world
        for vertex in obj.data.vertices:
            points.append(matrix @ vertex.co)
    if not points:
        raise RuntimeError("no vertices available to compute model bounds")
    return {
        "xmin": min(point.x for point in points),
        "xmax": max(point.x for point in points),
        "ymin": min(point.y for point in points),
        "ymax": max(point.y for point in points),
        "zmin": min(point.z for point in points),
        "zmax": max(point.z for point in points),
    }


def arm_world_bounds(arm) -> dict:
    points = []
    matrix = arm.matrix_world
    for bone in arm.data.bones:
        points.append(matrix @ bone.head_local)
        points.append(matrix @ bone.tail_local)
    if not points:
        raise RuntimeError("armature has no bones")
    return {
        "xmin": min(point.x for point in points),
        "xmax": max(point.x for point in points),
        "ymin": min(point.y for point in points),
        "ymax": max(point.y for point in points),
        "zmin": min(point.z for point in points),
        "zmax": max(point.z for point in points),
    }


def world_vertices(obj, frame: int) -> list[tuple[float, float, float]]:
    """Evaluated world-space vertex positions at a frame (spike technique)."""
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        matrix = evaluated.matrix_world
        return [tuple(matrix @ vertex.co) for vertex in mesh.vertices]
    finally:
        evaluated.to_mesh_clear()


def max_displacement(first, second) -> float | None:
    if len(first) != len(second) or not first:
        return None
    total = 0.0
    for a, b in zip(first, second):
        squared = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2
        total = max(total, squared)
    return total ** 0.5


def sample_deformation(arm, meshes: list, frame_a: int, frame_b: int) -> list:
    results = []
    for mesh in meshes:
        before = world_vertices(mesh, frame_a)
        after = world_vertices(mesh, frame_b)
        results.append(
            {
                "mesh": mesh.name,
                "vertices": len(before),
                "frame_a": frame_a,
                "frame_b": frame_b,
                "max_displacement_m": max_displacement(before, after),
            }
        )
    return results


def bone_depth(bone) -> int:
    depth = 0
    parent = bone.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    return depth


def cfg_to_blender(values) -> Vector:
    """Y-up metres (glTF/fit config) -> Blender Z-up: (x, y, z) -> (x, -z, y)."""
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError(f"fit coordinate must be [x, y, z], got {values!r}")
    x, y, z = (float(component) for component in values)
    return Vector((x, -z, y))


def auto_fit(arm, model_bounds: dict) -> dict:
    """Scale/translate the M2M skeleton to the model bounds and bake it."""
    local_points = []
    for bone in arm.data.bones:
        local_points.append(bone.head_local)
        local_points.append(bone.tail_local)
    z_min = min(point.z for point in local_points)
    z_max = max(point.z for point in local_points)
    skeleton_height = z_max - z_min
    if skeleton_height <= 0.0:
        raise RuntimeError("skeleton has zero height")
    model_height = model_bounds["zmax"] - model_bounds["zmin"]
    if model_height <= 0.0:
        raise RuntimeError("model has zero height")

    scale = model_height / skeleton_height
    arm.scale = (scale, scale, scale)
    bpy.context.view_layer.update()
    before = arm_world_bounds(arm)

    delta = Vector(
        (
            (model_bounds["xmin"] + model_bounds["xmax"]) / 2.0
            - (before["xmin"] + before["xmax"]) / 2.0,
            (model_bounds["ymin"] + model_bounds["ymax"]) / 2.0
            - (before["ymin"] + before["ymax"]) / 2.0,
            model_bounds["zmin"] - before["zmin"],
        )
    )
    arm.location = arm.location + delta
    bpy.context.view_layer.update()

    select_only(arm)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()
    after = arm_world_bounds(arm)
    return {
        "uniform_scale": scale,
        "skeleton_height": skeleton_height,
        "model_height": model_height,
        "before": before,
        "after": after,
    }


def apply_fit_overrides(arm, config: dict) -> list:
    """Apply per-bone head/tail/roll overrides in EDIT mode.

    Config coordinates are Y-up metres and are converted to Blender Z-up.
    ``roll`` is a Blender EditBone roll in radians and is copied verbatim.
    ``global`` values are informational only: the interactive fitter already
    baked them into the per-bone head/tail values, so they are never re-applied.
    """
    bones_config = config.get("bones") or {}
    if not isinstance(bones_config, dict):
        raise RuntimeError("fit config 'bones' must be an object")
    depths = {bone.name: bone_depth(bone) for bone in arm.data.bones}
    ordered = sorted(bones_config, key=lambda name: (depths.get(name, 999), name))

    select_only(arm)
    applied = []
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for name in ordered:
            edit_bone = arm.data.edit_bones.get(name)
            if edit_bone is None:
                raise RuntimeError(f"fit config overrides unknown bone {name!r}")
            spec = bones_config[name]
            if not isinstance(spec, dict):
                raise RuntimeError(f"fit config for bone {name!r} must be an object")
            detail = {"bone": name}
            if "head" in spec:
                edit_bone.head = cfg_to_blender(spec["head"])
                detail["head"] = spec["head"]
            if "tail" in spec:
                edit_bone.tail = cfg_to_blender(spec["tail"])
                detail["tail"] = spec["tail"]
            if "roll" in spec:
                edit_bone.roll = float(spec["roll"])  # radians, verbatim
                detail["roll_radians"] = float(spec["roll"])
            applied.append(detail)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()
    return applied


def skin_meshes(arm, meshes: list) -> dict:
    """Auto-weight via Blender, with a proximity-weight fallback."""
    bpy.ops.object.select_all(action="DESELECT")
    for mesh in meshes:
        mesh.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm

    method = "armature_auto"
    fallback_reason = None
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    except Exception as exc:
        method = "proximity"
        fallback_reason = f"ARMATURE_AUTO raised {exc!r}"

    def unweighted_for(mesh) -> list[int]:
        return [
            vertex.index
            for vertex in mesh.data.vertices
            if sum(group.weight for group in vertex.groups) <= 1e-8
        ]

    bad_before = {mesh.name: unweighted_for(mesh) for mesh in meshes}
    modifiers_ok = all(
        any(mod.type == "ARMATURE" and mod.object == arm for mod in mesh.modifiers)
        for mesh in meshes
    )
    if method != "proximity" and (not modifiers_ok or any(bad_before.values())):
        method = "proximity"
        fallback_reason = "ARMATURE_AUTO left unweighted vertices or no armature modifier"

    if method == "proximity":
        apply_proximity_weights(arm, meshes)

    influences_limited = sum(limit_influences(mesh) for mesh in meshes)
    bad_after = {mesh.name: unweighted_for(mesh) for mesh in meshes}
    remaining = sum(len(value) for value in bad_after.values())
    if remaining:
        raise RuntimeError(f"{remaining} vertex/vertices have no non-zero weight")

    details = []
    for mesh in meshes:
        details.append(
            {
                "mesh": mesh.name,
                "vertices": len(mesh.data.vertices),
                "unweighted_before": len(bad_before.get(mesh.name, [])),
                "unweighted_after": len(bad_after[mesh.name]),
                "vertex_groups": len(mesh.vertex_groups),
            }
        )
    return {
        "method": method,
        "fallback_reason": fallback_reason,
        "meshes": details,
        "unweighted_total": remaining,
        "vertices_limited_to_four_influences": influences_limited,
    }


def point_segment_distance(point: Vector, head: Vector, tail: Vector) -> float:
    segment = tail - head
    length_sq = segment.length_squared
    if length_sq <= 1e-12:
        return (point - head).length
    factor = max(0.0, min(1.0, (point - head).dot(segment) / length_sq))
    return (point - (head + segment * factor)).length


def apply_proximity_weights(arm, meshes: list, maximum: int = 4) -> None:
    """Assign up to four inverse-distance bone weights per vertex."""
    arm_matrix = arm.matrix_world
    segments = [
        (arm_matrix @ bone.head_local, arm_matrix @ bone.tail_local)
        for bone in arm.data.bones
    ]
    if not segments:
        raise RuntimeError("cannot proximity-weight to an empty skeleton")
    for mesh in meshes:
        mesh.vertex_groups.clear()
        groups = [mesh.vertex_groups.new(name=bone.name) for bone in arm.data.bones]
        mesh_matrix = mesh.matrix_world
        for vertex in mesh.data.vertices:
            point = mesh_matrix @ vertex.co
            nearest = sorted(
                (point_segment_distance(point, head, tail), index)
                for index, (head, tail) in enumerate(segments)
            )[:maximum]
            weights = [1.0 / (distance + 1e-6) ** 2 for distance, _ in nearest]
            total = sum(weights)
            if total <= 0.0:
                raise RuntimeError(f"invalid proximity weights for {mesh.name}:{vertex.index}")
            for (_, index), weight in zip(nearest, weights):
                groups[index].add([vertex.index], weight / total, "REPLACE")
        for existing in list(mesh.modifiers):
            if existing.type == "ARMATURE":
                mesh.modifiers.remove(existing)
        modifier = mesh.modifiers.new(name="ProximityArmature", type="ARMATURE")
        modifier.object = arm


def limit_influences(mesh, maximum: int = 4) -> int:
    """Keep the strongest four weights per vertex (glTF's maximum)."""
    limited = 0
    for vertex in mesh.data.vertices:
        nonzero = [
            (group.group, group.weight)
            for group in vertex.groups
            if group.weight > 1e-8
        ]
        if len(nonzero) <= maximum:
            continue
        strongest = sorted(nonzero, key=lambda item: -item[1])[:maximum]
        kept = {index for index, _ in strongest}
        for index, _ in nonzero:
            if index not in kept:
                mesh.vertex_groups[index].remove([vertex.index])
        total = sum(weight for _, weight in strongest)
        for index, weight in strongest:
            mesh.vertex_groups[index].add([vertex.index], weight / total, "REPLACE")
        limited += 1
    return limited


def iter_fcurves(action):
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                for fcurve in channelbag.fcurves:
                    yield fcurve


def action_frame_range(action) -> tuple[float, float]:
    try:
        start, end = action.frame_range
        return float(start), float(end)
    except Exception:
        return (0.0, 0.0)


def action_score(action, bone_names: set[str]) -> tuple[int, int]:
    paths = set()
    for fcurve in iter_fcurves(action):
        paths.add(fcurve.data_path)
    animated_bones = set()
    for path in paths:
        if path.startswith('pose.bones["'):
            animated_bones.add(path.split('"')[1])
    return (len(animated_bones & bone_names), len(paths))


def choose_action(actions: list, bone_names: set[str]):
    if not actions:
        raise RuntimeError("clip import produced no actions")
    best = max(actions, key=lambda action: action_score(action, bone_names))
    score = action_score(best, bone_names)
    if score[0] == 0:
        raise RuntimeError("no imported action animates a bone on our skeleton")
    return best, score


def modify_action(action, uniform_scale: float) -> dict:
    """Zero root/pelvis translation and scale remaining translations."""
    zeroed = 0
    scaled = 0
    keyframes = 0
    for fcurve in iter_fcurves(action):
        is_root = fcurve.data_path in ROOT_TRANSLATION_PATHS
        is_location = fcurve.data_path.endswith("].location")
        if not (is_root or is_location):
            continue
        if is_root:
            for keyframe in fcurve.keyframe_points:
                keyframe.co.y = 0.0
                keyframe.handle_left.y = 0.0
                keyframe.handle_right.y = 0.0
                keyframes += 1
            zeroed += 1
        elif uniform_scale != 1.0:
            for keyframe in fcurve.keyframe_points:
                keyframe.co.y *= uniform_scale
                keyframe.handle_left.y *= uniform_scale
                keyframe.handle_right.y *= uniform_scale
                keyframes += 1
            scaled += 1
        else:
            continue
        fcurve.update()
    return {
        "root_translation_channels_zeroed": zeroed,
        "translation_channels_scaled": scaled,
        "keyframes_edited": keyframes,
        "uniform_scale": uniform_scale,
    }


def parse_glb_animations(path: str) -> dict:
    """Parse the GLB header/JSON chunk directly (no third-party library)."""
    with open(path, "rb") as handle:
        data = handle.read()
    if len(data) < 20:
        raise RuntimeError("exported GLB is too short")
    magic, version, total = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2 or total != len(data):
        raise RuntimeError("exported GLB has an invalid header")
    gltf = None
    offset = 12
    while offset + 8 <= len(data):
        length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        if offset + length > len(data):
            raise RuntimeError("exported GLB has a truncated chunk")
        if chunk_type == 0x4E4F534A:
            gltf = json.loads(data[offset : offset + length].decode("utf-8").rstrip(" \x00"))
        offset += length
    if gltf is None:
        raise RuntimeError("exported GLB has no JSON chunk")
    return {
        "animations": [item.get("name", "") for item in gltf.get("animations", [])],
        "skins": len(gltf.get("skins", [])),
        "nodes": len(gltf.get("nodes", [])),
        "meshes": len(gltf.get("meshes", [])),
    }


def main() -> None:
    ensure_meshopt_decoder()
    opts = parse_args(sys.argv)
    if not opts.get("job"):
        raise RuntimeError("--job is required")
    job_path = os.path.abspath(opts["job"])
    vendor = os.path.abspath(opts["vendor"])
    out = os.path.abspath(opts["out"])

    with open(job_path, "r", encoding="utf-8") as handle:
        job = json.load(handle)
    name = job["name"]
    model_path = os.path.abspath(job["model"])
    clips = list(job["clips"])
    fit_path = job.get("fit")
    if fit_path:
        fit_path = os.path.abspath(fit_path)

    report(
        "config",
        {
            "name": name,
            "job": job_path,
            "vendor": vendor,
            "out": out,
            "model": model_path,
            "clips": clips,
            "fit": fit_path,
        },
    )

    if not os.path.isfile(model_path) or os.path.getsize(model_path) == 0:
        raise RuntimeError(f"missing or empty model: {model_path}")
    skeleton_path = os.path.join(vendor, "skeleton.glb")
    if not os.path.isfile(skeleton_path) or os.path.getsize(skeleton_path) == 0:
        raise RuntimeError(f"missing or empty skeleton: {skeleton_path}")
    clip_paths = []
    for clip in clips:
        file_name = clip if clip.lower().endswith(".glb") else clip + ".glb"
        path = os.path.join(vendor, file_name)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise RuntimeError(f"missing or empty clip: {path}")
        clip_paths.append((clip, path))
    os.makedirs(out, exist_ok=True)
    clear_scene()

    # --- Import the model, discard its armature, keep the visual mesh(es) ---
    model_objects, _ = import_glb(model_path)
    old_arms = [obj for obj in model_objects if obj.type == "ARMATURE"]
    old_arm = old_arms[0] if old_arms else None
    if old_arm:
        visual = [
            obj
            for obj in model_objects
            if obj.type == "MESH"
            and any(mod.type == "ARMATURE" and mod.object == old_arm for mod in obj.modifiers)
        ]
    else:
        visual = []
    if not visual:
        visual = [
            obj
            for obj in model_objects
            if obj.type == "MESH" and len(obj.data.vertices) > 0 and not is_bone_shape(obj)
        ]
    if not visual:
        raise RuntimeError("model GLB has no visual mesh")

    for mesh in visual:
        world_matrix = mesh.matrix_world.copy()
        for modifier in list(mesh.modifiers):
            if modifier.type == "ARMATURE":
                mesh.modifiers.remove(modifier)
        mesh.vertex_groups.clear()
        mesh.parent = None
        mesh.matrix_world = world_matrix
    for obj in model_objects:
        if obj not in visual:
            remove_object(obj)
    if old_arm is not None:
        remove_object(old_arm)

    model_bounds = world_bounds(visual)
    report(
        "model",
        {
            "meshes": [
                {"name": mesh.name, "vertices": len(mesh.data.vertices)} for mesh in visual
            ],
            "bounds": model_bounds,
            "old_armature_deleted": old_arm is not None,
        },
    )

    # --- Import + validate the pinned M2M skeleton ---
    skeleton_objects, _ = import_glb(skeleton_path)
    armatures = [obj for obj in skeleton_objects if obj.type == "ARMATURE"]
    if not armatures:
        raise RuntimeError("skeleton.glb has no armature")
    arm = max(armatures, key=lambda obj: len(obj.data.bones))
    actual_bones = sorted(bone.name for bone in arm.data.bones)
    if actual_bones != EXPECTED_BONES:
        raise RuntimeError(
            "skeleton bone names differ from the spike's 66 M2M bones; "
            f"missing={sorted(set(EXPECTED_BONES) - set(actual_bones))} "
            f"extra={sorted(set(actual_bones) - set(EXPECTED_BONES))}"
        )
    for obj in skeleton_objects:
        if obj != arm:
            remove_object(obj)
    for bone in arm.data.bones:
        bone.use_deform = True  # export_def_bones=True must keep all 66 joints

    # --- Fit: auto-fit baseline, then optional config overrides ---
    auto_info = auto_fit(arm, model_bounds)
    config = None
    if fit_path:
        if not os.path.isfile(fit_path):
            raise RuntimeError(f"missing fit config: {fit_path}")
        with open(fit_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        if not isinstance(config, dict):
            raise RuntimeError("fit config root must be a JSON object")
    global_config = (config or {}).get("global") or {}
    if not isinstance(global_config, dict):
        raise RuntimeError("fit config 'global' must be an object")
    overrides = apply_fit_overrides(arm, config) if config else []
    uniform_scale = float(global_config.get("uniform_scale", auto_info["uniform_scale"]))
    if uniform_scale <= 0.0:
        raise RuntimeError("fit uniform_scale must be positive")
    report(
        "fit",
        {
            "mode": "config" if config else "auto",
            "uniform_scale": uniform_scale,
            "auto_fit": auto_info,
            "global": global_config,
            "global_applied": False,
            "global_note": "informational: baked into per-bone head/tail; never re-applied",
            "yaw_degrees": float(global_config.get("yaw_degrees", 0.0)),
            "overrides_applied": len(overrides),
            "overridden_bones": overrides,
            "bone_count": len(arm.data.bones),
            "bone_bounds_after": arm_world_bounds(arm),
        },
    )

    # --- Skin ---
    skin_info = skin_meshes(arm, visual)
    report("skin", skin_info)

    # --- Import clips, copy + transplant actions, strip root motion ---
    bone_names = set(actual_bones)
    exported_actions = []
    clip_details = []
    for clip, clip_path in clip_paths:
        clip_objects, clip_actions = import_glb(clip_path)
        action, score = choose_action(clip_actions, bone_names)
        copied = action.copy()
        copied.name = clip
        edits = modify_action(copied, uniform_scale)
        start, end = action_frame_range(copied)
        animation_data = arm.animation_data_create()
        animation_data.action = copied
        if animation_data.action_slot is None and copied.slots:
            animation_data.action_slot = copied.slots[0]

        # Sample this clip alone: earlier NLA strips are muted while measuring.
        for existing_track in animation_data.nla_tracks:
            existing_track.mute = True
        frame_a = int(round(start))
        frame_b = max(frame_a + 1, min(frame_a + 10, int(round(end))))
        deformation = sample_deformation(arm, visual, frame_a, frame_b)
        for existing_track in animation_data.nla_tracks:
            existing_track.mute = False
        report("deformation", {"clip": clip, "samples": deformation})

        track = animation_data.nla_tracks.new()
        track.name = clip
        strip_start = int(round(start))
        strip = track.strips.new(clip, strip_start, copied)
        if strip.action_slot is None and copied.slots:
            strip.action_slot = copied.slots[0]

        for obj in clip_objects:
            remove_object(obj)
        if action.name in bpy.data.actions and action.users == 0:
            bpy.data.actions.remove(action)

        exported_actions.append(copied)
        clip_details.append(
            {
                "clip": clip,
                "file": clip_path,
                "action": copied.name,
                "score": {"animated_bones": score[0], "paths": score[1]},
                "frame_start": start,
                "frame_end": end,
                "slot": getattr(strip.action_slot, "identifier", None),
                "edits": edits,
            }
        )
        report("clip", clip_details[-1])

    # The combine-and-export reference binds every action through an NLA track
    # and leaves no active action on the armature. Clear the last assigned
    # active action so the ACTIONS exporter emits exactly one animation per clip
    # instead of duplicating the last one.
    if arm.animation_data:
        arm.animation_data.action = None  # Blender clears the slot by itself
    scene = bpy.context.scene
    scene.frame_start = int(min(action_frame_range(action)[0] for action in exported_actions))
    scene.frame_end = int(max(action_frame_range(action)[1] for action in exported_actions))
    if scene.frame_end <= scene.frame_start:
        scene.frame_end = scene.frame_start + 1
    report(
        "nla",
        {
            "tracks": [track.name for track in arm.animation_data.nla_tracks],
            "frame_start": scene.frame_start,
            "frame_end": scene.frame_end,
            "actions": [action.name for action in exported_actions],
        },
    )

    # --- Export every action in one GLB ---
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    for mesh in visual:
        mesh.select_set(True)
    bpy.context.view_layer.objects.active = arm
    mesh_fixes = {mesh.name: bool(mesh.data.validate(clean_customdata=False)) for mesh in visual}
    report("mesh_validate", mesh_fixes)
    output_glb = os.path.join(out, name + ".glb")
    bpy.ops.export_scene.gltf(filepath=output_glb, **EXPORT_SETTINGS)

    contents = parse_glb_animations(output_glb)
    missing = [clip for clip, _ in clip_paths if clip not in contents["animations"]]
    if missing:
        raise RuntimeError(
            f"exported GLB is missing clip(s) {missing}; found {contents['animations']}"
        )
    report(
        "export",
        {
            "path": output_glb,
            "bytes": os.path.getsize(output_glb),
            "animations": contents["animations"],
            "skins": contents["skins"],
            "nodes": contents["nodes"],
            "meshes": contents["meshes"],
            "settings": EXPORT_SETTINGS,
        },
    )
    print("BATCH_OK " + output_glb, flush=True)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        print("BATCH_FAILED", flush=True)
        sys.exit(1)
