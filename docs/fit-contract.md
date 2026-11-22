# Fit contract: frames, units and bone names

This document is the contract between the fitting stage, the animation
transplant stage and the Godot consumer. It is derived from
[`vendor/index.json`](../vendor/index.json) — the pinned Mesh2Motion (M2M)
assets. See [`pipeline.md`](pipeline.md) for the stage sequence and
[`licensing.md`](licensing.md) for provenance.

## 1. Frame and unit contract

Every intermediate and final asset obeys the same frame:

| Property | Value |
|---|---|
| Unit | 1 unit = 1 metre |
| Up axis | +Y |
| Forward axis | -Z |
| Origin | At the character's feet, between the heels |
| Armature object scale | 1.0, uniform, positive |
| Bone scale | 1.0, uniform, positive (no negative or mirrored scale) |
| Rest pose | The pinned M2M `skeleton.glb` bind pose |
| Root motion in exported clips | Removed; the `Root` track is constant zero |

glTF/GLB already specifies metres and Y-up, so "normalize" means *removing*
import-time conversions, not adding new ones. A model authored in centimetres
or Z-up must be converted once in `prep` and never again downstream.

The Godot consumer expects a node named `Armature` with a `Skeleton3D` child.
Animation tracks therefore resolve as `Armature/Skeleton3D:<bone>`. Bone names
in the exported GLB must match the names in this document exactly, including
case and underscores, or those tracks will be dropped on import.

### Why bone roll matters

The transplant stage copies M2M actions **directly**, with no retargeting. That
is only valid when the fitted rig has the same bone names, the same parent
hierarchy, the same rest transforms *and the same bone roll* as the M2M source.
Bone roll defines each bone's local coordinate frame; rotation channels in a
clip are expressed in that frame. Changing roll — even if head and tail
positions look correct — makes every transplanted rotation wrong.

The auto-fit stage therefore moves bone heads and tails to match the target
mesh bounds but must preserve roll. Bone-roll edits are not part of the fit
override contract: only positions may be overridden (see §5).

## 2. M2M bone inventory

The pinned `skeleton.glb` contains 66 joints. These are the complete set the
transplant stage sees. They are authored on a single chain topology, which is
why no general retargeting is required.

| Chain | Bones | Count |
|---|---|---|
| Root | `root` | 1 |
| Torso | `pelvis`, `spine_01`, `spine_02`, `spine_03` | 4 |
| Head | `neck_01`, `head`, `head_leaf` | 3 |
| Left arm | `clavicle_l`, `upperarm_l`, `lowerarm_l`, `hand_l` | 4 |
| Right arm | `clavicle_r`, `upperarm_r`, `lowerarm_r`, `hand_r` | 4 |
| Left thumb | `thumb_01_l`, `thumb_02_l`, `thumb_03_l`, `thumb_04_leaf_l` | 4 |
| Left index | `index_01_l`, `index_02_l`, `index_03_l`, `index_04_leaf_l` | 4 |
| Left middle | `middle_01_l`, `middle_02_l`, `middle_03_l`, `middle_04_leaf_l` | 4 |
| Left ring | `ring_01_l`, `ring_02_l`, `ring_03_l`, `ring_04_leaf_l` | 4 |
| Left pinky | `pinky_01_l`, `pinky_02_l`, `pinky_03_l`, `pinky_04_leaf_l` | 4 |
| Right thumb | `thumb_01_r`, `thumb_02_r`, `thumb_03_r`, `thumb_04_leaf_r` | 4 |
| Right index | `index_01_r`, `index_02_r`, `index_03_r`, `index_04_leaf_r` | 4 |
| Right middle | `middle_01_r`, `middle_02_r`, `middle_03_r`, `middle_04_leaf_r` | 4 |
| Right ring | `ring_01_r`, `ring_02_r`, `ring_03_r`, `ring_04_leaf_r` | 4 |
| Right pinky | `pinky_01_r`, `pinky_02_r`, `pinky_03_r`, `pinky_04_leaf_r` | 4 |
| Left leg | `thigh_l`, `calf_l`, `foot_l`, `ball_l`, `ball_leaf_l` | 5 |
| Right leg | `thigh_r`, `calf_r`, `foot_r`, `ball_r`, `ball_leaf_r` | 5 |

