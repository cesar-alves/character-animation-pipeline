"""Headless preparation step for the interactive Mesh2Motion skeleton fit.

Invocation (from the repository root):

    blender -b --factory-startup --python blender/fit_prepare.py -- \
        --model models/foo.glb \
        --skeleton vendor/bin/skeleton.glb \
        --blend work/fit/foo.blend \
        --config config/fit/foo.json \
        [--interactive]

It imports the target model and the CC0 M2M human skeleton, normalizes the
model (metres / Blender Z-up / feet at Z=0 -- which is metres / Y-up / feet at
0 in the exported glTF), auto-fits the skeleton to the model, writes the full
fit config (every bone), and saves a .blend containing the model and the
fitted armature.  The config is the hand-off contract; see docs/interactive-
fit.md for the schema.

Coordinates stored in the JSON are in *final normalized model space*: glTF
convention (Y up), metres, feet at Y=0.  Blender works in Z-up, so the helper
``to_model_space`` applies the standard Blender -> glTF rotation
``(x, y, z) -> (x, z, -y)``.  That rotation is proper (det +1), so bone roll
(in radians, as Blender stores it) is unchanged by the conversion and is
copied verbatim -- preserving roll is essential for later action transplant.
"""

import json
import math
import os
import sys
import traceback

import bpy
from mathutils import Matrix, Vector


M2M_SIGNATURE = ("pelvis", "head", "foot_l", "foot_r")
HEAD_CHAIN = ("pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head")
FOOT_CHAINS = ("foot_l", "foot_r")
SCHEMA_VERSION = 1
PROFILE = "m2m-human"
HUMAN_HEIGHT_M = 1.7  # only used as a fallback when the GLB is not in metres


# --------------------------------------------------------------------------- #
# small utilities
# --------------------------------------------------------------------------- #
def log(msg):
    print(msg, flush=True)


def parse_args(argv):
    """Parse everything after the Blender '--' separator."""
    opts = {}
    if "--" in argv:
        args = argv[argv.index("--") + 1:]
    else:
        args = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--interactive":
            opts["interactive"] = True
            i += 1
        elif a.startswith("--") and i + 1 < len(args):
            opts[a[2:]] = args[i + 1]
            i += 2
        else:
            i += 1
    return opts


def to_model_space(v):
    """Blender Z-up -> final glTF-style model space (Y up, feet at 0)."""
    return [round(float(v.x), 6), round(float(v.z), 6), round(-float(v.y), 6)]


def from_model_space(seq):
    """Inverse of to_model_space."""
    x, y, z = (float(c) for c in seq)
    return Vector((x, -z, y))


def bounds(points):
    points = list(points)
    if not points:
        raise RuntimeError("cannot compute bounds of an empty point set")
    return (
        Vector((min(p[0] for p in points), min(p[1] for p in points), min(p[2] for p in points))),
        Vector((max(p[0] for p in points), max(p[1] for p in points), max(p[2] for p in points))),
    )


def object_names():
    return set(o.name for o in bpy.data.objects)


def import_glb(path):
    """Import a GLB and return only the objects it created."""
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError("missing or empty asset: " + path)
    before = object_names()
    bpy.ops.import_scene.gltf(filepath=path)
    return [bpy.data.objects[n] for n in (object_names() - before)]


def make_active(obj):
    # object.select_all only polls in Object Mode; the .blend is deliberately
    # saved in Edit Mode, so leave it first when another object is being edited.
    active = bpy.context.object
    if active and active.mode != "OBJECT":
        if active == obj:
            return
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def enter_edit(arm):
    make_active(arm)
    if bpy.context.object.mode != "EDIT":
        bpy.ops.object.mode_set(mode="EDIT")


