# Agent Registry (GENERATED — do not hand-edit)

> **GENERATED FILE.** Source of truth = `app/platform/team.py → STAFF`.
> Regenerate with: `python scripts/gen_agent_registry.py`.
> A hand-edited copy of this doc WILL drift — that is exactly why
> `docs/AGENT_REGISTRY.md` went stale at 19-vs-31 (see ARCH §8 R2).
> **Agent count:** 31

Evidence label: `CODE-PRESENT` (derived from `team.py → STAFF` at generation time).

| ID | Name | Product | Title | Schedule |
|----|------|---------|-------|----------|
| `ananya` | Ananya | voice | Appointment Booker | On-demand (booking campaigns / callbacks) |
| `anika` | Anika | marketing | Cadence Manager | Roz scheduled (team_scheduler.py cadence.run_due()) |
| `arjun` | Arjun | voice | QA Engineer | Roz raat 2:30 + on-demand |
| `arnav` | Arnav | platform | Security / Compliance | Daily (gated SECURITY_AGENT) + on-demand posture report |
| `arya` | Arya | platform | MCP Engineer | Hourly (gated MCP_ENGINEER) + on-demand /api/platform/mcp/health |
| `aryan` | Aryan | platform | Dependency / Supply-chain Engineer | Weekly Sun 04:30 IST (gated DEPS_AGENT) |
| `dev` | Dev | marketing | Data Analyst | Har naye client pe auto |
| `diya` | Diya | platform | Data-Integrity Engineer | Daily 10:30 IST (gated DATA_INTEGRITY_AGENT) |
| `guru` | Guru | platform | Skill Trainer | Roz (trainer job ke saath, gated SKILL_PACK) |
| `hermes` | Hermes | platform | Infrastructure Handler | Har ghante (watchdog, gated INFRA_HANDLER) + pulse rotation |
| `ira` | Ira | marketing | Journey Automation Manager | Event-driven (jab bhi koi wired hook trigger fire kare) |
| `isha` | Isha | marketing | Marketing Executive | On-demand (marketing) |
| `kabir` | Kabir | platform | DB Reliability Engineer | Daily 10:00 IST (gated DBRE_AGENT) |
| `kavya` | Kavya | platform | Ops Monitor | Har ghante + on-demand |
| `kiran` | Kiran | marketing | Campaign Optimizer | Weekly + threshold (gated CAMPAIGN_OPTIMIZER) |
| `lekha` | Lekha | voice | Call Analytics Lead | Roz subah + on-demand (/api/admin/web-calls/kpis) |
| `manager` | Boss | platform | Manager (Supervisor) | On-demand (har /api/agents/run pe) |
| `meera` | Meera | voice | Trainer | Roz raat 3:00 + on-demand |
| `neha` | Neha | marketing | Pipeline Ops | Roz 11:00 IST pipeline job |
| `nikhil` | Nikhil | platform | Revenue Ops | Roz (digest/content jobs ke saath) |
| `pranav` | Pranav | platform | SRE / Reliability | Har ghante (gated SRE_AGENT) + daily DR-readiness summary |
| `priya` | Priya | marketing | CRM Sync Specialist | On-demand (har qualified lead pe, jab client ne CRM connect kiya ho) |
| `raksha` | Raksha | voice | Human Escalation Manager | On-demand (live calls) |
| `ravi` | Ravi | marketing | SEO Scout | Roz blog ke saath + Monday SEO batch |
| `riya` | Riya | voice | AI Receptionist | On-demand (inbound / mini-site widget) |
| `rohan` | Rohan | marketing | Leads Manager | On-demand (campaigns) |
| `swara` | Swara | voice | Telecaller | On-demand (calls/demos) |
| `tara` | Tara | voice | Voice Infra Ops | Har ghante (watchdog ke saath) |
| `vidya` | Vidya | platform | FinOps / Cost | Roz (daily margin digest, gated FINOPS_AGENT) |
| `vikram` | Vikram | platform | Code Upgrader | Har ghante (watchdog ke saath, gated CODE_UPGRADER) |
| `zara` | Zara | marketing | Social Media Manager | Queue-driven (jab bhi approved content publish ke liye ready ho) |

**Total: 31 agents.**
