#!/usr/bin/env bash
# End-to-end smoke test: build one character with two pinned clips and verify
# the GLB, the validation report and the build record. Run from anywhere.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p work out-e2e docs

python3 tools/fetch_vendor.py

cat > work/e2e_jobs.json <<'JSON'
{
  "schema_version": 1,
  "characters": [
    {
      "name": "e2e-hero",
      "model": "vendor/bin/model.glb",
      "clips": ["walk", "idle-a"],
      "profile": "m2m-human"
    }
  ]
}
JSON

echo "+ python3 pipeline.py --job work/e2e_jobs.json --no-fetch --out out-e2e --vendor vendor/bin"
python3 pipeline.py --job work/e2e_jobs.json --no-fetch --out out-e2e --vendor vendor/bin 2>&1 | tee work/e2e-run.log

test -s out-e2e/e2e-hero.glb
test -s reports/e2e-hero.json
test -s builds/e2e-hero.json

python3 - <<'PY'
import json
with open("reports/e2e-hero.json", encoding="utf-8") as handle:
    report = json.load(handle)
assert report["ok"], report["errors"]
assert "walk" in report["clips"] and "idle-a" in report["clips"], report["clips"]
with open("builds/e2e-hero.json", encoding="utf-8") as handle:
    record = json.load(handle)
assert record["name"] == "e2e-hero"
assert record["clips_requested"] == ["walk", "idle-a"]
print("E2E: validator report:")
print(json.dumps(report, indent=2))
PY

python3 - <<'PY'
import json
with open("work/e2e-run.log", encoding="utf-8") as handle:
    log = handle.read()
with open("reports/e2e-hero.json", encoding="utf-8") as handle:
    report = json.dumps(json.load(handle), indent=2)
with open("docs/e2e-run.md", "w", encoding="utf-8") as handle:
    handle.write("# End-to-end run\n\n")
    handle.write("Command: `python3 pipeline.py --job work/e2e_jobs.json --no-fetch "
                 "--out out-e2e --vendor vendor/bin`\n\n")
    handle.write("## Full output\n\n```text\n" + log.rstrip() + "\n```\n\n")
    handle.write("## Validator report (`reports/e2e-hero.json`)\n\n```json\n" + report + "\n```\n")
PY

echo "E2E_OK"