def leave_edit():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def find_skeleton_armature(objects):
    candidates = [o for o in objects if o.type == "ARMATURE"]
    if not candidates:
        raise RuntimeError("skeleton GLB contains no armature")
    def score(arm):
        names = set(b.name for b in arm.data.bones)
        return (sum(n in names for n in M2M_SIGNATURE), len(names))
    return max(candidates, key=score)


def descendants(bones, root_name):
    """All bones in the subtree rooted at root_name (including itself)."""
    out = []
    stack = [root_name]
    seen = set()
    while stack:
        name = stack.pop()
        if name in seen or name not in bones:
            continue
        seen.add(name)
        out.append(bones[name])
        stack.extend(c.name for c in bones[name].children)
    return out


# --------------------------------------------------------------------------- #
# normalization + auto fit
# --------------------------------------------------------------------------- #
def normalize_model(meshes):
    """Bake object transforms, drop old armatures, put feet at Z=0.

    glTF defines one unit == one metre, so after baking the importer's node
    transforms the model is already in metres.  As a safety net, models whose
    height is clearly not human-scale are uniformly rescaled to ~1.7 m.
    """
    for obj in meshes:
        # Bake world transform into the mesh data (also consumes any glTF
        # node scale).  Static meshes are what this interactive step expects.
        obj.data.transform(obj.matrix_world.copy())
        obj.matrix_world = Matrix.Identity(4)
        for mod in list(obj.modifiers):
            if mod.type == "ARMATURE":
                obj.modifiers.remove(mod)

    pts = [tuple(obj.matrix_world @ v.co) for obj in meshes for v in obj.data.vertices]
    mn, mx = bounds(pts)
    height = mx.z - mn.z
    scale_note = "metres (glTF units)"
    if height > 3.0 or height < 0.2:
        factor = HUMAN_HEIGHT_M / height if height > 1e-9 else 1.0
        log("FIT_NOTE model height %.4f looks non-human; rescaling by %.6f to %.2f m"
            % (height, factor, HUMAN_HEIGHT_M))
        for obj in meshes:
            for v in obj.data.vertices:
                v.co *= factor
        for obj in meshes:
            obj.data.update()
        pts = [tuple(v.co) for obj in meshes for v in obj.data.vertices]
        mn, mx = bounds(pts)
        scale_note = "rescaled x%.6f to %.2f m" % (factor, HUMAN_HEIGHT_M)

    # Feet to Z=0.  X/Y stay where the artist authored them; the skeleton is
    # centered on the model below.
    dz = -mn.z
    for obj in meshes:
        for v in obj.data.vertices:
            v.co.z += dz
        obj.data.update()
    pts = [tuple(v.co) for obj in meshes for v in obj.data.vertices]
    mn, mx = bounds(pts)
    log("FIT_NOTE normalized model bounds min=%s max=%s (%s)"
        % (tuple(round(c, 4) for c in mn), tuple(round(c, 4) for c in mx), scale_note))
    return mn, mx


def skeleton_vertical_refs(arm):
    """Return (top_z, bottom_z) using the pelvis->head chain and the feet."""
    bones = {b.name: b for b in arm.data.bones}
    chain = [bones[n] for n in HEAD_CHAIN if n in bones]
    if not chain:
        raise RuntimeError("skeleton has no pelvis/head chain")
    top = max(max(b.head_local.z, b.tail_local.z) for b in chain)

    foot_bones = []
    for name in FOOT_CHAINS:
        foot_bones.extend(descendants(bones, name))
    if not foot_bones:
        foot_bones = [b for b in bones.values() if b.name != "root"]
    bottom = min(min(b.head_local.z, b.tail_local.z) for b in foot_bones)
    if not top > bottom:
        raise RuntimeError("degenerate skeleton height")
    return top, bottom


