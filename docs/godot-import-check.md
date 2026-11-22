# Godot clean-project import check

This records a verification of the final consumer path: an exported character
GLB dropped into `assets/vendor/characters/` (the Godot project's vendor rule)
imports cleanly and exposes its clips.

The check was run against `out-e2e/e2e-hero.glb` from `bash tests/e2e.sh`, using
a disposable project in `/tmp` — no real Godot project was modified.

## Commands

```bash
TDIR=/tmp/opencode/cap-godot-import
mkdir -p "$TDIR/assets/vendor/characters/e2e-hero"
cat > "$TDIR/project.godot" <<'EOF'
[application]
config/name="cap-import-test"
config/features=PackedStringArray("4.7")
EOF
cp out-e2e/e2e-hero.glb "$TDIR/assets/vendor/characters/e2e-hero/"
godot --headless --path "$TDIR" --import
godot --headless --path "$TDIR" --script res://probe.gd
```

`probe.gd` loads the GLB as a `PackedScene`, instantiates it, walks the tree for
`AnimationPlayer` nodes and prints every clip name.

## Observed result

The import completed with no import errors and produced
`e2e-hero.glb.import` plus the extracted embedded texture. The probe printed:

```text
PROBE_ROOT e2e-hero
PROBE_CLIP idle-a
PROBE_CLIP walk
PROBE_OK
```

Godot's headless dummy renderer emits unrelated cleanup messages at exit
(`RID allocations ... leaked`); these are not import failures and the probe's
assertion on both clip names passed.

This confirms the exported GLB satisfies the Godot project's import contract:
one skinned mesh, named clips, and no missing resources when the binary lives
in the gitignored vendor tree.