`*_leaf` joints are terminal helpers. They carry animation channels in the
stock clips but have no independent geometry to drive.

## 3. Naming trap

In the `polygon_humanoid` rig:

- `Shoulder_*` is the **upper arm** (M2M `upperarm_*`).
- `Elbow_*` is the **forearm** (M2M `lowerarm_*`).

Do not map by intuition. This is the single most common source of a
visually plausible but wrong transplant.

## 4. Full M2M → `polygon_humanoid` mapping

The default profile is `m2m-human`: names stay M2M, no mapping is applied. The
opt-in `polygon_humanoid` profile applies the table below. A dash means the
source bone has no destination in the target rig (see §6).

| # | M2M bone | `polygon_humanoid` bone |
|---:|---|---|
| 1 | `root` | `Root` |
| 2 | `pelvis` | `Hips` |
| 3 | `spine_01` | `Spine_01` |
| 4 | `spine_02` | `Spine_02` |
| 5 | `spine_03` | `Spine_03` |
| 6 | `neck_01` | `Neck` |
| 7 | `head` | `Head` |
| 8 | `head_leaf` | — |
| 9 | `clavicle_l` | `Clavicle_L` |
| 10 | `upperarm_l` | `Shoulder_L` |
| 11 | `lowerarm_l` | `Elbow_L` |
| 12 | `hand_l` | `Hand_L` |
| 13 | `index_01_l` | `IndexFinger_01_L` |
| 14 | `index_02_l` | `IndexFinger_02_L` |
| 15 | `index_03_l` | `IndexFinger_03_L` |
| 16 | `index_04_leaf_l` | `IndexFinger_04_L` |
| 17 | `middle_01_l` | `Finger_01_L` |
| 18 | `middle_02_l` | `Finger_02_L` |
| 19 | `middle_03_l` | `Finger_03_L` |
| 20 | `middle_04_leaf_l` | `Finger_04_L` |
| 21 | `pinky_01_l` | — |
| 22 | `pinky_02_l` | — |
| 23 | `pinky_03_l` | — |
| 24 | `pinky_04_leaf_l` | — |
| 25 | `ring_01_l` | — |
| 26 | `ring_02_l` | — |
| 27 | `ring_03_l` | — |
| 28 | `ring_04_leaf_l` | — |
| 29 | `thumb_01_l` | `Thumb_01_L` |
| 30 | `thumb_02_l` | `Thumb_02_L` |
| 31 | `thumb_03_l` | `Thumb_03_L` |
| 32 | `thumb_04_leaf_l` | — (folded into `Thumb_03_L`) |
| 33 | `clavicle_r` | `Clavicle_R` |
| 34 | `upperarm_r` | `Shoulder_R` |
| 35 | `lowerarm_r` | `Elbow_R` |
| 36 | `hand_r` | `Hand_R` |
| 37 | `index_01_r` | `IndexFinger_01_R` |
| 38 | `index_02_r` | `IndexFinger_02_R` |
| 39 | `index_03_r` | `IndexFinger_03_R` |
| 40 | `index_04_leaf_r` | `IndexFinger_04_R` |
| 41 | `middle_01_r` | `Finger_01_R` |
| 42 | `middle_02_r` | `Finger_02_R` |
| 43 | `middle_03_r` | `Finger_03_R` |
| 44 | `middle_04_leaf_r` | `Finger_04_R` |
| 45 | `pinky_01_r` | — |
| 46 | `pinky_02_r` | — |
| 47 | `pinky_03_r` | — |
| 48 | `pinky_04_leaf_r` | — |
| 49 | `ring_01_r` | — |
| 50 | `ring_02_r` | — |
| 51 | `ring_03_r` | — |
| 52 | `ring_04_leaf_r` | — |
| 53 | `thumb_01_r` | `Thumb_01_R` |
| 54 | `thumb_02_r` | `Thumb_02_R` |
| 55 | `thumb_03_r` | `Thumb_03_R` |
| 56 | `thumb_04_leaf_r` | — (folded into `Thumb_03_R`) |
| 57 | `thigh_l` | `UpperLeg_L` |
| 58 | `calf_l` | `LowerLeg_L` |
| 59 | `foot_l` | `Ankle_L` |
| 60 | `ball_l` | `Ball_L` |
| 61 | `ball_leaf_l` | `Toes_L` |
| 62 | `thigh_r` | `UpperLeg_R` |
| 63 | `calf_r` | `LowerLeg_R` |
| 64 | `foot_r` | `Ankle_R` |
| 65 | `ball_r` | `Ball_R` |
| 66 | `ball_leaf_r` | `Toes_R` |