def auto_fit(arm, mn, mx):
    """Compute (uniform_scale, offset_blender) that fit the skeleton to model."""
    top, bottom = skeleton_vertical_refs(arm)
    skel_h = top - bottom
    model_h = mx.z - mn.z
    scale = model_h / skel_h if skel_h > 1e-9 else 1.0

    # Centers use body bones only: 'root' is a long forward-pointing control
    # bone in the M2M rig and would skew the X/Y bounding box.
    bones = {b.name: b for b in arm.data.bones}
    body = [b for b in bones.values() if b.name != "root"]
    pts = [tuple(v) for b in body for v in (b.head_local, b.tail_local)]
    smn, smx = bounds(pts)
    offset = Vector((
        (mn.x + mx.x) * 0.5 - (smn.x + smx.x) * 0.5 * scale,
        (mn.y + mx.y) * 0.5 - (smn.y + smx.y) * 0.5 * scale,
        mn.z - bottom * scale,
    ))
    log("FIT_NOTE auto_fit scale=%.6f offset=%s (skeleton h=%.4f model h=%.4f)"
        % (scale, tuple(round(c, 4) for c in offset), skel_h, model_h))
    return scale, offset


REST_POSE_KEY = "m2m_rest_bones_json"


def store_rest_pose(arm):
    """Keep the pristine M2M rest pose in the .blend so 'Auto Fit Again' can
    truly reset after manual edits (the config contract must stay unchanged)."""
    enter_edit(arm)
    rest = {}
    for eb in arm.data.edit_bones:
        rest[eb.name] = {
            "head": [float(c) for c in eb.head],
            "tail": [float(c) for c in eb.tail],
            "roll": float(eb.roll),
        }
    leave_edit()
    arm[REST_POSE_KEY] = json.dumps(rest, sort_keys=True)
    return rest


def apply_auto_fit(arm, scale, offset):
    """Bake scale+offset into edit bones, leaving the armature object at identity."""
    enter_edit(arm)
    ebs = list(arm.data.edit_bones)
    connected = {eb.name: eb.use_connect for eb in ebs}
    for eb in ebs:
        eb.use_connect = False
    for eb in ebs:
        eb.head = Vector(eb.head) * scale + offset
        eb.tail = Vector(eb.tail) * scale + offset
        # Uniform scale + translation preserve roll; leave eb.roll as-is.
    for eb in ebs:
        eb.use_connect = connected[eb.name]
    leave_edit()
    arm.location = (0.0, 0.0, 0.0)
    arm.rotation_euler = (0.0, 0.0, 0.0)
    arm.scale = (1.0, 1.0, 1.0)
    arm.show_in_front = True
    arm.data.display_type = "STICK"


# --------------------------------------------------------------------------- #
# config I/O
# --------------------------------------------------------------------------- #
def bones_to_config(arm):
    """Read every edit bone in final model space, preserving roll."""
    enter_edit(arm)
    out = {}
    mw = arm.matrix_world.copy()
    for eb in arm.data.edit_bones:
        out[eb.name] = {
            "head": to_model_space(mw @ eb.head),
            "tail": to_model_space(mw @ eb.tail),
            "roll": round(float(eb.roll), 6),
        }
    leave_edit()
    return out


