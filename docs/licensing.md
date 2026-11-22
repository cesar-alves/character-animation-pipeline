# Licensing and provenance

## Summary

| Component | Origin | License | Vendored here? |
|---|---|---|---|
| Pipeline code (`tools/`, scripts, config, docs) | This project | MIT — see [`LICENSE`](../LICENSE) | Yes |
| Mesh2Motion human skeleton and animation clips | [Mesh2Motion](https://github.com/Mesh2Motion/mesh2motion-app) | CC0 1.0 (public domain dedication) | Yes, pinned in [`vendor/index.json`](../vendor/index.json) |
| Quaternius art used by Mesh2Motion | [Quaternius](https://quaternius.com/) | CC0 1.0 | Yes, indirectly, as embedded in the pinned GLBs |
| Mesh2Motion application source | [Mesh2Motion](https://github.com/Mesh2Motion/mesh2motion-app) | MIT | No — not fetched |
| Other Mesh2Motion art variations | [Mesh2Motion](https://github.com/Mesh2Motion/mesh2motion-app) | Mixed, including CC-BY and CC-SA | No — not fetched |

## What this repository actually fetches

The asset pin in [`vendor/index.json`](../vendor/index.json) records one commit of
`Mesh2Motion/mesh2motion-app` and a short, explicit allow-list of files. Only
these are downloaded, by [`tools/fetch_vendor.py`](../tools/fetch_vendor.py):

- `static/assets/human/skeleton.glb` — the fitted rig template.
- `static/assets/human/model.glb` — the reference human mesh.
- A starter set of animation GLBs under `static/assets/human/animations/`.

Nothing else is fetched. In particular, no application code, no other
characters, and no other model libraries are copied into this repository.
Downloaded binaries land in `vendor/bin/`, which is gitignored; only the pin
and the checksums are tracked. Re-running the fetcher verifies sha256 for every
entry, so a changed upstream file is detected rather than silently absorbed.

## Important: not all Mesh2Motion variations are CC0

Mesh2Motion ships several asset variations (characters, props and some
animation packs) that are **not** CC0. Some are licensed **CC-BY** and some
**CC-SA**. Those variations are deliberately **not vendored**, and they are not
part of this project's distribution. Do not add them to `vendor/index.json`
without first resolving their license and adding the required attribution or
share-alike terms. The CC0 status described here applies only to the specific
files listed in the pin.

## Attribution

This project does not require attribution for the CC0 assets it reuses, but we
gladly credit the original authors:

- **Mesh2Motion** — the fitted human skeleton template and the animation clips.
  <https://github.com/Mesh2Motion/mesh2motion-app> (MIT code, CC0 art).
- **Quaternius** — the original CC0 character art that the Mesh2Motion human
  assets are based on. <https://quaternius.com/> (CC0).
- **This project** — pipeline code and documentation, licensed under the
  [MIT License](../LICENSE), Copyright (c) 2026 cesar-alves.

If you redistribute a GLB produced by this pipeline, it contains derived CC0
mesh and animation data and can be redistributed under any terms. The MIT
license covers the pipeline code, not the output assets.
