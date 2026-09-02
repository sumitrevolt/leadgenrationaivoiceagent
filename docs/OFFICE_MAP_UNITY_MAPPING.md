# OFFICE MAP → UNITY MAPPING (2026-07-12)

> The existing office map (`frontend/office_map.html`, `/app/office`) DRIVES Unity placement.
> Rooms are never placed arbitrarily. The 2D map remains the fully-usable lightweight fallback.

## 1. Canonical floor plan (source: office_map.html `OFFICE.ROOMS` lines 873–881; ids match backend `office_hq.ROOM_DEFS`)

World: 1200×820 (2D px). Unity mapping: 1 px = 0.025 m → 30 m × 20.5 m floor, X→X, Y→Z, y-up.

| Room id | Label | 2D x,y,w,h | Unity center (x, z) m | Unity size (w, d) m | Stroke |
|---|---|---|---|---|---|
| `coordinator` | 🧑‍💼 Coordinator Room | 0,0,1200,120 | (15.0, 1.5) | 30.0 × 3.0 | `#8b5cf6` |
| `lead_lab` | 🧹 Data / Lead Lab | 0,120,300,350 | (3.75, 7.375) | 7.5 × 8.75 | `#0ea5e9` |
| `sales_crm` | 🤝 Sales / CRM | 300,120,300,350 | (11.25, 7.375) | 7.5 × 8.75 | `#f97316` |
| `voice_team` | 📞 Voice Team | 600,120,300,350 | (18.75, 7.375) | 7.5 × 8.75 | `#3b82f6` |
| `marketing_team` | 📣 Marketing Team | 900,120,300,350 | (26.25, 7.375) | 7.5 × 8.75 | `#ec4899` |
| `qa_audit` | 🧪 QA / Audit | 0,470,250,350 | (3.125, 16.125) | 6.25 × 8.75 | `#eab308` |
| `platform_engineering` | 🛠️ Platform / Engineering | 250,470,700,350 | (15.0, 16.125) | 17.5 × 8.75 | `#10b981` |
| `admin_finance` | 💰 Admin / Finance | 950,470,250,350 | (28.125, 16.125) | 6.25 × 8.75 | `#64748b` |

Adjacency semantics preserved: Coordinator = full-width top strip routing work to the mid-row
(lead_lab → sales_crm → voice_team → marketing_team = pipeline flow left→right); bottom row =
QA / Engineering / Finance support layer. Workflow paths in Unity follow this same left→right flow
(matches `PIPELINE_STAGE_META`, office_hq.py:225–238, 12 stages).

Ops-view rooms from COMMAND_CENTER_UNITY_MAPPING.md §1 (reception/delivery/approvals/billing/
compliance/server_room/support_desk) are PANELS/ZONES rendered inside these 8 physical rooms
(e.g. reception + billing inside `admin_finance`; server_room + compliance inside
`platform_engineering`; delivery + approvals inside `coordinator` strip) — the floor plan itself
adds NO new rooms, so the minimap stays 1:1 with the existing 2D map.

## 2. Agents

- Roster: `snapshot.agents[]` (31 staff; `MEMBER_ROOM` office_hq.py:62–101 assigns room).
- Desk slots: Unity generates N desk anchors per room (grid inside room bounds, same approach as
  office_map desk layout). Desk binding = stable hash(agent_key) → slot index, so desks don't
  shuffle between polls.
- Count-driven props (REAL data only, mirroring 2D map): DLQ pile (dlq depth), reception tray
  (hot-queue count). No decorative fake props.

## 3. Three forms of the map (Phase 7)

1. **Unity floor plan** — table above, navigable, camera click-to-focus.
2. **Blueprint minimap** — top-down orthographic render of the SAME room rects + status dots;
   visually matches `/app/explorer` dark grid style (see style guide §2).
3. **Lightweight fallback** — the EXISTING `/app/office` Phaser map, untouched, default mode.
   Triggers: `UNITY_VIRTUAL_OFFICE_ENABLED` off · WebGL2 unsupported · `deviceMemory < 4` GB ·
   `?mode=map` · Unity loader error/timeout (20s) · `prefers-reduced-motion` (accessibility).
   Fallback message: "Your Virtual Office is available in Lightweight Mode." — never a blank canvas.

## 4. Customer journey map (customer scene)

Source: customer_dashboard views + delivery pipeline:
`Setup → Brand → Content → Approval → Social Delivery → Reports`
→ 6 zones on a simplified single-row floor (reuses light palette). Data:
`GET /api/customer/office` + `/api/customer/dashboard` + `/delivery-proof` + `/approvals/pending`
+ `/social/accounts` (all `require_customer`, tenant derived server-side). No customer selector.

## 5. Explorer graph reuse

Workflow/Infrastructure modes overlay: node dataset + hand-authored positions from
`frontend/explorer.html` `NODES`/`edges` (or ELK layout via the L2 graph). Unity renders these as a
wall-projection "system map" inside `platform_engineering` (same iframe content the 2D office embeds
via `/app/control-center/graph?view=automation`, office_map.html:3178) — in Unity this remains an
HTML overlay through the shell, NOT re-modeled meshes.
