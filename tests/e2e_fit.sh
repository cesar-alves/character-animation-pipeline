#!/usr/bin/env bash
# End-to-end check of the interactive-fit hand-off: generate a fit config,
# consume it in the batch pipeline, validate the resulting GLB.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f vendor/bin/skeleton.glb ] || [ ! -f vendor/bin/model.glb ]; then
  python3 tools/fetch_vendor.py >/dev/null
fi

FIT_CONFIG=work/e2e-fit.json
JOB=work/e2e-fit-jobs.json
OUT=out-e2e-fit
NAME=e2e-fit-hero
rm -rf "$OUT"

python3 tools/fit.py \
  --model vendor/bin/model.glb \
  --config "$FIT_CONFIG" \
  --blend work/fit/e2e-fit.blend \
  --no-interactive

python3 - "$FIT_CONFIG" "$JOB" "$NAME" <<'PY'
import json, sys
fit, job, name = sys.argv[1:4]
data = {
    "schema_version": 1,
    "characters": [{
        "name": name,
        "model": "vendor/bin/model.glb",
        "clips": ["walk", "idle-a"],
        "profile": "m2m-human",
        "fit": fit,
    }],
}
with open(job, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
PY

python3 pipeline.py --job "$JOB" --no-fetch --out "$OUT" --vendor vendor/bin

test -s "$OUT/$NAME.glb"
python3 - "$NAME" <<'PY'
import json, sys
name = sys.argv[1]
with open(f"reports/{name}.json", encoding="utf-8") as handle:
    report = json.load(handle)
assert report["ok"], report["errors"]
assert set(report["clips"]) == {"walk", "idle-a"}, report["clips"]
assert any(c["name"] == "root_translation_constant" and c["ok"] for c in report["checks"])
with open(f"builds/{name}.json", encoding="utf-8") as handle:
    record = json.load(handle)
assert record["fit"] and record["fit"]["sha256"], record
print("E2E_FIT_REPORT_OK", name)
PY

echo E2E_FIT_OK
