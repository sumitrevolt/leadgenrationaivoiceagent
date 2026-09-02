# UNITY BLUEPRINT STYLE GUIDE (2026-07-12)

> Rule: Unity invents NO new color system. Every Unity material/UI token maps to an existing
> project token. Two visual languages exist in the codebase — Unity uses BOTH, by scene.

## 1. Which palette where

| Scene / mode | Palette | Source of truth |
|---|---|---|
| `AdminBlueprintOffice` (blueprint/command-center feel) | DARK "Blueprint" | inline `:root` in `frontend/control_center.html:10–16` (same hexes hardcoded in `explorer.html`, `control_center_graph.html`) |
| `CustomerBlueprintOffice` (friendly office feel) | LIGHT "AI Office" | `frontend/design-system/tokens/colors.css` + `tokens/ai-office.css` |
| Node/agent/room STATUS colors (both scenes) | Status set | `control_center_graph.html:116–120` legend + `colors.css:45–48` |

## 2. Dark "Blueprint" mapping (admin scene)

| Existing CSS token | Hex | Unity usage |
|---|---|---|
| `--bg` | `#0a0a0c` | Camera clear color / blueprint floor base material |
| dotted grid (`radial-gradient(circle,#1a1d26 1px,transparent 1px)` 24–26px) | `#1a1d26` | Tiling grid texture on floor plane (one 26px-cell dot texture, repeat) |
| `--panel` / `--panel2` / `--card` | `#111113` / `#13141a` / `#161618` | Room floor fill / BlueprintPanel background / card material |
| `--bd` / `--bd2` | `#1e2028` / `#2d3748` | Room outline (thin), wall lines |
| `--tx` / `--mut` / `--mut2` | `#e2e8f0` / `#64748b` / `#475569` | Label text / secondary text / faint text |
| `--amber` (signature accent) | `#f59e0b` | Selected room outline glow, active path, focus ring, brand dot |
| `--ai` | `#a855f7` | AI/loop nodes, agent "thinking" tint |
| `--idle` | `#64748b` | Offline/inactive rooms & agents |
| explorer `TYPE_COLORS` (explorer.html:1211) | platform `#60a5fa`, marketing `#3b82f6`, voice `#fb923c`, ai `#818cf8`, data `#22d3ee`, external `#4ade80`, monitor `#fbbf24`, loop `#e879f9`, gap `#f87171` | Workflow-Mode edge/node tints per node type |
| Room stroke colors (office_map.html:873–881) | coordinator `#8b5cf6`, lead_lab `#0ea5e9`, sales_crm `#f97316`, voice `#3b82f6`, marketing `#ec4899`, qa `#eab308`, engineering `#10b981`, finance `#64748b` | Per-room outline glow color (keep 1:1 with 2D map so minimap matches) |

## 3. Status colors (canonical, BOTH scenes — never invent new ones)

| State | Hex | Existing source | Unity prefab |
|---|---|---|---|
| healthy / working | `#22c55e` | `--healthy` (graph legend) / `--ao-live` | StatusBeacon green |
| processing / working-active | `#3b82f6` | `--processing` / `--info` | StatusBeacon blue pulse (bounded anim) |
| waiting / blocked-soft / degraded | `#eab308` | `--waiting` / `--warning #d97706` (light) | StatusBeacon yellow |
| retry | `#f97316` | `--retry` | StatusBeacon orange |
| failed / critical | `#ef4444` | `--failed` / `--danger #b91c1c` (light) | StatusBeacon red + AlertMarker |
| offline / inactive | `#64748b` | `--idle` / `--muted` | StatusBeacon grey, no anim |

Agent status vocabulary (Phase 13): `working / waiting / reviewing / blocked / failed / offline`
→ map to processing / waiting / waiting(+icon) / waiting(+lock icon) / failed / idle. No new hexes.

## 4. Light "AI Office" mapping (customer scene)

| Existing token | Hex | Unity usage |
|---|---|---|
| `--grad-brand` | `linear-gradient(135deg,#4f46e5,#7c3aed)` | Reception branding wall, primary CTA buttons |
| `--indigo-600` / `--violet-500` | `#4f46e5` / `#7c3aed` | Primary/secondary accents |
| `--bg` / `--bg-soft` | `#ffffff` / `#f6f6fb` | Customer scene ambient / floor |
| `--line` | `#e8e8f2` | Room dividers |
| `--ao-sb-top/-bot` (navy sidebar) | `#080c18` / `#0d1629` | Minimap/panel chrome |
| `--hot/--warm/--cold` | `#ef4444/#f59e0b/#3b82f6` | Lead-temperature markers (reports room) |
| office_map inline `:root` (office_map.html:14–18) | `--brand #6d28d9`, `--ok #10b981`, `--warn #f59e0b`, `--err #ef4444` | Keep parity with the 2D fallback the customer may toggle to |

## 5. Typography & motion

- Fonts: reuse the design-system font tokens (`tokens/fonts.css` / `typography.css`); monospace for
  file-path/technical labels (matches explorer). Unity: one clean sans TMP font + one mono TMP font.
- Motion budget (Phase 23): NO continuous per-agent animation. Allowed: status-beacon pulse (only
  `processing`), camera eases on selection, standup-walk equivalent max 1×/hour (as in office_map).
- FORBIDDEN (Phase 4): cartoon characters, FPS controls, bright metaverse gradients, decorative
  rooms without real data, fake activity animations. platform_dial room MUST render HARD OFF state
  (red/grey lock), never a "ready" green.

## 6. Formula

```
office_hq ROOM_DEFS geometry (via snapshot.rooms)
+ office_map room stroke colors
+ control_center dark tokens (admin) / ai-office light tokens (customer)
+ graph status legend for ALL states
+ LeadGen AI branding (logo from frontend/website assets)
= Unity look. Zero invented tokens.
```
