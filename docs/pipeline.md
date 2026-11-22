# Pipeline architecture

```
models/*.glb + config/jobs.json
        |
        v
[prep] normalize units/axes, clean mesh
        |
        v
[skeleton] import pinned M2M skeleton, auto-fit to bounds (+ config/fit overrides)
        |
        v
[skin] bone-heat auto weights, with proximity fallback
        |
        v
[animations] import selected M2M clip GLBs, transplant actions onto fitted rig
        |
        v
[export] one GLB per character, all clips as named actions
        |
        v
[validate] re-import, check skeleton/clips/deformation
        |
        v
[mirror] dated, immutable output folder + manifest + checksums
```

Design note: Mesh2Motion's animation library is authored on the same skeleton
template we fit to the target mesh, so no general retargeting (bone mapping,
swing-twist) is needed for the default path. See
[`fit-contract.md`](fit-contract.md) for the exact bone, frame and roll
contract, and [`licensing.md`](licensing.md) for what we vendor.

## jobs.json fields

`config/jobs.example.json` is a working template. Copy it to
`config/jobs.json` and edit. JSON has no comments, so every field is described
here.

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

| Field | Required | Type | Meaning |
|---|---|---|---|
| `schema_version` | yes | integer | Must be `1`. Reject anything else. |
| `characters` | yes | array | One entry per output GLB. Order defines processing order. |
| `characters[].name` | yes | string | Character id. Used for `builds/<name>.json`, `reports/<name>.json` and the output GLB stem. Must be unique and safe as a file name. |
| `characters[].model` | yes | string | Path to the input GLB, relative to the repository root. v1 accepts GLB only (see [`formats.md`](formats.md)). |
| `characters[].clips` | yes | array of strings | M2M clips to embed. Each entry is either a logical clip name (`walk`) or a GLB file name (`walk.glb`). Names are resolved against the files pinned in [`vendor/index.json`](../vendor/index.json). Duplicates are deduplicated; order sets action order in the export. |
| `characters[].profile` | no | string | Output bone-naming profile. Default `m2m-human` (keep M2M names). Use `polygon_humanoid` to map to the Godot project's 50-bone rig; see [`fit-contract.md`](fit-contract.md#4-full-m2m--polygon_humanoid-mapping). |
| `characters[].fit` | no | string | Path to a manual bone-override JSON, relative to the repository root. See [`fit-contract.md`](fit-contract.md#6-configfitnamejson-overrides). |

Further rules:

- `clips` must resolve to files that exist in `vendor/bin/` after
  `tools/fetch_vendor.py` has run. An unknown name is a hard error, not a
  warning, so a typo never produces a silently incomplete GLB.
- The pinned starter clips are `walk.glb`, `idle-a.glb`, `run-anime.glb` and
  `jump-2.glb`. Upstream has no plain `idle.glb`, `run.glb` or `jump.glb`, so
  those logical names are not available; use the pinned names.
- `profile` and `fit` are independent: fitting always happens in M2M bone
  space, and name mapping happens afterwards.
- Unknown top-level or per-character fields are rejected to catch typos.

## Asset pin

[`vendor/index.json`](../vendor/index.json) pins one Mesh2Motion commit and an
explicit allow-list of files with sha256, byte size and source URL. Fetch and
verify them with:

```bash
python3 tools/fetch_vendor.py --index vendor/index.json --dest vendor/bin
```

The tool is idempotent: correct files are left untouched and no network call
is made. Failures print `FETCH_FAILED <reason>` and exit non-zero. Binaries in
`vendor/bin/` are gitignored; only the index is tracked.

## Exact stage contract

Each stage is pure with respect to the previous one: it reads only the named
inputs and writes only the named outputs. Intermediate state lives in `work/`.

### 1. prep

- **In:** the character GLB from `model`.
- **Out:** one normalized GLB in `work/`.
- **Contract:** 1 unit = 1 metre, +Y up, -Z forward, origin at the feet,
  armature scale 1.0. Mesh is cleaned (orphan vertices, non-manifold edges,
  applied object transforms). No animation data is expected on input.

### 2. skeleton

- **In:** normalized GLB + pinned `vendor/bin/skeleton.glb` + optional `fit`
  override JSON.
- **Out:** a GLB whose armature uses the M2M 66-joint hierarchy, fitted to the
  model bounds.
- **Contract:** bone names, hierarchy, rest transforms and **bone roll** match
  the M2M template so actions can be transplanted directly. Overrides are
  applied after auto-fit and may not change roll.

### 3. skin

- **In:** fitted rig + mesh.
- **Out:** the same rig with per-vertex weights and one skin modifier.
- **Contract:** Blender bone-heat weighting is the primary method; vertices
  that bone heat cannot weight use nearest-bone proximity as a fallback. Every
  vertex has a normalized, non-empty weight set. The rig is unchanged.

### 4. animations

- **In:** skinned GLB + one GLB per entry in `clips`.
- **Out:** the same rig with one named action per clip.
- **Contract:** actions are transplanted, not retargeted. Channel curves are
  copied onto bones with identical M2M names. When `profile` is
  `polygon_humanoid`, names are mapped per the fit contract and gaps are
  resolved there. M2M root motion is stripped and the root track is held at
  zero. Action names are the logical clip names (without `.glb`).

### 5. export

- **In:** rig, skin and all actions.
- **Out:** `out/<name>.glb` plus `builds/<name>.json`.
- **Contract:** exactly one skinned mesh and one skeleton per file; every
  selected clip is embedded as a named action. The GLB is self-contained — no
  external textures or buffers. `builds/<name>.json` records the input paths,
  resolved clip names, profile, fit override and the source asset commit.

### 6. validate

- **In:** exported GLB + `builds/<name>.json`.
- **Out:** `reports/<name>.json`.
- **Contract:** re-import the GLB in a clean Blender session and assert the
  joint count and names, that every expected action is present, that the root
  track is constant zero, and that a sample of vertices deforms when a clip is
  evaluated. Any failed assertion aborts the run and is recorded in the
  report.

### 7. mirror

- **In:** validated GLB, build JSON, report JSON.
- **Out:** a dated, immutable output folder containing the GLBs, a manifest
  and per-file checksums.
- **Contract:** the mirror is append-only. Re-running a job never overwrites a
  dated folder; the manifest is generated from the actual files, not from
  expected paths.

Blender 5.2 is required for the stages that touch `bpy` and is invoked
headlessly; the Python CLI itself never imports `bpy`.

Implementation phases are tracked in the repository history.
