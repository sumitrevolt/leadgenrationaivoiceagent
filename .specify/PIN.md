# Spec Kit pin (LeadGen)

| Field | Value |
|-------|-------|
| Tool | `specify-cli` from `github/spec-kit` |
| Pin | **`v0.15.2`** (not floating `latest`) |
| Install | `scripts/setup_spec_kit.ps1` (dev-operator only) |
| Constitution | `.specify/memory/constitution.md` |

**Wave 1 rule:** Do **not** install Spec Kit inside CI or production Docker images.
Do **not** run `uv tool install specify-cli` without the `@v0.15.2` pin.
