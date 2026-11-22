"""M2M Fit -- interactive bone placement panel for Blender 5.2.

ARTIST WORKFLOW
===============

1. Generate a fit session for your character (one command, run outside Blender):

       python3 tools/fit.py --interactive --model models/my_character.glb

   This normalizes the model, imports the CC0 Mesh2Motion human skeleton,
   auto-fits it to the mesh, saves ``work/fit/my_character.blend`` and writes
   the hand-off config ``config/fit/my_character.json``.  With --interactive it
   also opens the .blend in the GUI with this panel already registered.

   You can also run this file from Blender's Text Editor ("Run Script") after
   opening any fit .blend -- the panel appears in the 3D View N-panel under the
   "M2M Fit" tab.

2. The rig is saved in Edit Mode, positioned in a front orthographic view.
   Select individual bones and move heads/tails (and adjust Roll in the Bone
   properties) to match your character's joints.  Work on the *armature*, not
   on the mesh.  Keep the bone names and the parent/child structure intact:
   the batch pipeline transplants Mesh2Motion animation actions by bone name.

3. Write your notes in the panel field, then click "Export Fit Config".  This
   writes every edit bone's head/tail/roll back to the JSON file, preserving
   schema_version, model, profile, global and notes.  Coordinates are stored
   in final normalized model space (glTF convention: Y up, metres, feet at
   Y=0) and roll is stored in radians, exactly as Blender keeps it.

   "Reload Fit Config" throws away unsaved edits and re-reads the JSON.
   "Auto Fit Again" recomputes the uniform scale / foot alignment / X-Y
   centering from the current mesh and overwrites the config's global block
   and bone coordinates -- use it to reset after a bad manual edit.

4. Commit only the JSON config (the .blend is a scratch file).  The headless
   pipeline reads config/fit/<name>.json, applies the global transform, then
   overrides the listed bones with your head/tail/roll and skins the mesh.

NOTE ON ROLL: roll defines the bone's twist axis.  Preserve it or animations
will twist limbs inside-out.  Dragging heads/tails does not change roll; if
you rotate a bone in Edit Mode (R), check its Roll value afterwards.

Coordinate conversion: Blender is Z-up, the exported GLB (and the config) is
Y-up.  to_model_space() applies the proper rotation (x,y,z)->(x,z,-y); because
it is a rotation (not a mirror), roll is unchanged and copied verbatim.
"""

import json
import math
import os
import traceback

import bpy
from mathutils import Matrix, Vector


M2M_SIGNATURE = ("pelvis", "head", "foot_l", "foot_r")
HEAD_CHAIN = ("pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head")
FOOT_CHAINS = ("foot_l", "foot_r")


# --------------------------------------------------------------------------- #
# helpers (kept in sync with blender/fit_prepare.py)
# --------------------------------------------------------------------------- #
def to_model_space(v):
    return [round(float(v.x), 6), round(float(v.z), 6), round(-float(v.y), 6)]


def from_model_space(seq):
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


def make_active(obj):
    # object.select_all only polls in Object Mode; a fit session is saved in
    # Edit Mode, so leave it first when a *different* object is being edited.
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


def leave_edit(restore_edit=False):
    obj = bpy.context.object
    if obj and obj.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    if restore_edit and obj:
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")


def get_armature(context):
    name = context.scene.get("m2m_fit_armature_name", "")
    if name and name in bpy.data.objects:
        obj = bpy.data.objects[name]
        if obj.type == "ARMATURE":
            return obj
    for obj in context.scene.objects:
        if obj.type != "ARMATURE":
            continue
        names = set(b.name for b in obj.data.bones)
        if all(n in names for n in M2M_SIGNATURE):
            return obj
    return None


def descendants(bones, root_name):
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


def skeleton_vertical_refs(arm):
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
    top, bottom = skeleton_vertical_refs(arm)
    skel_h = top - bottom
    model_h = mx.z - mn.z
    scale = model_h / skel_h if skel_h > 1e-9 else 1.0
    bones = {b.name: b for b in arm.data.bones}
    body = [b for b in bones.values() if b.name != "root"]
    smn, smx = bounds([tuple(v) for b in body for v in (b.head_local, b.tail_local)])
    offset = Vector((
        (mn.x + mx.x) * 0.5 - (smn.x + smx.x) * 0.5 * scale,
        (mn.y + mx.y) * 0.5 - (smn.y + smx.y) * 0.5 * scale,
        mn.z - bottom * scale,
    ))
    return scale, offset


