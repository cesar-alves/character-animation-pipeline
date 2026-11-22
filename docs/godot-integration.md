# Godot integration

The Godot side of the pipeline is deliberately thin: the Blender build produces
one Godot-ready GLB per character, and the standard-library helpers in `src/`
validate it, mirror it to dated storage and drop it into a Godot project.
Nothing in `src/` imports `bpy`.

## Target rig conventions

The Godot project's rig is **`polygon_humanoid`**, a frozen 50-bone skeleton.
All exported assets must follow these conventions:

| Convention | Value |
|---|---|
| Units | 1 unit = 1 m |
| Up axis | Y up |
| Forward | -Z forward |
| Ground | feet at y = 0 |
| Armature node | `Armature` |
| Skeleton child | `Skeleton3D` (child of `Armature`) |
| Animation track paths | `Armature/Skeleton3D:<bone>` |
| Root motion | stripped from every clip |
| Output | one GLB with exactly one skin, one skinned mesh and named clips |

## Bone profile (`profiles/polygon_humanoid.json`)

The profile is **opt-in**: pass it to the validator with `--profile` and use it
in the Godot importer when renaming bones. Its `map` maps Mesh2Motion (M2M)
source bone names (the map keys, i.e. the names expected inside the exported
GLB) to the frozen Godot rig names (the values). A value of `DROP` means the
source chain has no target: `thumb_04_leaf`, all `ring_*` and all `pinky_*`
chains are discarded. The ten bones in `synthesize` have no M2M source and are
added at rest in Godot (`Root`, `Clavicle_L/R`, `Ball_L/R`, `Toes_L/R`, `Eyes`,
`Eyebrows`, `Jaw`), giving 40 mapped + 10 synthesized = 50 bones.

## Validator

```
python3 -m src.validate out/hero.glb \
  --clips idle,walk \
  --profile profiles/polygon_humanoid.json \
  --report reports/hero.json
```

It prints `VALIDATE_OK` (exit 0) or `VALIDATE_FAILED` (exit 1) and writes a
2-space-indented JSON report when `--report` is given. The report contains
`ok`, `checks` (`name`/`ok`/`detail`), `bones`, `clips` and `errors`.

Checks performed:

- exactly one skin;
- at least one skinned mesh (primitive with `JOINTS_0` and `WEIGHTS_0`);
- skeleton bone count > 0;
- no cameras or lights (`cameras`, node `camera`, `KHR_lights_punctual`);
- every requested clip is present in `animations`;
- when a profile is given, bone names match it (no unknown or missing source
  bones; synthesized bones are allowed but not required);
- if a `Root`/`pelvis` translation channel exists, its translation is constant
  (root motion must have been stripped).

Python API: `validate.validate_glb(path, expected_clips=None, profile=None)`
and `validate.write_report(report, path)`.

## Dated Drive mirror

```
export CHARACTER_PIPELINE_DRIVE_ROOT=/mnt/drive/characters
python3 -m src.mirror --files out/hero.glb --name hero \
  --date 2026-11-22 --godot-project /path/to/godot-project
```

`mirror_files(files, root, date, name, require=False, force=False)` copies each
`(source, relative_dest)` pair into
`<root>/generated/characters/<name>/<YYYY-MM-DD>/`, writes `manifest.json`
(schema version, name, date, generated-at timestamp and per-file path/size/
sha256) and `CHECKSUMS.sha256` (`sha256  path` lines). A non-empty existing dated
folder is refused unless `force=True`, keeping published builds immutable.

With no drive root and without `--require-drive`, the CLI prints `MIRROR_SKIP`
and does nothing; with `--require-drive` a missing root is an error. The CLI
never touches a Godot project unless `--godot-project` is passed explicitly.

Use `SRC::REL` in `--files` to choose a relative destination name, e.g.
`--files out/hero.glb::models/hero.glb`.

## Godot drop-in

`copy_to_godot(files, godot_project, character_name,
subdir='assets/vendor/characters')` copies the same GLBs into
`<godot_project>/assets/vendor/characters/<character_name>/` and writes a short
`README.md`. The assets are **CC0-derived build artifacts** and the target
project **gitignores** `assets/vendor/characters/`, so the drop-in folder stays
local and is not committed.

## Tests

```
python3 -m unittest discover -s tests -v
```

The tests build a tiny GLB fixture in memory, so no external asset or Blender
installation is required.