## 5. Gap handling in the `polygon_humanoid` profile

The Godot rig has 50 bones and M2M has 66, and the two assign different
semantics to some chains. The profile resolves every gap deterministically:

| Gap | What the profile does |
|---|---|
| **Root** | `Root` is created, but all clips export a constant-zero `Root` track. M2M root motion is stripped, so the character does not drift in Godot. |
| **Clavicle** | `Clavicle_L/R` are created from the M2M `clavicle_l/r` where present; where a source rig omits them, they are synthesized as neutral bones at the shoulder base with no animation channels. |
| **Ball / Toes** | `Ball_L/R` and `Toes_L/R` are created. `ball_*` drives `Ball_*`; `ball_leaf_*` drives `Toes_*`. If a source lacks the leaf joint, `Toes_*` is left at rest. |
| **Eyes / Eyebrows / Jaw** | M2M has no equivalents. The three bones exist in the Godot rig with no tracks and stay at their rest transforms. |
| **Head leaf** | `head_leaf` has no target and is dropped after its parent `head` is mapped. |
| **Fifth finger chains** | M2M has five chains per hand (`thumb`, `index`, `middle`, `ring`, `pinky`); `polygon_humanoid` has only `Thumb`, `IndexFinger` and `Finger`. `index_*` → `IndexFinger_*`, `middle_*` → `Finger_*`. `ring_*` and `pinky_*` are dropped and their channels discarded: the Godot rig has a single bone group for the three non-index fingers. |
| **Thumb leaf** | M2M thumbs have four joints; the target has three. `thumb_04_leaf_*` is folded into `Thumb_03_*` (its rotation is applied to the last thumb bone), not silently dropped. |

Note on the pinned file: the raw `skeleton.glb` does contain `root`,
`clavicle_l/r`, `ball_l/r` and `*_leaf` joints, and the stock clips animate
them. The gaps above describe what the *export profile* guarantees for the
50-bone Godot target, not an absence of nodes in the source GLB. The mapping
table is therefore complete for all 66 source joints.

## 6. `config/fit/<name>.json` overrides

Auto-fitting scales the M2M skeleton to the normalized model's bounds. Manual
overrides are an optional, per-character refinement, referenced by the
character's `fit` field in `config/jobs.json` (see
[`pipeline.md`](pipeline.md#jobsjson-fields)). The file is applied **after**
auto-fit and uses metres in the normalized model frame:

```json
{
  "bones": {
    "pelvis": { "head": [0.0, 0.95, 0.0], "tail": [0.0, 1.05, 0.0] },
    "upperarm_l": { "tail": [0.42, 1.32, 0.0] }
  }
}
```

Rules:

- The path is relative to the repository root and is optional. Without it the
  auto-fit result is used unchanged.
- Only listed bones are modified. Unlisted bones keep their auto-fitted
  positions.
- You may specify `head`, `tail`, or both. Values are `[x, y, z]` in metres.
- Moving a parent translates its whole subtree; the relative offsets of
  descendants are preserved.
- **Roll is never overridden.** The vector from `head` to `tail` defines the
  bone direction; the bone's local twist is inherited from the M2M rest pose.
  Any override that would change roll must be rejected by the fit stage,
  because a direct action transplant cannot survive roll changes.
- Overrides are keyed by **M2M bone names**, even when the output profile is
  `polygon_humanoid`, because fitting happens before name mapping.

Use `--fit <model.glb> --interactive` to generate a starting point for this
file; see the quick start in the [README](../README.md).
