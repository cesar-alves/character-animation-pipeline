# AGENTS.md

## Tests

This repository declares its test suite in `test-segments.toml`. The single
entry point is `scripts/test.sh`; do not invent or run unlisted test commands.

- List the declared segments: `scripts/test.sh --list`
- Run the full suite: `scripts/test.sh --full`
- Prove exhaustiveness: `scripts/test.sh --verify`

Never use a test command that is not declared in the manifest.
