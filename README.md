# character-animation-pipeline

Headless, Blender-based pipeline that fits the CC0 Mesh2Motion human skeleton to
your own GLB character, auto-weights the mesh, embeds selected Mesh2Motion
animation clips, and exports a single Godot-ready GLB.

The tool is offline, free and open source:

- Pipeline code: MIT
- Reused Mesh2Motion assets: CC0 (see `docs/licensing.md`)

See [`docs/pipeline.md`](docs/pipeline.md) for the architecture and
[`docs/formats.md`](docs/formats.md) for the supported input formats.

## Quick start

```bash
# one character + the clips named in config/jobs.json
python3 pipeline.py --job config/jobs.json --in ./models --out ./out

# prepare an interactive fitting session for a character that needs manual bone placement
python3 pipeline.py --fit models/my_character.glb --interactive
```

Blender 5.2 is required and is invoked headlessly; the CLI itself never imports
`bpy`.
