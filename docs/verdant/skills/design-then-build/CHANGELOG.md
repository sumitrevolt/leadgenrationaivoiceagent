# Changelog

## 11.9.6 — 2026-08-10

- Replace the stale fixed Opus version list in user-facing Design Then Build guidance with the most capable Claude Opus model currently available in the app.


## 11.9.4 — 2026-07-14

- Re-export `icon-dark.png` / `icon-light.png` as RGBA with transparent rounded corners; remove the baked-in black corner background that showed as a dark border in the skills list.

## 11.9.2 — 2026-06-24

- Remove number-picking language from stage-1 style selection prompts.
- Restore the neutral `Let the user choose` wording and ask generally when the user has not chosen.

## 11.9.1 — 2026-06-24

- Relax style exploration count docs: `use_styles=true` no longer implies exactly 4 images.
- Keep default stage-1 exploration at 4 directions, but honor explicit user requests for 1–4 style directions by setting `n` and `images.length` to the requested count.
- Require `use_styles=true` for all style direction generation regardless of count.

## 11.9.0 — 2026-06-23

- Sync image tool examples with the current public schema: remove the `model` parameter from `create_image` and `edit_image` calls.
- Update stage-1 style exploration docs so each image item carries only `prompt`, `title`, and `palettes`; reference-anchored items also carry `image_path`.
- Keep `manager-skills/design-then-build` in lockstep with the builtin skill copy.

## 11.8.0 — 2026-06-16

- Correct the tool-call migration docs after fenji confirmation: `use_styles` and `use_picture` are workflow intent flags supported by both `create_image` and `edit_image`.
- Stage 1 keeps two valid paths: no-reference style exploration uses `create_image + use_styles=true`; reference-anchored style exploration uses `edit_image + use_styles=true + image_path`.
- Stage 3 is explicitly the fenji selected-comp flow only: generate per-page comps via `edit_image + use_picture=true + image_path + title`. Do not document a no-reference `create_image` Stage 3 branch.
- Keep normal follow-up assets and reference-based asset edits flag-free: no `use_styles`, no `use_picture`.

---

## 11.7.0 — 2026-06-12

Migrate from bash CLI commands to native tool calls for all image generation and editing.

- Replace all `verdent-image generate` / `verdent-image edit` bash commands with direct `create_image` / `edit_image` tool calls throughout the workflow.
- Stage 1: 4 parallel bash commands → single `create_image` batch call with `n=4`, `use_styles=true`, and an `images` array; each element has its own `prompt`, `title`, and `palettes`.
- Stage 2: follow-up asset generation via `edit_image` with `image_path` in each `images[i]` instead of `--image` CLI flag.
- Stage 3: per-page comp generation follows the selected-comp reference flow via `edit_image` with `use_picture=true`, `image_path`, and `title` in each `images[i]`.
- `use_picture` and `use_styles` are supported by both `create_image` and `edit_image`. `use_picture` and `use_styles` are mutually exclusive. On both image tools, `title` must be paired with `use_picture=true` or `use_styles=true`; `palettes` must be paired with `use_styles=true`.
- Add `use_picture`/`use_styles` restriction clarification in `restoration.md` and `high-fidelity-assets.md`: both are reserved for workflow-level style directions and page comps, not ordinary assets.
- Update `examples/comp-prompt.md` from bash command format to JSON tool-call format.
- Update `references/software-saas-references.md` to use `create_image` / `edit_image` terminology.

---

## 11.6.0 — 2026-06-04

- Branch Stage 4 deployment guidance on `Verdent surface`: recommend Vercel for `desktop-app`, and recommend starting the project then clicking the top-right **Publish** button for `cloud-web` / cloud agents.
- Keep all deployment and publish actions behind explicit user confirmation.
- Change Manager Worker dispatch from `claude-opus-4-7` to `claude-opus-4-6`.

---

## 11.5.1 — 2026-06-03

- Keep `--palette` in design direction generation commands for workflow metadata, and require the same three-color system to be written directly in each image prompt.

## 11.5.0 — 2026-05-30

- Restrict image intent flags: `--use-styles` is only for stage-1 style direction images, `--use-picture` is only for stage-3 complete page/screen design comps, and normal assets/component images/illustrations/supporting artwork must omit both.

---

## 11.2.0 — 2026-05-30