def write_config(path, model, scale, offset, bones):
    cfg = {
        "schema_version": SCHEMA_VERSION,
        "model": model.replace("\\", "/"),
        "profile": PROFILE,
        "global": {
            "uniform_scale": round(float(scale), 6),
            "offset": to_model_space(offset),
            "yaw_degrees": 0.0,
        },
        "bones": bones,
        "notes": "",
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return cfg


def configure_viewports(arm, model_height):
    """Make the saved .blend open in a useful front view for bone editing."""
    try:
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type != "VIEW_3D":
                    continue
                for space in area.spaces:
                    if space.type != "VIEW_3D":
                        continue
                    rv3d = space.region_3d
                    rv3d.view_perspective = "ORTHO"
                    rv3d.view_rotation = (mathutils_euler_front()).to_quaternion()
                    rv3d.view_distance = max(2.0, model_height * 1.6)
                    rv3d.view_location = (0.0, 0.0, model_height * 0.5)
    except Exception as exc:  # viewport state is cosmetic; never fail the fit
        log("FIT_NOTE could not configure viewport: " + repr(exc))


def mathutils_euler_front():
    from mathutils import Euler
    return Euler((math.pi / 2.0, 0.0, 0.0), "XYZ")


def register_embedded_ui(blend_path, config_path):
    """When --interactive is set, register the bundled fit_ui.py panel logic.

    fit_prepare itself is headless; the actual GUI window is opened by
    tools/fit.py, which reopens this .blend with fit_ui.py.  Registering here
    also makes the panel available if the artist opens the .blend manually in
    a session where this script's namespace persists.
    """
    ui_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fit_ui.py")
    if not os.path.isfile(ui_path):
        log("FIT_NOTE fit_ui.py not found next to fit_prepare.py: " + ui_path)
        return
    try:
        with open(ui_path, "r", encoding="utf-8") as f:
            source = f.read()
        namespace = {"__name__": "m2m_fit_ui_embedded", "__file__": ui_path}
        exec(compile(source, ui_path, "exec"), namespace)
        namespace["register"]()
        log("FIT_UI_REGISTERED " + ui_path)
    except Exception as exc:
        log("FIT_NOTE could not register fit_ui.py: " + repr(exc))
        log(traceback.format_exc())


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    opts = parse_args(sys.argv)
    for key in ("model", "skeleton", "blend", "config"):
        if not opts.get(key):
            raise RuntimeError("missing required argument --" + key)

    model_arg = opts["model"]
    skeleton_path = os.path.abspath(opts["skeleton"])
    blend_path = os.path.abspath(opts["blend"])
    config_path = os.path.abspath(opts["config"])
    model_path = os.path.abspath(model_arg)
    interactive = bool(opts.get("interactive"))

    log("FIT_PREPARE_START " + json.dumps({
        "model": model_path, "skeleton": skeleton_path,
        "blend": blend_path, "config": config_path,
        "interactive": interactive,
    }, sort_keys=True))

    # Start from an empty scene (factory startup still ships Cube/Camera/Light).
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    model_objs = import_glb(model_path)
    model_meshes = [o for o in model_objs if o.type == "MESH"]
    if not model_meshes:
        raise RuntimeError("model GLB contains no mesh")
    # Remove any armature that came with the model: this step fits the M2M rig.
    for o in model_objs:
        if o.type == "ARMATURE":
            bpy.data.objects.remove(o, do_unlink=True)

    skeleton_objs = import_glb(skeleton_path)
    arm = find_skeleton_armature(skeleton_objs)
    # Drop helper meshes (the M2M skeleton GLB ships a debug Icosphere) and
    # any extra armatures so the .blend holds exactly one model + one rig.
    for o in skeleton_objs:
        if o == arm:
            continue
        if o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)

    mn, mx = normalize_model(model_meshes)
    store_rest_pose(arm)
    scale, offset = auto_fit(arm, mn, mx)
    apply_auto_fit(arm, scale, offset)
    bones = bones_to_config(arm)
    write_config(config_path, model_arg, scale, offset, bones)

    scene = bpy.context.scene
    scene["m2m_fit_config_path"] = config_path
    scene["m2m_fit_armature_name"] = arm.name
    scene["m2m_fit_interactive"] = bool(interactive)
    configure_viewports(arm, mx.z - mn.z)

    os.makedirs(os.path.dirname(blend_path), exist_ok=True)
    # Leave the rig in Edit Mode so the GUI is ready for direct bone editing.
    enter_edit(arm)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    leave_edit()

    if interactive:
        register_embedded_ui(blend_path, config_path)

    log("FIT_PREPARE_OK %s %s" % (blend_path, config_path))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log("FIT_PREPARE_FAILED " + repr(exc))
        log(traceback.format_exc())
        sys.exit(1)
