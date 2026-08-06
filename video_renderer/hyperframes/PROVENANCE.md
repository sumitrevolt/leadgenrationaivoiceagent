# HyperFrames renderer — provenance and licence record

Everything here was verified on **2026-08-01** against the live upstream, not
copied from documentation or memory.

## Upstream

| Field | Value | How it was verified |
|---|---|---|
| Repository | `heygen-com/hyperframes` | GitHub API `repos/heygen-com/hyperframes` |
| Licence | **Apache-2.0** | `license.spdx_id` from the same API response, and the published package's own `license` field |
| Inspected commit | `343c02518889f46ee3962256b19ac4189264907d` | `repos/.../commits/main`, committed `2026-08-01T03:07:03Z` |
| npm package | `hyperframes` | `npm view hyperframes` |
| **Pinned version** | **`0.7.87`** | exact pin in `package.json`; `package-lock.json` committed |
| Archived / deprecated | No | repo `archived: false`, released `v0.7.87` on 2026-07-31 |

The npm tarball ships only `README.md`, `bin/`, `dist/`, `package.json` — it does
**not** include a `LICENSE` file. The Apache-2.0 grant is therefore evidenced by
the package metadata plus the upstream `LICENSE` at the pinned commit.

## What is vendored

Nothing from the upstream monorepo is copied into this repository. We depend on
the published npm package only, installed from the committed lockfile. No
upstream demo footage, music, logo, voiceover or other bundled media is used —
the `registry` examples were never installed.

## Bundled third-party assets

| Asset | Version | Licence |
|---|---|---|
| `@fontsource/noto-sans` (Latin woff2) | `5.3.0` | OFL-1.1 |
| `@fontsource/noto-sans-devanagari` (Devanagari woff2) | `5.3.0` | OFL-1.1 |

The woff2 files are copied into each template's `assets/fonts/` so a render never
depends on a system font or a webfont CDN. Devanagari coverage is deliberate:
the previous FFmpeg path used DejaVu Sans, which has **no** Devanagari glyphs, so
Hindi copy rendered as tofu boxes.

## GSAP is deliberately NOT used

HyperFrames' default animation runtime is GSAP, and its own scaffolds load it
from `cdn.jsdelivr.net`. We use neither, for two independent reasons:

1. **Licence.** `gsap@3.15.0` is published under a *"Standard 'no charge'
   license"*, which is not an OSI licence. `app/marketing/creative_os/licence.py`
   fails closed on anything it cannot classify as commercially clear, so bundling
   GSAP would have made the provider licence-blocked.
2. **No network at render time.** A CDN `<script src>` violates the hard rule
   that a production render performs no external fetches.

Templates therefore use the **CSS animation adapter**, which upstream documents
as a first-class supported runtime. Every animation carries a finite
`animation-iteration-count`; `infinite` is a determinism violation because it has
no computable end time and cannot be seeked.

## Runtime isolation

Set on every child process by `hyperframes_provider._hermetic_env()`:

`HYPERFRAMES_NO_TELEMETRY=1`, `HYPERFRAMES_NO_UPDATE_CHECK=1`,
`HYPERFRAMES_NO_FEEDBACK=1`, `HYPERFRAMES_NO_AUTO_INSTALL=1`,
`HYPERFRAMES_SKIP_SKILLS=1`, `DO_NOT_TRACK=1`, `HYPERFRAMES_API_KEY=""`.

The `cloud`, `lambda`, `cloudrun`, `publish` and `auth` subcommands are never
invoked; a test asserts they are absent from the argv.

Chrome (`chrome-headless-shell`, pinned by `@puppeteer/browsers`) is fetched
**at image-build time** by `Dockerfile.video`. Verified locally as
`win64-152.0.7928.2`; the Linux build resolves its own pinned equivalent.

## Upgrade procedure

1. Re-run the verification above for the new version — licence and archived
   status are re-checked, never assumed.
2. `npm install --save-exact hyperframes@<new>` inside `video_renderer/hyperframes`.
3. Commit BOTH `package.json` and `package-lock.json`.
4. Update `model_revision` and the pinned commit in the
   `hyperframes/hyperframes-cli` row of `app/marketing/creative_os/licence.py`,
   and the expected version in `tests/test_hyperframes_provider.py`.
5. `npx hyperframes check templates/<each>` must report 0 errors.
6. Re-render the canary and compare the ffprobe contract.
7. Rebuild `Dockerfile.video` (Chrome may also move).

## Rollback

No database migration was introduced, so rollback is configuration only:

1. `CREATIVE_PROVIDER_HYPERFRAMES_ENABLED=0`
2. Remove the tenant from `CREATIVE_HYPERFRAMES_CANARY_TENANTS`
3. Future generations route to `deterministic` (the registry's declared
   `rollback_provider`)
4. Redeploy `worker-video` **without** `deploy/compose/docker-compose.video.yml` to drop the
   toolchain image
5. Previously approved media and their immutable snapshots are untouched