- Unify image output paths to `<project-root>/verdent-design/{images,icons,logo}` (previously `assets/images/`, `assets/icons/`, `assets/logo/`).
- Stage 2 (primary-restoration): generated follow-up assets no longer pass `--use-picture` — it is only for design comp output, not normal asset generation.
- Stage 3 (extended-pages): restore `--use-picture` on per-page comp generation commands, since page comps are design deliverables.
- Clarify `--use-picture` and `--use-styles` are both optional intent flags; omit both for plain asset generation.

---

## 11.1.0 — 2026-05-30

Theme for this round: quality baseline + teaching guidance. Refine the examples and rules away from tendencies that models may copy verbatim, such as retro styling, high density, and presentation-board compositions, into product interface generation guidance that is contemporary-first, content-restrained, uses real UI colors, and allows free hero layouts.

- De-retro: changed the example content in `examples/comp-prompt.md` from “retro era anchor-led” to “contemporary-first”; updated the filled template to a contemporary direction (Geist/Inter, omit the era line); changed the four parallel command examples to three contemporary directions plus at most one retro comparison direction (Memphis); added contemporary-first guidance. The root cause was that models copied the examples as templates.
- Restrained content density: refined the wording of “core functional modules” in rule 5 of `references/style-exploration.md` (show key modules/main views, not every feature crammed into one screen); added a “restrained content density” rule to Page design quality (one screen focuses on one primary task/main view, 3–5 primary modules, dashboards still need whitespace, and when there is too much content, split screens before compressing density); added an over-dense everything-on-one-screen anti-example to Common mistakes.
- Do not draw the color palette as swatches: added a constraint to rule 10—the three-color palette is only a color-usage instruction and may appear only through actual UI element colors; never draw the palette anywhere in the generated image (including inside the interface, presentation-board whitespace, canvas edges, margins, or beside mockups), explicitly calling out the typical violation of “vertical three color blocks on the canvas side + hex labels”; added the corresponding anti-example to Common mistakes; synchronized COLOR SYSTEM/AVOID in `comp-prompt.md`.
- Rule 4 does not restrict hero layouts: removed negative examples such as “single big decorative headline” that could mistakenly penalize hero composition; changed the constraint to whether the whole comp is a usable product interface, and explicitly encouraged bold/oversized/highly decorative hero typography (Bold hero layouts are strongly welcome); adjusted Common mistakes accordingly to constrain the overall result, not the hero.

---

## 11.0.5 — 2026-05-30

- Removed `references/software-saas-references.md` — it was an orphan file never referenced by any stage in `SKILL.md`; its unique value (reference-anchoring to real sites) overlapped with `style-exploration.md` after the loosening pass.

---

## 11.0.4 — 2026-05-30

Theme for this round: adjust the skill from “hard constraints on creativity” to “quality baseline only + teaching guidance”, removing constraints that induce retro/poster/website/fixed-alignment/fixed-canvas-size outputs, so the image model can freely explore each direction.

- Relax `references/style-exploration.md`: remove the over-specific landing-page-vs-app split and related Common Mistakes row, generalize website-only wording to product UI across web/app/mobile/dashboard, remove era reference from the required variation axes, while keeping real-UI-not-poster, product-type matching, and front-facing flat-view guidance.
- Soften `examples/comp-prompt.md`: make REFERENCE ERA/MOVEMENT optional with an anti-retro warning, remove the centered-hero restriction from AVOID lists, frame AVOID items as “unless intentionally chosen”, mark placeholders as freely replaceable non-defaults, soften the “missing sections create AI defaults” warning, and make SUBJECT examples neutral product main screens.
- Rework `references/software-saas-references.md` from hard constraints into teaching guidance: recommend edit mode when it improves quality, ask abstract terms to pair with named tokens, remove board/canvas and fixed-size mandates, while preserving the real-site quality bar, diversity advice, mini-spec, and shortlist table.
- Update `references/restoration.md` so board/canvas stripping applies only when the stage-1 comp used a presentation board; full-bleed, cropped, multi-screen, and other open presentations should be restored as shown.

---

## 11.0.3 — 2026-05-30

- Remove all output-size constraints and unsupported `create-image` flags from the workflow docs to match the real `verdent-image generate` CLI (supported sizes: 1024x1024 / 1024x1536 / 1536x1024 / auto; supported flags include `--prompt` / `--model` / `--n` / `--size` / `--quality` / `--output-format` / `--background` / `--use-picture`, plus `--title` only for `--use-styles` or `--use-picture` commands).
- Drop fixed canvas dimensions (portrait ratios, mockup width percentages, viewport-count limits) from `SKILL.md`, `references/style-exploration.md`, `references/software-saas-references.md`, `references/restoration.md`, and `examples/comp-prompt.md`.
- Replace the per-comp style-card metadata flags with a plain per-comp three-color palette commitment expressed in each prompt.

