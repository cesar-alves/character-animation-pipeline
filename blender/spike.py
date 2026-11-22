"""P0 spike: prove/disprove direct transplant of a Mesh2Motion clip action onto
the model armature in Blender 5.2, with no general retargeting.

Run:
  blender -b --factory-startup --python blender/spike.py -- \
      --vendor vendor/bin --out out
"""

import ctypes
import json
import os
import sys
import traceback

import bpy


def ensure_meshopt_decoder():
    """Blender 5.2's glTF Meshopt bridge links libmeshoptimizer.so without an
    rpath in some installs. Preload it globally so ctypes.CDLL(bridge) resolves.
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
            except Exception as e:
                report("meshopt_preload", {"path": path, "ok": False, "error": repr(e)})
    report("meshopt_preload", {"ok": False, "note": "no library found"})


def report(tag, payload):
    print("REPORT:" + tag + ":" + json.dumps(payload, sort_keys=True), flush=True)


def parse_args(argv):
    opts = {"vendor": "vendor/bin", "out": "out", "clip": "walk.glb"}
    if "--" in argv:
        args = argv[argv.index("--") + 1:]
    else:
        args = []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--") and i + 1 < len(args):
            opts[a[2:]] = args[i + 1]
            i += 2
        else:
            i += 1
    return opts


def object_names():
    return set(o.name for o in bpy.data.objects)


def import_glb(path):
    before = object_names()
    actions_before = set(a.name for a in bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=path)
    new_objs = [bpy.data.objects[n] for n in (object_names() - before)]
    new_actions = [bpy.data.actions[n] for n in (set(a.name for a in bpy.data.actions) - actions_before)]
    return new_objs, new_actions


def bone_names(arm_obj):
    return set(b.name for b in arm_obj.data.bones)


def action_frame_range(action):
    try:
        r = action.frame_range
        return (float(r[0]), float(r[1]))
    except Exception:
        return (0.0, 0.0)


def action_info(action):
    curves = 0
    keys = 0
    paths = set()
    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                for fc in cb.fcurves:
                    curves += 1
                    paths.add(fc.data_path)
                    keys += len(fc.keyframe_points)
    slots = []
    for s in action.slots:
        slots.append({
            "identifier": getattr(s, "identifier", ""),
            "target_id_type": getattr(s, "target_id_type", ""),
        })
    start, end = action_frame_range(action)
    return {
        "name": action.name,
        "frame_start": start,
        "frame_end": end,
        "fcurves": curves,
        "keyframe_points": keys,
        "slots": slots,
        "sample_paths": sorted(paths)[:8],
    }


def describe_scene(label):
    armatures = []
    meshes = []
    for obj in bpy.context.scene.objects:
        if obj.type == 'ARMATURE':
            armatures.append({
                "name": obj.name,
                "bone_count": len(obj.data.bones),
                "bones": sorted(b.name for b in obj.data.bones),
                "action": obj.animation_data.action.name if (obj.animation_data and obj.animation_data.action) else None,
            })
        elif obj.type == 'MESH':
            arm_mods = [m.object.name for m in obj.modifiers if m.type == 'ARMATURE' and m.object]
            meshes.append({
                "name": obj.name,
                "vertices": len(obj.data.vertices),
                "armature_modifiers": arm_mods,
            })
    report("scene_" + label, {
        "armatures": armatures,
        "meshes": meshes,
        "actions": [action_info(a) for a in bpy.data.actions],
    })
    return armatures, meshes


def skinned_meshes_for(arm_obj):
    out = []
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        if any(m.type == 'ARMATURE' and m.object == arm_obj for m in obj.modifiers):
            out.append(obj)
    return out


def world_vertices(obj, frame):
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(depsgraph)
    mesh = ev.to_mesh()
    try:
        mw = ev.matrix_world
        return [tuple(mw @ v.co) for v in mesh.vertices]
    finally:
        ev.to_mesh_clear()


def max_displacement(a, b):
    if len(a) != len(b) or not a:
        return None
    total = 0.0
    for va, vb in zip(a, b):
        d = (vb[0] - va[0]) ** 2 + (vb[1] - va[1]) ** 2 + (vb[2] - va[2]) ** 2
        total = max(total, d)
    return total ** 0.5


def sample_deformation(arm_obj, mesh_objs, f0, f1):
    results = []
    for mesh in mesh_objs:
        v0 = world_vertices(mesh, f0)
        v1 = world_vertices(mesh, f1)
        d = max_displacement(v0, v1)
        results.append({
            "mesh": mesh.name,
            "vertices": len(v0),
            "frame_a": f0,
            "frame_b": f1,
            "max_displacement_m": d,
        })
    report("deformation", results)
    return results


def clear_animation(arm_obj):
    ad = arm_obj.animation_data
    if ad is None:
        return
    for track in list(ad.nla_tracks):
        ad.nla_tracks.remove(track)
    # In Blender 5.x assigning action=None clears the slot automatically;
    # explicitly setting action_slot=None while no action is assigned raises.
    ad.action = None


def direct_assign(arm_obj, action):
    ad = arm_obj.animation_data_create()
    clear_animation(arm_obj)
    ad.action = action
    if ad.action_slot is None and action.slots:
        ad.action_slot = action.slots[0]
    return {
        "action": ad.action.name if ad.action else None,
        "slot": getattr(ad.action_slot, "identifier", None) if ad.action_slot else None,
    }


def nla_assign(arm_obj, action):
    ad = arm_obj.animation_data_create()
    clear_animation(arm_obj)
    start, end = action_frame_range(action)
    track = ad.nla_tracks.new()
    track.name = "spike_" + action.name
    strip = track.strips.new(action.name, int(round(start)), action)
    if strip.action_slot is None and action.slots:
        strip.action_slot = action.slots[0]
    return {
        "track": track.name,
        "strip": strip.name,
        "slot": getattr(strip.action_slot, "identifier", None) if strip.action_slot else None,
        "start": int(round(start)),
        "end": int(round(end)),
    }


def bake_assign(arm_obj, action):
    start, end = action_frame_range(action)
    f0 = int(round(start))
    f1 = max(f0 + 1, int(round(end)))
    ad = arm_obj.animation_data_create()
    clear_animation(arm_obj)
    ad.action = action
    if ad.action_slot is None and action.slots:
        ad.action_slot = action.slots[0]
    bpy.ops.object.select_all(action='DESELECT')
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.nla.bake(
        frame_start=f0, frame_end=f1, step=1,
        only_selected=False, visual_keying=True,
        clear_constraints=False, clear_custom_props=False,
        bake_types={'POSE'},
    )
    baked = arm_obj.animation_data.action if arm_obj.animation_data else None
    return {
        "baked_action": baked.name if baked else None,
        "frame_start": f0,
        "frame_end": f1,
    }


def main():
    ensure_meshopt_decoder()
    opts = parse_args(sys.argv)
    vendor = os.path.abspath(opts["vendor"])
    out = os.path.abspath(opts["out"])
    os.makedirs(out, exist_ok=True)

    model_path = os.path.join(vendor, "model.glb")
    clip_path = os.path.join(vendor, opts.get("clip", "walk.glb"))
    report("config", {"vendor": vendor, "out": out, "model": model_path, "clip": clip_path})

    for p in (model_path, clip_path):
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            raise RuntimeError("missing or empty asset: " + p)

    # --- Import model then clip, tracking provenance -------------------------
    model_objs, model_actions = import_glb(model_path)
    clip_objs, clip_actions = import_glb(clip_path)
    report("import_provenance", {
        "model_objects": [o.name for o in model_objs],
        "model_actions": [a.name for a in model_actions],
        "clip_objects": [o.name for o in clip_objs],
        "clip_actions": [a.name for a in clip_actions],
    })

    scene_arms, scene_meshes = describe_scene("after_import")

    model_arms = [o for o in model_objs if o.type == 'ARMATURE']
    clip_arms = [o for o in clip_objs if o.type == 'ARMATURE']
    if not model_arms:
        raise RuntimeError("no armature in model.glb")
    model_arm = model_arms[0]
    clip_arm = clip_arms[0] if clip_arms else None
    bone_sets_equal = bone_names(model_arm) == bone_names(clip_arm) if clip_arm else None
    model_bone_list = sorted(bone_names(model_arm))

    mesh_objs = skinned_meshes_for(model_arm)
    report("selection", {
        "model_armature": model_arm.name,
        "clip_armature": clip_arm.name if clip_arm else None,
        "model_bone_count": len(bone_names(model_arm)),
        "clip_bone_count": len(bone_names(clip_arm)) if clip_arm else 0,
        "bone_sets_equal": bone_sets_equal,
        "missing_from_model": sorted(bone_names(clip_arm) - bone_names(model_arm)) if clip_arm else [],
        "missing_from_clip": sorted(bone_names(model_arm) - bone_names(clip_arm)) if clip_arm else [],
        "skinned_meshes": [m.name for m in mesh_objs],
    })

    # Pick an action: prefer actions imported with the clip that actually
    # animate pose bones present on the model armature.
    candidates = clip_actions or list(bpy.data.actions)
    model_bones = bone_names(model_arm)
    def score_action(a):
        paths = set()
        for layer in a.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    for fc in cb.fcurves:
                        paths.add(fc.data_path)
        bones = set()
        for p in paths:
            if p.startswith('pose.bones["'):
                bones.add(p.split('"')[1])
        return (len(bones & model_bones), len(paths))
    candidates = sorted(candidates, key=score_action, reverse=True)
    if not candidates:
        raise RuntimeError("no actions imported")
    action = candidates[0]
    report("chosen_action", action_info(action))

    start, end = action_frame_range(action)
    f0 = int(round(start))
    f1 = int(round(start + 10))
    if f1 <= f0:
        f1 = f0 + 1
    if end > f0 and f1 > end:
        f1 = max(f0 + 1, int(round(end)))
    report("sample_frames", {"action_start": start, "action_end": end, "f0": f0, "f1": f1})

    # Remove the clip's own armature/mesh objects from the scene so they cannot
    # contribute to displacement or export; we only need its action.
    for o in clip_objs:
        if o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)
    mesh_objs = skinned_meshes_for(model_arm)
    if not mesh_objs:
        raise RuntimeError("no skinned mesh bound to model armature")

    # Control: with no action assigned the mesh must be static at both frames.
    baseline = sample_deformation(model_arm, mesh_objs, f0, f1)
    report("baseline_no_action", baseline)

    attempts = []
    best_disp = -1.0
    best_kind = None
    ok = False

    # --- Attempt 1: direct Action assignment --------------------------------
    try:
        info = direct_assign(model_arm, action)
        res = sample_deformation(model_arm, mesh_objs, f0, f1)
        d = max((r["max_displacement_m"] or 0.0) for r in res)
        attempts.append({"kind": "direct_action", "info": info, "max_displacement_m": d})
        if d > 0.001:
            ok = True
            best_disp, best_kind = d, "direct_action"
    except Exception as e:
        attempts.append({"kind": "direct_action", "error": repr(e), "trace": traceback.format_exc()})

    # --- Attempt 2: NLA strip with explicit slot -----------------------------
    if not ok:
        try:
            info = nla_assign(model_arm, action)
            res = sample_deformation(model_arm, mesh_objs, f0, f1)
            d = max((r["max_displacement_m"] or 0.0) for r in res)
            attempts.append({"kind": "nla_strip", "info": info, "max_displacement_m": d})
            if d > 0.001:
                ok = True
                best_disp, best_kind = d, "nla_strip"
        except Exception as e:
            attempts.append({"kind": "nla_strip", "error": repr(e), "trace": traceback.format_exc()})

    # --- Attempt 3: bake to fresh pose Action --------------------------------
    if not ok:
        try:
            info = bake_assign(model_arm, action)
            res = sample_deformation(model_arm, mesh_objs, f0, f1)
            d = max((r["max_displacement_m"] or 0.0) for r in res)
            attempts.append({"kind": "nla_bake", "info": info, "max_displacement_m": d})
            if d > 0.001:
                ok = True
                best_disp, best_kind = d, "nla_bake"
        except Exception as e:
            attempts.append({"kind": "nla_bake", "error": repr(e), "trace": traceback.format_exc()})

    report("attempts", attempts)

    # Also sample the literal frames requested in the spike brief (0 and 10).
    literal = sample_deformation(model_arm, mesh_objs, 0, 10)

    # --- Export --------------------------------------------------------------
    bpy.ops.object.select_all(action='DESELECT')
    model_arm.select_set(True)
    for m in mesh_objs:
        m.select_set(True)
    bpy.context.view_layer.objects.active = model_arm
    export_path = os.path.join(out, "spike.glb")
    bpy.ops.export_scene.gltf(
        filepath=export_path,
        export_format='GLB',
        export_animations=True,
        export_animation_mode='ACTIONS',
        use_selection=True,
        export_yup=True,
    )
    report("export", {
        "path": export_path,
        "bytes": os.path.getsize(export_path) if os.path.exists(export_path) else 0,
        "method": best_kind,
        "max_displacement_m": best_disp,
    })

    # --- Verify re-import ----------------------------------------------------
    verify = {}
    try:
        before = object_names()
        before_actions = set(a.name for a in bpy.data.actions)
        bpy.ops.import_scene.gltf(filepath=export_path)
        new_objs = [bpy.data.objects[n] for n in (object_names() - before)]
        new_actions = [bpy.data.actions[n] for n in (set(a.name for a in bpy.data.actions) - before_actions)]
        new_arms = [o for o in new_objs if o.type == 'ARMATURE']
        new_meshes = [o for o in new_objs if o.type == 'MESH']
        verify = {
            "objects": [o.name for o in new_objs],
            "armatures": [o.name for o in new_arms],
            "actions": [action_info(a) for a in new_actions],
            "meshes": [{"name": m.name, "vertices": len(m.data.vertices)} for m in new_meshes],
        }
        if new_arms and new_meshes and new_actions:
            target_actions = [a for a in new_actions if action_frame_range(a)[1] > action_frame_range(a)[0]]
            if target_actions:
                a2 = target_actions[0]
                s2, e2 = action_frame_range(a2)
                q0 = int(round(s2))
                q1 = max(q0 + 1, min(int(round(s2 + 10)), int(round(e2))))
                arm2 = new_arms[0]
                # If import already assigned the action, just sample. Otherwise assign it.
                if not (arm2.animation_data and arm2.animation_data.action):
                    ad2 = arm2.animation_data_create()
                    ad2.action = a2
                    if ad2.action_slot is None and a2.slots:
                        ad2.action_slot = a2.slots[0]
                verify["reimport_deformation"] = sample_deformation(arm2, new_meshes, q0, q1)
                verify["reimport_action_assigned"] = bool(
                    arm2.animation_data and arm2.animation_data.action
                )
    except Exception as e:
        verify = {"error": repr(e), "trace": traceback.format_exc()}
    report("reimport_verification", verify)

    verdict = {
        "deformation_detected": ok,
        "method": best_kind,
        "max_displacement_m": best_disp,
        "threshold_m": 0.001,
        "bone_sets_equal": bone_sets_equal,
        "bone_count": len(model_bone_list),
        "bones": model_bone_list,
        "baseline_no_action": baseline,
        "literal_frame_sample": literal,
    }
    report("verdict", verdict)

    if ok:
        print("SPIKE_OK", flush=True)
        sys.exit(0)
    else:
        print("SPIKE_FAILED", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        print("SPIKE_FAILED", flush=True)
        sys.exit(1)
