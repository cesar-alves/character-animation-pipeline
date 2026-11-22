# character-animation-pipeline

Headless, Blender-based pipeline that fits the CC0 Mesh2Motion human skeleton to
your own GLB character, auto-weights the mesh, embeds selected Mesh2Motion
animation clips, and exports a single Godot-ready GLB.

The tool is offline, free and open source:

- Pipeline code: MIT — see [`LICENSE`](LICENSE).
- Reused Mesh2Motion art: CC0 — see [`docs/licensing.md`](docs/licensing.md).

## Layout

```text
character-animation-pipeline/
├── README.md, LICENSE, .gitignore, .gitattributes
├── pipeline.py                 # headless CLI (never imports bpy itself)
├── tools/fetch_vendor.py       # fetch + sha256-verify pinned assets
├── config/
│   ├── jobs.example.json       # template; copy to jobs.json
│   ├── jobs.json               # your job definitions
│   └── fit/<name>.json         # optional manual bone overrides
├── vendor/
│   ├── index.json              # pinned commit + hashes (tracked)
│   └── bin/                    # downloaded GLBs (gitignored)
├── models/                     # your input GLBs (local, not tracked)
├── docs/
│   ├── pipeline.md             # jobs.json fields + stage contract
│   ├── formats.md              # supported input/output formats
│   ├── fit-contract.md         # units, bone names and mapping
│   └── licensing.md            # provenance and attribution
├── builds/<name>.json          # per-build metadata (tracked)
├── reports/<name>.json         # validation reports (tracked)
├── work/                       # intermediates (gitignored)
└── out/                        # exported GLBs (gitignored)
```

The Godot drop-in target for exported GLBs is `assets/vendor/characters/`.

## Quick start

```bash
# 1. Requirements: Python 3 and Blender 5.2 on PATH.

# 2. Fetch and verify the pinned Mesh2Motion assets (idempotent; no network
#    access needed once the files are already correct).
python3 tools/fetch_vendor.py --index vendor/index.json --dest vendor/bin
# -> FETCH_OK 6

# 3. Define characters and clips.
cp config/jobs.example.json config/jobs.json
#    edit name, model, clips, profile and fit — see docs/pipeline.md

# 4. Put your GLBs in models/ and run the pipeline.
python3 pipeline.py --job config/jobs.json --in ./models --out ./out

# 5. Drop the results into the Godot project.
cp out/hero.glb <godot-project>/assets/vendor/characters/hero.glb

# Optional: prepare an interactive fitting session for a character that needs
# manual bone placement, then save the result as config/fit/<name>.json.
python3 tools/fit.py --model models/my_character.glb --interactive
```

V1 accepts GLB input only and exports one GLB per character with all selected
clips embedded as named actions. The default output keeps M2M bone names; use
`profile: "polygon_humanoid"` for the Godot project's 50-bone rig.

## Docs

- [`docs/pipeline.md`](docs/pipeline.md) — jobs.json fields and the exact stage contract.
- [`docs/formats.md`](docs/formats.md) — supported formats and what is planned.
- [`docs/fit-contract.md`](docs/fit-contract.md) — units, bone names, mapping and overrides.
- [`docs/licensing.md`](docs/licensing.md) — licenses, vendored scope and attribution.
- [`docs/batch-usage.md`](docs/batch-usage.md) — batch CLI, job schema and root-motion stripping.
- [`docs/interactive-fit.md`](docs/interactive-fit.md) — Blender fitting panel and fit JSON.
- [`docs/godot-integration.md`](docs/godot-integration.md) — validator, Drive mirror and bone profile.
- [`docs/godot-import-check.md`](docs/godot-import-check.md) — clean-project import evidence.
- [`docs/e2e-run.md`](docs/e2e-run.md) — recorded end-to-end run.

## Tests

The repository uses a declared segment contract (`test-segments.toml`):

```bash
python3 scripts/testctl.py --verify   # every test belongs to exactly one segment
bash scripts/test.sh --full           # unit + both E2E segments
```

Segment ids: `unit`, `e2e-batch`, `e2e-fit`. The E2E segments use the cached
CC0 assets in `vendor/bin/` and Blender 5.2; no display is required.