---

## 11.0.2 — 2026-05-29

- Unify all `verdent-image generate` / `verdent-image edit` commands to use ordinary `bash` tool calls instead of `bash_background`.
- Reserve `bash_background` exclusively for long-running dev servers (e.g. `npm run dev`).
- Update `SKILL.md` top-level rule and `references/restoration.md` execution guidance accordingly.

---

## 11.0.1 — 2026-05-28

- Require `create-image` per-comp palette metadata for style exploration outputs: one clear three-color color system per comp.
- Define palette usage as one set of exactly three `#RRGGBB` colors, aligned with one comp's color system.
- Require follow-up page comp generation after user selection to use `--use-picture` with page-specific `--title`; ordinary asset generation must omit `--use-picture` and `--use-styles`.
- Update the style-comp example command to include the new candidate-card metadata.

---

## 3.0.5 — 2026-05-28

Desktop-app deploy path switched back to Vercel; cloud-web path unchanged.

- For `Verdent surface: desktop-app`, recommend **Vercel** deployment instead of Verdent cloud.
- Recommendation copy simplified to: "All frontend pages are ready. Would you like to deploy them online? I recommend deploying with Vercel."
- After user confirmation, the model deploys the project to Vercel directly. Do not list GitHub/Vercel step-by-step UI instructions.
- For `Verdent surface: cloud-web`, the built-in Publish flow remains unchanged (start project → click top-right Publish → recommend Verdent app + Verdent manager afterward).
- Supersedes the 3.0.1 entry "Remove Vercel from the default deployment recommendation path" for the desktop-app branch only.

## 3.0.1 — 2026-05-26

Deploy guidance now follows the user's Verdent environment instead of giving a generic hosting list.

- If the user is in Verdent app, recommend: upload to GitHub → open `https://dev-cloud.verdent.ai/` → connect GitHub → open project → click top-right **Publish**.
- If the user is already in Verdent cloud, recommend: start the project → click top-right **Publish**.
- Add a follow-up recommendation for Verdent cloud users to download Verdent app from `https://www.verdent.ai/` and keep iterating with **Verdent manager**.
- Remove Vercel from the default deployment recommendation path.
- Tighten the consent rule: no GitHub connection, cloud deploy flow, or publish action without explicit user confirmation.

## 2.2.1 — 2026-05-26

Restoration fidelity hardening. Rewrote rule 6 in `references/restoration.md`.

- Layout must follow the comp: section order, column ratios, key element positions; no adding/removing sections.
- Color must be sampled from the comp into Tailwind v4 `@theme`; framework default palettes (shadcn neutral, Tailwind default blue, recharts/chart.js defaults) are forbidden; light/dark base tone follows the comp.
- Typography and spacing follow comp proportions; no default framework scales.
- Side-by-side self-check against the comp before reporting done.

---

## 2.2.0 — 2026-05-26

Manager dispatch hard rules. Adds a new top-level section `## Manager dispatch rules (hard rule, Manager only)` to `SKILL.md`. Rules apply only when Manager (the orchestrator) is the caller; ignored when this skill runs under a single agent.

- **Rule 1 — verbatim prompt forwarding.** When Manager dispatches a step to a Worker, the user's original prompt MUST be passed through unchanged. No rewriting, summarizing, "prompt optimization", or paraphrasing.
- **Rule 2 — `claude-opus-4-7` for ALL frontend restoration.** Any task turning an approved comp into runnable frontend code MUST be dispatched with `--model claude-opus-4-7`.
- **Rule 3 — `gpt-5.5` for ALL design-asset and image generation.** Any task whose primary work calls `create-image` MUST be dispatched with `--model gpt-5.5`.
- **Rule 4 — new task on model switch.** Cross-model handoffs MUST use a fresh `task create --model <new>`; reusing the existing task with `message send --model` is forbidden.

---

## 2.1.0 — 2026-05-21

Frontend fidelity hardening on top of the remote `design-then-build` version checked from family.verdent.ai.

