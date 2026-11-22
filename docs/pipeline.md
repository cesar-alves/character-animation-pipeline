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
swing-twist) is needed for the default path. See `docs/fit-contract.md`.

Implementation phases are tracked in the repository history.
