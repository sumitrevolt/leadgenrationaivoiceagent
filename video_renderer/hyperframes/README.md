# `video_renderer/hyperframes`

Bounded, pinned HTML→video rendering package for the Creative Automation OS.
Licence and upstream provenance: **`PROVENANCE.md`** (read it before upgrading).

This package renders. It does **not** decide what may be sold: the enterprise
contract, approval binding and publish gate all live in Python
(`app/marketing/creative_os/`).

## Layout

```
package.json / package-lock.json   pinned hyperframes 0.7.87 + OFL fonts
templates/<template_id>/           ONE self-contained HyperFrames project
  index.html                       the composition
  assets/base.css                  design system (local, no CDN)
  assets/fonts/*.woff2             bundled OFL fonts
```

`package-lock.json` is force-tracked past the repo's blanket `*.json` ignore (see
the `!package-lock.json` negation in the root `.gitignore`). Without it `npm ci`
in `Dockerfile.video` refuses to run and the image is not reproducible.

## Templates

| id | use | scenes | look |
|---|---|---|---|
| `beauty_luxury_offer_v1` | beauty / salon offer reel | 6 | dark editorial luxury — monogram reveal, glass cards, particles |
| `local_service_promo_v1` | local SMB services | 6 | bright editorial trust — problem→solution→proof→offer→CTA, strike-through hinge, numbered steps |
| `agency_product_launch_v1` | LeadGen AI own-brand launch | 6 | product/tech — CSS-drawn app frame, workflow nodes, metric cards |

All three are 1080×1920, 30fps, 25.4s, CSS-runtime, Devanagari-capable.

They are deliberately three different visual languages rather than one recoloured
layout: a salon, a plumber and a SaaS launch do not read as credible in the same
treatment.

Trust chips (`local_service`) and metric cards (`agency`) render **only** from an
explicitly verified list on the brand record. There is no default and no
derivation — an unproven business simply renders without them, because an
invented rating or "10,000+ customers" in a customer's ad is a false claim.

Each template is its own project directory. That is not stylistic: HyperFrames
refuses asset paths that traverse above the project root (`../shared/…` 404s in
Studio and in preview), so shared assets are bundled per template instead.

## Commands

Run from this directory. `node_modules/` is installed from the lockfile and is
never committed.

```bash
npm ci                                                  # install exact lockfile
node ./node_modules/hyperframes/bin/hyperframes.mjs doctor
node ./node_modules/hyperframes/bin/hyperframes.mjs check templates/beauty_luxury_offer_v1
node ./node_modules/hyperframes/bin/hyperframes.mjs browser ensure   # build-time only
```

`check` must report **0 errors** before a template ships.

Renders in production are invoked by
`app/marketing/creative_os/hyperframes_provider.py`, never by hand — it is what
supplies the validated manifest, the timeout, and the output path under a media
root the publish gate trusts.

## Composition contract (learned the hard way)

The first render of this template produced a 71 KB, 25-second, entirely black
video that still probed as valid 1080×1920 H.264. Four contract violations
caused it, and all four are now covered by `hyperframes check`:

1. **`<!doctype html>` must be the first line.** Without it the file is treated
   as a fragment and quirks-moded.
2. **The root element needs `data-start="0"`**, alongside `data-composition-id`,
   `data-width`, `data-height`.
3. **No `../` asset paths.** They 404 — which is what silently dropped the
   stylesheet and left every text element unstyled black-on-black.
4. **`data-no-timeline` on the root** when there is no GSAP timeline. Without
   it the producer polls 45 s for a `window.__timelines` registration that will
   never arrive, then warns `sub_timeline_readiness_timeout`.

Additionally:

- Every animation needs a **finite** `animation-iteration-count`. `infinite` has
  no computable end time, cannot be seeked, and is a determinism violation.
- A full-frame background must sit on a full-bleed **child**, never on the
  composition root — the compositor can drop the root's own `background` and
  render black.
- No `Date.now()`, no unseeded `Math.random()`, no hover/scroll state: the
  renderer seeks each frame independently, so any state that depends on having
  arrived through the previous frame desyncs.

## Adding a template

1. Copy an existing template directory (keeps the bundled fonts and base.css).
2. Bind every customer-specific value to a declared variable. Never hard-code a
   business name, price, rating, address or testimonial — an unfilled variable
   must render as an omitted block, not as invented copy.
3. Register it in `app/marketing/creative_os/hyperframes_templates.py`
   (`TEMPLATE_REGISTRY`) with its `template_version`, `scene_count`, supported
   `aspect_ratios`, declared `variables` and `required_variables`. The registry
   is an exact-match allowlist — an unregistered id can never reach Chrome.
4. `hyperframes check` → 0 errors, then render and eyeball frames.
5. Add a binding test in `tests/test_hyperframes_provider.py`.