- Require motion restoration: entry, scroll reveal, hover/focus/active, open/close states, and reduced-motion handling.
- Require style-carrying guidance assets: onboarding visuals, empty states, product mockups, annotations, textures, and branded illustrations.
- Add a no-emoji-by-default rule for UI copy, buttons, statuses, empty states, and icon substitutes.
- Expand high-fidelity assets with cutout/background-removal pipeline and bugcase checks: fake transparency, halos, hair/glass damage, eaten edges, leftover backgrounds, and shadow mismatch.
- Tighten single-color icon handling: SVG only, `currentColor`, stroke/cap/join matching, and multi-size clarity checks.
- Add frontend-complete handoff: open preview, summarize checks, then ask whether to test, continue features, or publish/deploy; never publish/deploy without explicit confirmation.

---

## 2.0.0 — 2025

Full structural rewrite for [writing-skills](https://github.com/obra/superpowers/tree/main/skills/writing-skills) compliance.

**Renamed** `design-first-product` → `design-then-build`. The new name:
- Is verb-first and active voice (writing-skills naming guideline).
- Is plainly readable by product builders (not engineering jargon).
- Captures the full arc: design **then** build, not just "design first".

**Restructured** single 357-line `SKILL.md` into a layered skill:
- `SKILL.md` (~280 lines) — overview, when-to-use, decision tree, hard rules, anti-AI bar, common-mistakes table, stage cheatsheets with reference-file pointers.
- `references/style-exploration.md` — full stage-1 rules, 4-direction matrix, gates.
- `references/pages-and-spec.md` — full stage-2 rules, fidelity question.
- `references/restoration.md` — full stage-3 standard fidelity + responsive hard rules.
- `references/high-fidelity-assets.md` — full HF pipeline (images / icons / logo / manifest).
- `references/continued-build.md` — full stage-4 workflow.
- `examples/comp-prompt.md` — one complete `create-image` skill prompt covering all seven required sections.

**Description rewritten** to follow CSO best practice: triggering conditions only, no workflow summary, includes negative triggers (snake-style trivial games, fully-specified briefs, "skip design").

**`metadata.version` retained** and bumped to `2.0.0` (structural break).

**Phase numbers renamed** to verb-first stage names:
- `phase 1` → `style-exploration`
- `phase 2` → `pages-and-spec`
- `phase 3` → `restoration` / `high-fidelity-assets`
- `phase 4` → `continued-build`

**Each reference file ends with a Common Mistakes table** distilled from the original "do NOT" rules, explaining why each fails and the fix.

**Cross-skill reference** to `create-image` now uses the explicit `**REQUIRED SUB-SKILL:**` marker, not natural-language prose.

---

## 1.x history (pre-rewrite, original `design-first-product`)

- **1.2.12** — In continued development, clarify that any module time estimate requested by the user should estimate AI development time rather than human team development time.
- **1.2.11** — In the product requirements diagram rules, allow the image color style to stay consistent with the product's design style.
- **1.2.10** — Remove the follow-up question about common supporting screens after the user picks a design direction.
- **1.2.9** — Update When to Use: position the skill as best for 0-to-1 product work, and limit game usage to more complex game projects rather than simple games like snake.
- **1.2.8** — When a project has a spec image, require a visible progress update after each larger development module by marking completed logic as done on the spec image and showing the updated image or HTML view to the user.
- **1.2.7** — In continued development, require the implementation to match the product type shown in the design comps, such as building a mobile app for mobile app designs instead of turning them into a website.
- **1.2.6** — Replace the opening summary line with a more accurate one-sentence description of the full workflow: design direction, page design, product spec, code restoration, and continued development.
- **1.2.5** — After the user picks a design direction, require a simple follow-up question about common supporting screens such as sign in, sign up, password reset, onboarding, profile, and settings. (Reverted in 1.2.10.)
- **1.2.4** — Add a required question after design confirmation: ask whether the user wants style-matched restoration or high-precision restoration, then choose Standard fidelity or High fidelity based on that answer.
- **1.2.3** — Add an explicit skill-wide rule that all user-facing wording must stay simple, easy to understand, and light on technical language.
- **1.2.2** — Add a user communication rule: do not mention phase numbers when talking to the user. Say what is happening now and what comes next in simple language instead.
- **1.2.1** — Remove Chinese from the skill and simplify user-facing wording in Phase 4 so prompts stay easy to understand and low on technical jargon.
- **1.2.0** — Rewrite Phase 4 to focus on a three-part finish: frontend restoration, backend task breakdown, and wrap-up for analytics, testing, and deployment. Add clear guidance for Google Fonts matching, automatically opening the frontend preview, identifying the user's technical background, guiding PostHog analytics setup, using Playwright for testing, and wrapping up with GitHub and deployment guidance.