def mesh_bounds(meshes):
    pts = [tuple(obj.matrix_world @ v.co) for obj in meshes for v in obj.data.vertices]
    return bounds(pts)


def apply_auto_fit(arm, scale, offset):
    was_edit = bpy.context.object and bpy.context.object.mode == "EDIT"
    enter_edit(arm)
    ebs = list(arm.data.edit_bones)
    connected = {eb.name: eb.use_connect for eb in ebs}
    for eb in ebs:
        eb.use_connect = False
    for eb in ebs:
        eb.head = Vector(eb.head) * scale + offset
        eb.tail = Vector(eb.tail) * scale + offset
    for eb in ebs:
        eb.use_connect = connected[eb.name]
    leave_edit(restore_edit=was_edit)
    arm.location = (0.0, 0.0, 0.0)
    arm.rotation_euler = (0.0, 0.0, 0.0)
    arm.scale = (1.0, 1.0, 1.0)


def bones_to_config(arm):
    was_edit = bpy.context.object and bpy.context.object.mode == "EDIT"
    enter_edit(arm)
    out = {}
    mw = arm.matrix_world.copy()
    for eb in arm.data.edit_bones:
        out[eb.name] = {
            "head": to_model_space(mw @ eb.head),
            "tail": to_model_space(mw @ eb.tail),
            "roll": round(float(eb.roll), 6),
        }
    leave_edit(restore_edit=was_edit)
    return out


def apply_bone_config(arm, bones):
    """Set head/tail/roll for the bones present in the config (Y-up -> Z-up)."""
    was_edit = bpy.context.object and bpy.context.object.mode == "EDIT"
    enter_edit(arm)
    ebs = {eb.name: eb for eb in arm.data.edit_bones}
    connected = {eb.name: eb.use_connect for eb in ebs.values()}
    for eb in ebs.values():
        eb.use_connect = False
    applied = []
    for name, data in bones.items():
        eb = ebs.get(name)
        if eb is None:
            continue
        mw = arm.matrix_world.copy()
        inv = mw.inverted()
        eb.head = inv @ from_model_space(data["head"])
        eb.tail = inv @ from_model_space(data["tail"])
        eb.roll = float(data.get("roll", 0.0))
        applied.append(name)
    for eb in ebs.values():
        eb.use_connect = connected[eb.name]
    leave_edit(restore_edit=was_edit)
    return applied


def restore_rest_pose(arm):
    """Restore the pristine skeleton saved by fit_prepare (Edit Mode safe)."""
    raw = arm.get("m2m_rest_bones_json", "")
    if not raw:
        return False
    rest = json.loads(raw)
    was_edit = bpy.context.object and bpy.context.object.mode == "EDIT"
    enter_edit(arm)
    ebs = {eb.name: eb for eb in arm.data.edit_bones}
    connected = {eb.name: eb.use_connect for eb in ebs.values()}
    for eb in ebs.values():
        eb.use_connect = False
    for name, data in rest.items():
        eb = ebs.get(name)
        if eb is None:
            continue
        eb.head = Vector(data["head"])
        eb.tail = Vector(data["tail"])
        eb.roll = float(data["roll"])
    for eb in ebs.values():
        eb.use_connect = connected[eb.name]
    leave_edit(restore_edit=was_edit)
    return True


def get_config_path(scene):
    path = (getattr(scene, "m2m_fit_config", "") or "").strip()
    if not path:
        path = scene.get("m2m_fit_config_path", "")
    return os.path.abspath(bpy.path.abspath(path)) if path else ""


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(path, cfg):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")


# --------------------------------------------------------------------------- #
# scene properties (registered with the panel)
# --------------------------------------------------------------------------- #
def register_props():
    if not hasattr(bpy.types.Scene, "m2m_fit_config"):
        bpy.types.Scene.m2m_fit_config = bpy.props.StringProperty(
            name="Fit Config JSON", description="config/fit/*.json hand-off file",
            subtype="FILE_PATH", default="",
        )
    if not hasattr(bpy.types.Scene, "m2m_fit_notes"):
        bpy.types.Scene.m2m_fit_notes = bpy.props.StringProperty(
            name="Notes", description="Notes saved into the fit config", default="",
        )
    scene = bpy.context.scene
    if not scene.m2m_fit_config:
        scene.m2m_fit_config = scene.get("m2m_fit_config_path", "")
    path = get_config_path(scene)
    if path and os.path.isfile(path) and not scene.m2m_fit_notes:
        try:
            scene.m2m_fit_notes = load_config(path).get("notes", "")
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# operators
# --------------------------------------------------------------------------- #
class FIT_OT_SelectConfig(bpy.types.Operator):
    """Pick the fit JSON this panel reads and writes."""

    bl_idname = "m2m_fit.select_config"
    bl_label = "Browse Fit Config"
    bl_property = "filepath"

    filepath: bpy.props.StringProperty(
        name="Fit Config", description="Path to config/fit/*.json",
        subtype="FILE_PATH", default="",
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        path = bpy.path.abspath(self.filepath)
        context.scene.m2m_fit_config = path
        context.scene["m2m_fit_config_path"] = path
        if os.path.isfile(path):
            try:
                context.scene.m2m_fit_notes = load_config(path).get("notes", "")
            except Exception as exc:
                self.report({"WARNING"}, "Could not read notes: " + repr(exc))
        self.report({"INFO"}, "Fit config: " + path)
        return {"FINISHED"}


class FIT_OT_ExportConfig(bpy.types.Operator):
    """Write current edit-bone head/tail/roll into the fit JSON."""

    bl_idname = "m2m_fit.export_config"
    bl_label = "Export Fit Config"
    bl_property = "config_path"

    config_path: bpy.props.StringProperty(
        name="Fit Config", description="Where to write the fit JSON",
        subtype="FILE_PATH", default="",
    )

    def execute(self, context):
        path = bpy.path.abspath(self.config_path) if self.config_path else get_config_path(context.scene)
        if not path:
            self.report({"ERROR"}, "No fit config path set -- use Browse first")
            return {"CANCELLED"}
        arm = get_armature(context)
        if arm is None:
            self.report({"ERROR"}, "No Mesh2Motion armature found in the scene")
            return {"CANCELLED"}
        try:
            cfg = load_config(path) if os.path.isfile(path) else {}
            # Preserve the whole contract; only bone coordinates + notes change.
            cfg.setdefault("schema_version", 1)
            cfg.setdefault("model", "")
            cfg.setdefault("profile", "m2m-human")
            cfg.setdefault("global", {"uniform_scale": 1.0, "offset": [0.0, 0.0, 0.0], "yaw_degrees": 0.0})
            cfg["notes"] = context.scene.m2m_fit_notes
            cfg["bones"] = bones_to_config(arm)
            save_config(path, cfg)
        except Exception as exc:
            self.report({"ERROR"}, "Export failed: " + repr(exc))
            self.report({"ERROR"}, traceback.format_exc())
            return {"CANCELLED"}
        context.scene.m2m_fit_config = path
        context.scene["m2m_fit_config_path"] = path
        self.report({"INFO"}, "Exported %d bones to %s" % (len(cfg["bones"]), path))
        return {"FINISHED"}


class FIT_OT_ReloadConfig(bpy.types.Operator):
    """Re-read the fit JSON and apply it to the armature."""

    bl_idname = "m2m_fit.reload_config"
    bl_label = "Reload Fit Config"
    bl_property = "config_path"

    config_path: bpy.props.StringProperty(
        name="Fit Config", description="Fit JSON to reload",
        subtype="FILE_PATH", default="",
    )

    def execute(self, context):
        path = bpy.path.abspath(self.config_path) if self.config_path else get_config_path(context.scene)
        if not path or not os.path.isfile(path):
            self.report({"ERROR"}, "Fit config not found: " + path)
            return {"CANCELLED"}
        arm = get_armature(context)
        if arm is None:
            self.report({"ERROR"}, "No Mesh2Motion armature found in the scene")
            return {"CANCELLED"}
        try:
            cfg = load_config(path)
            applied = apply_bone_config(arm, cfg.get("bones", {}))
            context.scene.m2m_fit_notes = cfg.get("notes", "")
            context.scene.m2m_fit_config = path
            context.scene["m2m_fit_config_path"] = path
        except Exception as exc:
            self.report({"ERROR"}, "Reload failed: " + repr(exc))
            self.report({"ERROR"}, traceback.format_exc())
            return {"CANCELLED"}
        self.report({"INFO"}, "Reloaded %d bones from %s" % (len(applied), path))
        return {"FINISHED"}


class FIT_OT_AutoFitAgain(bpy.types.Operator):
    """Recompute uniform scale, foot alignment and X/Y centering."""

    bl_idname = "m2m_fit.auto_fit_again"
    bl_label = "Auto Fit Again"

    def execute(self, context):
        arm = get_armature(context)
        if arm is None:
            self.report({"ERROR"}, "No Mesh2Motion armature found in the scene")
            return {"CANCELLED"}
        meshes = [o for o in context.scene.objects if o.type == "MESH"]
        if not meshes:
            self.report({"ERROR"}, "No model mesh found in the scene")
            return {"CANCELLED"}
        try:
            # Start from the pristine template, otherwise a second auto-fit
            # would just measure the already-fitted rig and change nothing.
            restore_rest_pose(arm)
            mn, mx = mesh_bounds(meshes)
            scale, offset = auto_fit(arm, mn, mx)
            apply_auto_fit(arm, scale, offset)
            bones = bones_to_config(arm)
            path = get_config_path(context.scene)
            if path and os.path.isfile(path):
                cfg = load_config(path)
                cfg["global"] = {
                    "uniform_scale": round(float(scale), 6),
                    "offset": to_model_space(offset),
                    "yaw_degrees": float(cfg.get("global", {}).get("yaw_degrees", 0.0)),
                }
                cfg["bones"] = bones
                save_config(path, cfg)
        except Exception as exc:
            self.report({"ERROR"}, "Auto fit failed: " + repr(exc))
            self.report({"ERROR"}, traceback.format_exc())
            return {"CANCELLED"}
        self.report({"INFO"}, "Auto fit: scale=%.6f, %d bones" % (scale, len(bones)))
        return {"FINISHED"}


# --------------------------------------------------------------------------- #
# panel
# --------------------------------------------------------------------------- #
class VIEW3D_PT_m2m_fit(bpy.types.Panel):
    bl_label = "M2M Fit"
    bl_idname = "VIEW3D_PT_m2m_fit"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "M2M Fit"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        arm = get_armature(context)

        box = layout.box()
        box.label(text="Fit config", icon="FILE")
        row = box.row(align=True)
        row.prop(scene, "m2m_fit_config", text="")
        row.operator("m2m_fit.select_config", text="", icon="FILE_FOLDER")
        box.operator("m2m_fit.export_config", icon="EXPORT")
        box.operator("m2m_fit.reload_config", icon="IMPORT")
        box.operator("m2m_fit.auto_fit_again", icon="OUTLINER_OB_ARMATURE")

        layout.separator()
        layout.label(text="Armature: " + (arm.name if arm else "<none>"))
        layout.label(text="Edit bones in Edit Mode, then Export.")
        layout.separator()
        layout.label(text="Notes")
        layout.prop(scene, "m2m_fit_notes", text="")


CLASSES = (
    FIT_OT_SelectConfig,
    FIT_OT_ExportConfig,
    FIT_OT_ReloadConfig,
    FIT_OT_AutoFitAgain,
    VIEW3D_PT_m2m_fit,
)


def register():
    for cls in CLASSES:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass  # already registered (e.g. script run twice)
    register_props()


def unregister():
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except (RuntimeError, ValueError):
            pass
    for prop in ("m2m_fit_config", "m2m_fit_notes"):
        try:
            delattr(bpy.types.Scene, prop)
        except AttributeError:
            pass


if __name__ == "__main__":
    register()
