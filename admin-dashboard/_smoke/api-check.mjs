var __defProp = Object.defineProperty;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __esm = (fn, res) => function __init() {
  return fn && (res = (0, fn[__getOwnPropNames(fn)[0]])(fn = 0)), res;
};
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};

// src/api/seed.ts
function mulberry32(seed) {
  let a = seed >>> 0;
  return function rand2() {
    a = a + 1831565813 >>> 0;
    let t = a;
    t = Math.imul(t ^ t >>> 15, t | 1);
    t ^= t + Math.imul(t ^ t >>> 7, t | 61);
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
function isoDaysAgo(days, hourJitter = true) {
  const d = /* @__PURE__ */ new Date();
  d.setDate(d.getDate() - days);
  if (hourJitter) {
    d.setHours(int(9, 20), int(0, 59), int(0, 59), 0);
  }
  return d.toISOString();
}
function makeLead(i) {
  const niche = pick(NICHES);
  const loc = pick(CITIES);
  const first = pick(FIRST);
  const last = pick(LAST);
  const businessName = `${pick(NICHE_PREFIX[niche])} ${pick(NICHE_SUFFIX[niche])}`;
  const status = pick(STATUSES);
  const createdDaysAgo = int(0, 89);
  const statusScore = {
    new: int(20, 45),
    enriched: int(35, 60),
    contacted: int(45, 72),
    qualified: int(70, 88),
    nurturing: int(50, 70),
    converted: int(85, 99),
    disqualified: int(5, 25)
  };
  const score = statusScore[status];
  const temperature = score >= 72 ? "hot" : score >= 45 ? "warm" : "cold";
  const contacted = status === "new" || status === "enriched" ? null : isoDaysAgo(int(0, 20));
  const slug = businessName.toLowerCase().replace(/[^a-z0-9]+/g, "");
  return {
    id: `LD-${String(1e3 + i)}`,
    name: `${first} ${last}`,
    businessName,
    phone: `9${int(1e8, 999999999)}`,
    email: `${first.toLowerCase()}.${last.toLowerCase()}@${slug.slice(0, 12)}.in`,
    city: loc.city,
    state: loc.state,
    niche,
    source: pick(SOURCES),
    status,
    temperature,
    score,
    owner: pick(OWNERS),
    notes: chance(0.65) ? pick(NOTES) : "",
    lastContactedAt: contacted,
    createdAt: isoDaysAgo(createdDaysAgo),
    updatedAt: isoDaysAgo(Math.max(0, createdDaysAgo - int(0, 5)))
  };
}
function buildLeads(count = 248) {
  const leads = Array.from({ length: count }, (_, i) => makeLead(i));
  const dupes = Math.round(count * 0.03);
  for (let i = 0; i < dupes; i++) {
    const src = leads[int(0, leads.length - 1)];
    leads.push({
      ...src,
      id: `LD-${9e3 + i}`,
      createdAt: isoDaysAgo(int(0, 89)),
      updatedAt: isoDaysAgo(int(0, 20))
    });
  }
  return leads;
}
function sentimentFor(intent) {
  if (intent === "interested") return chance(0.85) ? "positive" : "neutral";
  if (intent === "callback") return chance(0.55) ? "positive" : "neutral";
  if (intent === "not_interested") return chance(0.7) ? "negative" : "neutral";
  if (intent === "wrong_number") return "neutral";
  return chance(0.5) ? "neutral" : "positive";
}
function buildCalls(leads, count = 600) {
  const calls2 = [];
  for (let i = 0; i < count; i++) {
    const lead = pick(leads);
    const outcome = pick(OUTCOMES);
    const connected = outcome === "connected" || outcome === "scheduled";
    const durationSec = connected ? int(15, 140) : int(0, 18);
    const intent = connected ? pick(INTENTS) : outcome === "failed" ? "unknown" : "unknown";
    const startedAt = isoDaysAgo(int(0, 29));
    calls2.push({
      id: `CL-${String(5e4 + i)}`,
      leadId: lead.id,
      leadName: lead.name,
      businessName: lead.businessName,
      direction: chance(0.82) ? "outbound" : "inbound",
      outcome,
      intent,
      sentiment: sentimentFor(intent),
      durationSec,
      costInr: connected ? Number((durationSec / 60 * 1.9).toFixed(2)) : 0,
      transcript: connected ? pick(TRANSCRIPTS) : "",
      startedAt
    });
  }
  return calls2.sort((a, b) => +new Date(b.startedAt) - +new Date(a.startedAt));
}
var rand, pick, int, chance, FIRST, LAST, CITIES, NICHE_PREFIX, NICHE_SUFFIX, NICHES, SOURCES, OWNERS, NOTES, STATUSES, OUTCOMES, INTENTS, TRANSCRIPTS;
var init_seed = __esm({
  "src/api/seed.ts"() {
    "use strict";
    rand = mulberry32(20260831);
    pick = (arr) => arr[Math.floor(rand() * arr.length)];
    int = (min, max) => Math.floor(rand() * (max - min + 1)) + min;
    chance = (p) => rand() < p;
    FIRST = [
      "Aarav",
      "Vivaan",
      "Aditya",
      "Vihaan",
      "Arjun",
      "Sai",
      "Reyansh",
      "Ayaan",
      "Krishna",
      "Ishaan",
      "Ananya",
      "Diya",
      "Isha",
      "Kavya",
      "Meera",
      "Sara",
      "Pooja",
      "Neha",
      "Riya",
      "Anika",
      "Rohan",
      "Karan",
      "Nikhil",
      "Siddharth",
      "Manish",
      "Deepak",
      "Priya",
      "Sneha",
      "Tanvi",
      "Nisha"
    ];
    LAST = [
      "Sharma",
      "Verma",
      "Gupta",
      "Mehta",
      "Patel",
      "Reddy",
      "Nair",
      "Iyer",
      "Joshi",
      "Kulkarni",
      "Singh",
      "Yadav",
      "Mishra",
      "Chawla",
      "Bhatia",
      "Sethi",
      "Rane",
      "Desai",
      "Kaur",
      "Malhotra"
    ];
    CITIES = [
      { city: "Mumbai", state: "Maharashtra" },
      { city: "Pune", state: "Maharashtra" },
      { city: "Bengaluru", state: "Karnataka" },
      { city: "Delhi", state: "Delhi" },
      { city: "Hyderabad", state: "Telangana" },
      { city: "Chennai", state: "Tamil Nadu" },
      { city: "Ahmedabad", state: "Gujarat" },
      { city: "Jaipur", state: "Rajasthan" },
      { city: "Kolkata", state: "West Bengal" },
      { city: "Lucknow", state: "Uttar Pradesh" },
      { city: "Indore", state: "Madhya Pradesh" },
      { city: "Surat", state: "Gujarat" }
    ];
    NICHE_PREFIX = {
      salon: ["Glow", "Luxe", "Mirror", "Blush", "Radiant", "Styles", "Crown"],
      clinic: ["Care", "Health", "Arogya", "Vital", "Smile", "Prime", "Sanjeevani"],
      gym: ["Iron", "Pulse", "Titan", "Core", "Beast", "Apex", "Sweat"],
      real_estate: ["Skyline", "Nest", "Homeland", "Vertex", "Griha", "Estates", "Address"],
      coaching: ["Bright", "Aspire", "Genius", "Pathfinder", "Udaan", "Scholar", "Mentor"],
      restaurant: ["Spice", "Zaika", "Saffron", "Tandoor", "Basil", "Swad", "Flavours"],
      boutique: ["Ethereal", "Vastra", "Thread", "Couture", "Rang", "Silk", "Aura"],
      automobile: ["Motors", "Wheels", "Drive", "Auto", "Torque", "Cars", "Ride"]
    };
    NICHE_SUFFIX = {
      salon: ["Salon", "Unisex Salon", "Studio", "Hair & Beauty"],
      clinic: ["Clinic", "Dental Care", "Multi-speciality", "Diagnostics"],
      gym: ["Fitness", "Gym", "Fitness Studio", "CrossFit"],
      real_estate: ["Realty", "Properties", "Homes", "Realtors"],
      coaching: ["Academy", "Classes", "Institute", "Tutorials"],
      restaurant: ["Kitchen", "Restaurant", "Cafe", "Bistro"],
      boutique: ["Boutique", "Design Studio", "Collection", "Emporium"],
      automobile: ["Garage", "Service Centre", "Motors", "Auto Care"]
    };
    NICHES = Object.keys(NICHE_PREFIX);
    SOURCES = [
      "google_maps",
      "website_audit",
      "seo_page",
      "referral",
      "campaign",
      "manual"
    ];
    OWNERS = ["Sumit", "Riya", "Field Agent", "Unassigned"];
    NOTES = [
      "Owner replied on WhatsApp, prefers evening calls.",
      "Asked for pricing PDF; shared over email.",
      "Has an existing agency, open to switching if ROI improves.",
      "Website has no SSL \u2014 strong audit hook.",
      "Requested a demo before committing.",
      "Interested in the voice agent for appointment reminders.",
      "Budget constrained; revisit next quarter.",
      "Runs 3 branches \u2014 multi-location opportunity.",
      "No response on two attempts. Mark for nurture.",
      "Reference from Jiya Makeover (existing customer)."
    ];
    STATUSES = [
      "new",
      "enriched",
      "contacted",
      "qualified",
      "nurturing",
      "converted",
      "disqualified"
    ];
    OUTCOMES = [
      "connected",
      "connected",
      "connected",
      "no_answer",
      "busy",
      "voicemail",
      "failed",
      "scheduled"
    ];
    INTENTS = [
      "interested",
      "callback",
      "not_interested",
      "wrong_number",
      "unknown"
    ];
    TRANSCRIPTS = [
      "AI: Namaste, main LeadsGen AI se bol rahi hoon. Kya aap apne business ke liye naye customers dhoondh rahe hain? / Prospect: Haan, batayiye.",
      "AI: Aapki website par 3 issues mile hain. Kya main free audit report bhejoon? / Prospect: Haan bhej dijiye, WhatsApp par.",
      "Prospect: Abhi busy hoon. / AI: Theek hai, main kal shaam 6 baje call karti hoon.",
      "Prospect: Humein nahi chahiye. / AI: Samajh gayi. Dhanyavaad.",
      "AI: Kya aap appointment reminders automate karna chahenge? / Prospect: Ha, pricing batao.",
      "Wrong number \u2014 recipient is not a business owner."
    ];
  }
});

// node_modules/clsx/dist/clsx.mjs
var init_clsx = __esm({
  "node_modules/clsx/dist/clsx.mjs"() {
  }
});

// src/lib/utils.ts
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
var nfInt, nf1, inr;
var init_utils = __esm({
  "src/lib/utils.ts"() {
    "use strict";
    init_clsx();
    nfInt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
    nf1 = new Intl.NumberFormat("en-IN", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1
    });
    inr = new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0
    });
  }
});

// src/api/client.ts
var client_exports = {};
__export(client_exports, {
  ApiError: () => ApiError,
  api: () => api
});
function freshStore() {
  const leads = buildLeads();
  const calls2 = buildCalls(leads);
  return { leads, calls: calls2, runs: [], automations: defaultAutomations() };
}
function loadStore() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return freshStore();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed.leads) || !Array.isArray(parsed.calls)) return freshStore();
    const base = freshStore();
    return {
      leads: parsed.leads,
      calls: parsed.calls,
      runs: Array.isArray(parsed.runs) ? parsed.runs : [],
      // Automation *definitions* always come from code, but runtime flags persist.
      automations: base.automations.map((a) => {
        const saved = (parsed.automations ?? []).find((x) => x.id === a.id);
        return saved ? { ...a, enabled: saved.enabled, lastRun: saved.lastRun ?? null } : a;
      })
    };
  } catch {
    return freshStore();
  }
}
function persist(store) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
  } catch {
  }
}
function defaultAutomations() {
  return [
    {
      id: "enrich_leads",
      name: "Lead Enrichment",
      summary: "Fill missing email / notes and pull firmographic signals.",
      detail: "Runs each un-enriched lead through the free provider chain (SearXNG \u2192 Google Maps Places \u2192 Mistral) and back-fills email, notes and city/state. Promotes status from `new` to `enriched`.",
      category: "data",
      cron: "Every 30 minutes",
      enabled: true,
      avgDurationMs: 1600,
      destructive: false,
      params: [
        {
          name: "limit",
          label: "Batch size",
          type: "number",
          defaultValue: 50,
          min: 1,
          max: 250,
          help: "Max leads processed in one run."
        },
        {
          name: "provider",
          label: "Provider chain",
          type: "select",
          defaultValue: "auto",
          options: [
            { label: "Auto (free chain)", value: "auto" },
            { label: "Google Maps only", value: "maps" },
            { label: "SearXNG only", value: "searxng" }
          ]
        }
      ],
      lastRun: null
    },
    {
      id: "score_leads",
      name: "Lead Scoring",
      summary: "Recompute 0-100 score and hot / warm / cold band.",
      detail: "Applies the scoring heuristic (status weight + recency decay + source quality + call history) to every lead and re-bands temperature. Hot \u2265 72, Warm \u2265 45, else Cold.",
      category: "data",
      cron: "Hourly",
      enabled: true,
      avgDurationMs: 900,
      destructive: false,
      params: [
        {
          name: "model",
          label: "Scoring model",
          type: "select",
          defaultValue: "heuristic_v2",
          options: [
            { label: "Heuristic v2 (recency aware)", value: "heuristic_v2" },
            { label: "Heuristic v1 (flat)", value: "baseline" }
          ]
        }
      ],
      lastRun: null
    },
    {
      id: "dedupe_leads",
      name: "Duplicate Cleanup",
      summary: "Merge leads that share the same phone number.",
      detail: "Groups leads by normalised phone number and keeps one record per group. This permanently deletes the losing rows \u2014 run a dry run first if you are unsure.",
      category: "hygiene",
      cron: "Daily at 02:00 IST",
      enabled: true,
      avgDurationMs: 1400,
      destructive: true,
      params: [
        {
          name: "strategy",
          label: "Keep which record?",
          type: "select",
          defaultValue: "keep_newest",
          options: [
            { label: "Keep newest", value: "keep_newest" },
            { label: "Keep oldest", value: "keep_oldest" },
            { label: "Keep highest score", value: "keep_best" }
          ]
        },
        {
          name: "dryRun",
          label: "Dry run (report only, no deletes)",
          type: "boolean",
          defaultValue: true
        }
      ],
      lastRun: null
    },
    {
      id: "auto_dial_batch",
      name: "AI Auto-Dial Batch",
      summary: "Place outbound AI voice calls to the next batch of leads.",
      detail: "Picks the highest-scoring leads that have not been contacted recently and places AI voice calls through Vobiz. Writes a call record per attempt and advances the lead to `contacted`.",
      category: "voice",
      cron: "Every 15 minutes (09:00\u201320:00 IST)",
      enabled: true,
      avgDurationMs: 2600,
      destructive: false,
      params: [
        {
          name: "batchSize",
          label: "Calls to place",
          type: "number",
          defaultValue: 25,
          min: 1,
          max: 100
        },
        {
          name: "niche",
          label: "Restrict to niche",
          type: "select",
          defaultValue: "all",
          options: [
            { label: "All niches", value: "all" },
            { label: "Salon", value: "salon" },
            { label: "Clinic", value: "clinic" },
            { label: "Gym", value: "gym" },
            { label: "Real estate", value: "real_estate" },
            { label: "Coaching", value: "coaching" },
            { label: "Restaurant", value: "restaurant" },
            { label: "Boutique", value: "boutique" },
            { label: "Automobile", value: "automobile" }
          ]
        },
        {
          name: "respectDnd",
          label: "Skip DND-flagged numbers",
          type: "boolean",
          defaultValue: true
        }
      ],
      lastRun: null
    },
    {
      id: "retry_no_answer",
      name: "No-Answer Retry",
      summary: "Re-dial leads whose previous calls were not answered.",
      detail: "Finds call records with outcome no_answer / busy / failed and re-queues them, capped by attempt count and a minimum back-off window.",
      category: "voice",
      cron: "Every 3 hours",
      enabled: true,
      avgDurationMs: 1800,
      destructive: false,
      params: [
        { name: "maxAttempts", label: "Attempt ceiling", type: "number", defaultValue: 3, min: 1, max: 6 },
        { name: "backoffHours", label: "Back-off (hours)", type: "number", defaultValue: 6, min: 1, max: 72 }
      ],
      lastRun: null
    },
    {
      id: "followup_sequences",
      name: "Follow-up Sequences",
      summary: "Send WhatsApp / email follow-ups to qualified leads.",
      detail: "Advances every qualified or nurturing lead to the next step of its sequence and stamps `lastContactedAt`. Uses the Hostinger SMTP relay and WAHA for WhatsApp.",
      category: "outreach",
      cron: "Daily at 11:00 IST",
      enabled: true,
      avgDurationMs: 1500,
      destructive: false,
      params: [
        {
          name: "channel",
          label: "Channel",
          type: "select",
          defaultValue: "both",
          options: [
            { label: "WhatsApp + Email", value: "both" },
            { label: "WhatsApp only", value: "whatsapp" },
            { label: "Email only", value: "email" }
          ]
        },
        { name: "limit", label: "Max sends", type: "number", defaultValue: 100, min: 1, max: 500 }
      ],
      lastRun: null
    },
    {
      id: "transcribe_backlog",
      name: "Call Transcription",
      summary: "Transcribe connected calls that are missing a transcript.",
      detail: "Pushes call audio through Groq whisper-large-v3 (with EdgeTTS/Gemini fallback) and stores the transcript plus intent and sentiment classification.",
      category: "voice",
      cron: "Every 20 minutes",
      enabled: true,
      avgDurationMs: 2200,
      destructive: false,
      params: [{ name: "limit", label: "Calls per run", type: "number", defaultValue: 40, min: 1, max: 200 }],
      lastRun: null
    },
    {
      id: "stale_lead_reaper",
      name: "Stale Lead Reaper",
      summary: "Demote or disqualify leads with no activity for N days.",
      detail: "Leads untouched beyond the inactivity threshold are moved to `nurturing`, and beyond twice the threshold to `disqualified`. This is a destructive state change.",
      category: "hygiene",
      cron: "Weekly, Sunday 23:30 IST",
      enabled: false,
      avgDurationMs: 1100,
      destructive: true,
      params: [
        { name: "daysInactive", label: "Inactivity threshold (days)", type: "number", defaultValue: 30, min: 7, max: 180 },
        {
          name: "action",
          label: "Action",
          type: "select",
          defaultValue: "nurture",
          options: [
            { label: "Move to nurturing", value: "nurture" },
            { label: "Disqualify", value: "disqualify" }
          ]
        }
      ],
      lastRun: null
    },
    {
      id: "nightly_digest",
      name: "Nightly Digest Report",
      summary: "Build and email the daily performance digest.",
      detail: "Aggregates lead, call and conversion metrics for the day, renders the digest and emails it to the configured recipients through Hostinger SMTP.",
      category: "reporting",
      cron: "Daily at 21:00 IST",
      enabled: true,
      avgDurationMs: 1e3,
      destructive: false,
      params: [
        {
          name: "recipient",
          label: "Recipient",
          type: "text",
          defaultValue: "admin@leadsgenai.in",
          help: "Comma separated for multiple recipients."
        },
        {
          name: "includeTranscripts",
          label: "Attach call transcripts",
          type: "boolean",
          defaultValue: false
        }
      ],
      lastRun: null
    }
  ];
}
function compare(a, b) {
  if (typeof a === "number" && typeof b === "number") return a - b;
  const sa = String(a ?? "").toLowerCase();
  const sb = String(b ?? "").toLowerCase();
  return sa.localeCompare(sb);
}
function applySort(items, sort, dir = "asc") {
  if (!sort) return items;
  const sorted = [...items].sort((x, y) => compare(x[sort], y[sort]));
  return dir === "desc" ? sorted.reverse() : sorted;
}
function createMockApiClient() {
  let store = loadStore();
  let failureRate = 0;
  const save = () => persist(store);
  async function hop(ms) {
    await sleep(ms);
    if (failureRate > 0 && Math.random() < failureRate) {
      throw new ApiError("Upstream service is temporarily unavailable.", 503);
    }
  }
  const latency = (base) => base * (0.6 + Math.random() * 0.8);
  function findAutomation(id) {
    const found = store.automations.find((a) => a.id === id);
    if (!found) throw new ApiError(`Unknown automation "${id}".`, 404);
    return found;
  }
  function pushRun(run) {
    store.runs = [run, ...store.runs].slice(0, 60);
    const def = store.automations.find((a) => a.id === run.automationId);
    if (def) def.lastRun = run;
    save();
  }
  function runAutomation(def, params, dryRun) {
    const now = (/* @__PURE__ */ new Date()).toISOString();
    switch (def.id) {
      case "enrich_leads": {
        const limit = Number(params.limit ?? 50);
        const targets = store.leads.filter((l) => !l.email || l.status === "new").sort((a, b) => +new Date(b.createdAt) - +new Date(a.createdAt)).slice(0, limit);
        if (dryRun) {
          return { processed: targets.length, message: `${targets.length} leads would be enriched.` };
        }
        targets.forEach((l) => {
          if (!l.email) l.email = `owner.${l.phone.slice(-6)}@${l.niche}mail.in`;
          if (!l.notes) l.notes = "Auto-enriched: firmographics pulled from public sources.";
          if (l.status === "new") l.status = "enriched";
          l.updatedAt = now;
        });
        return { processed: targets.length, message: `Enriched ${targets.length} leads.` };
      }
      case "score_leads": {
        const useV2 = (params.model ?? "heuristic_v2") === "heuristic_v2";
        if (dryRun) return { processed: store.leads.length, message: `${store.leads.length} leads would be re-scored.` };
        store.leads.forEach((l) => {
          const statusWeight = {
            converted: 92,
            qualified: 78,
            nurturing: 60,
            contacted: 58,
            enriched: 48,
            new: 34,
            disqualified: 12
          };
          const sourceWeight = {
            referral: 12,
            website_audit: 8,
            campaign: 5,
            seo_page: 3,
            google_maps: 0,
            manual: -4
          };
          const ageDays = (Date.now() - +new Date(l.createdAt)) / 864e5;
          const recency = useV2 ? Math.max(-14, -Math.round(ageDays / 6)) : 0;
          const base = (statusWeight[l.status] ?? 40) + (sourceWeight[l.source] ?? 0) + recency;
          l.score = Math.max(1, Math.min(99, Math.round(base)));
          l.temperature = l.score >= 72 ? "hot" : l.score >= 45 ? "warm" : "cold";
          l.updatedAt = now;
        });
        return { processed: store.leads.length, message: `Re-scored ${store.leads.length} leads.` };
      }
      case "dedupe_leads": {
        const strategy = String(params.strategy ?? "keep_newest");
        const byPhone = /* @__PURE__ */ new Map();
        store.leads.forEach((l) => {
          const key = l.phone.replace(/\D/g, "").slice(-10);
          const group = byPhone.get(key) ?? [];
          group.push(l);
          byPhone.set(key, group);
        });
        const doomed = [];
        byPhone.forEach((group) => {
          if (group.length < 2) return;
          const sorted = [...group].sort((a, b) => {
            if (strategy === "keep_oldest") return +new Date(a.createdAt) - +new Date(b.createdAt);
            if (strategy === "keep_best") return b.score - a.score;
            return +new Date(b.createdAt) - +new Date(a.createdAt);
          });
          doomed.push(...sorted.slice(1).map((l) => l.id));
        });
        if (dryRun) {
          return { processed: doomed.length, message: `${doomed.length} duplicates would be removed.` };
        }
        store.leads = store.leads.filter((l) => !doomed.includes(l.id));
        return { processed: doomed.length, message: `Removed ${doomed.length} duplicate leads.` };
      }
      case "auto_dial_batch": {
        const size = Number(params.batchSize ?? 25);
        const niche = String(params.niche ?? "all");
        const pool = store.leads.filter(
          (l) => l.status !== "converted" && l.status !== "disqualified" && (niche === "all" || l.niche === niche)
        ).sort((a, b) => b.score - a.score).slice(0, size);
        if (dryRun) return { processed: pool.length, message: `${pool.length} calls would be placed.` };
        const outcomes = ["connected", "connected", "no_answer", "busy", "voicemail", "failed"];
        const intents = ["interested", "callback", "not_interested", "unknown"];
        let callSeq = store.calls.length + 6e4;
        pool.forEach((lead) => {
          const outcome = outcomes[Math.floor(Math.random() * outcomes.length)];
          const connected = outcome === "connected";
          const durationSec = connected ? Math.floor(35 + Math.random() * 480) : Math.floor(Math.random() * 16);
          store.calls.unshift({
            id: `CL-${callSeq++}`,
            leadId: lead.id,
            leadName: lead.name,
            businessName: lead.businessName,
            direction: "outbound",
            outcome,
            intent: connected ? intents[Math.floor(Math.random() * intents.length)] : "unknown",
            sentiment: connected ? ["positive", "neutral", "negative"][Math.floor(Math.random() * 3)] : "neutral",
            durationSec,
            costInr: connected ? Number((durationSec / 60 * 1.9).toFixed(2)) : 0,
            transcript: connected ? "AI: Namaste, main LeadsGen AI se bol rahi hoon. Kya aap apne business ke liye naye customers dhoondh rahe hain?" : "",
            startedAt: now
          });
          if (lead.status === "new" || lead.status === "enriched") lead.status = "contacted";
          lead.lastContactedAt = now;
          lead.updatedAt = now;
        });
        return { processed: pool.length, message: `Placed ${pool.length} AI calls.` };
      }
      case "retry_no_answer": {
        const maxAttempts = Number(params.maxAttempts ?? 3);
        const backoffHours = Number(params.backoffHours ?? 6);
        const cutoff = Date.now() - backoffHours * 36e5;
        const attempts = /* @__PURE__ */ new Map();
        store.calls.forEach((c) => {
          attempts.set(c.leadId, (attempts.get(c.leadId) ?? 0) + 1);
        });
        const targets = store.leads.filter((l) => {
          if (l.status === "converted" || l.status === "disqualified") return false;
          if ((attempts.get(l.id) ?? 0) >= maxAttempts) return false;
          const last = l.lastContactedAt ? +new Date(l.lastContactedAt) : 0;
          return last === 0 || last < cutoff;
        });
        if (dryRun) return { processed: targets.length, message: `${targets.length} retries would be queued.` };
        let seq = store.calls.length + 7e4;
        targets.forEach((lead) => {
          const outcome = Math.random() < 0.62 ? "connected" : "no_answer";
          const connected = outcome === "connected";
          const durationSec = connected ? Math.floor(40 + Math.random() * 400) : 0;
          store.calls.unshift({
            id: `CL-${seq++}`,
            leadId: lead.id,
            leadName: lead.name,
            businessName: lead.businessName,
            direction: "outbound",
            outcome,
            intent: connected ? "callback" : "unknown",
            sentiment: connected ? "positive" : "neutral",
            durationSec,
            costInr: connected ? Number((durationSec / 60 * 1.9).toFixed(2)) : 0,
            transcript: connected ? "AI: Follow-up call connected. Prospect requested a callback window." : "",
            startedAt: now
          });
          lead.lastContactedAt = now;
          lead.updatedAt = now;
        });
        return { processed: targets.length, message: `Queued ${targets.length} retry calls.` };
      }
      case "followup_sequences": {
        const limit = Number(params.limit ?? 100);
        const targets = store.leads.filter((l) => l.status === "qualified" || l.status === "nurturing").slice(0, limit);
        if (dryRun)
          return { processed: targets.length, message: `${targets.length} follow-ups would be sent.` };
        targets.forEach((l) => {
          l.lastContactedAt = now;
          l.notes = l.notes ? `${l.notes} | Follow-up sent ${new Date(now).toLocaleDateString("en-IN")}.` : `Follow-up sent ${new Date(now).toLocaleDateString("en-IN")}.`;
          l.updatedAt = now;
        });
        return { processed: targets.length, message: `Sent ${targets.length} follow-ups.` };
      }
      case "transcribe_backlog": {
        const limit = Number(params.limit ?? 40);
        const targets = store.calls.filter((c) => c.outcome === "connected" && !c.transcript).slice(0, limit);
        if (dryRun)
          return { processed: targets.length, message: `${targets.length} calls would be transcribed.` };
        targets.forEach((c) => {
          c.transcript = "AI: Namaste, main LeadsGen AI se bol rahi hoon. / Prospect: Haan, batayiye aapki service kya hai?";
          if (c.intent === "unknown") c.intent = Math.random() < 0.5 ? "interested" : "callback";
          c.sentiment = c.intent === "interested" ? "positive" : "neutral";
        });
        return { processed: targets.length, message: `Transcribed ${targets.length} calls.` };
      }
      case "stale_lead_reaper": {
        const days = Number(params.daysInactive ?? 30);
        const action = String(params.action ?? "nurture");
        const threshold = Date.now() - days * 864e5;
        const hard = Date.now() - days * 2 * 864e5;
        const targets = store.leads.filter((l) => {
          if (l.status === "converted") return false;
          const ref = l.lastContactedAt ? +new Date(l.lastContactedAt) : +new Date(l.createdAt);
          return ref < threshold;
        });
        if (dryRun) return { processed: targets.length, message: `${targets.length} leads would be demoted.` };
        targets.forEach((l) => {
          const ref = l.lastContactedAt ? +new Date(l.lastContactedAt) : +new Date(l.createdAt);
          l.status = action === "disqualify" && ref < hard ? "disqualified" : "nurturing";
          l.temperature = "cold";
          l.updatedAt = now;
        });
        return { processed: targets.length, message: `Demoted ${targets.length} stale leads.` };
      }
      case "nightly_digest": {
        const connected = store.calls.filter((c) => c.outcome === "connected").length;
        const converted = store.leads.filter((l) => l.status === "converted").length;
        const recipient = String(params.recipient ?? "admin@leadsgenai.in");
        return {
          processed: 1,
          message: `Digest built (${connected} connected calls, ${converted} conversions) \u2192 ${recipient}.`
        };
      }
      default:
        throw new ApiError(`No handler wired for automation "${def.id}".`, 501);
    }
  }
  return {
    auth: {
      async login({ email, password }) {
        await hop(latency(550));
        const entry = DEMO_USERS[email.trim().toLowerCase()];
        if (!entry || entry.password !== password) {
          throw new ApiError("Invalid email or password.", 401);
        }
        const issuedAt = /* @__PURE__ */ new Date();
        const expiresAt = new Date(issuedAt.getTime() + 8 * 36e5);
        return {
          token: `sess_${entry.user.id}_${Math.random().toString(36).slice(2)}_${issuedAt.getTime()}`,
          user: entry.user,
          issuedAt: issuedAt.toISOString(),
          expiresAt: expiresAt.toISOString()
        };
      },
      async logout() {
        await hop(latency(180));
      },
      async me(token) {
        await hop(latency(160));
        const parts = token.split("_");
        if (parts[0] !== "sess" || !parts[1]) throw new ApiError("Session expired.", 401);
        const entry = Object.values(DEMO_USERS).find((u) => u.user.id === parts[1]);
        if (!entry) throw new ApiError("Session expired.", 401);
        return entry.user;
      }
    },
    leads: {
      async list(q) {
        await hop(latency(420));
        const needle = (q.q ?? "").trim();
        let rows = store.leads;
        if (needle) {
          rows = rows.filter(
            (l) => [l.name, l.businessName, l.phone, l.email, l.city, l.owner, l.id, l.niche, l.status].join(" ").toLowerCase().includes(needle.toLowerCase())
          );
        }
        if (q.status) rows = rows.filter((l) => l.status === q.status);
        if (q.niche) rows = rows.filter((l) => l.niche === q.niche);
        if (q.temperature) rows = rows.filter((l) => l.temperature === q.temperature);
        if (q.source) rows = rows.filter((l) => l.source === q.source);
        if (q.owner) rows = rows.filter((l) => l.owner === q.owner);
        rows = applySort(rows, q.sort, q.dir);
        const pageSize = q.pageSize ?? 10;
        const page = q.page ?? 1;
        const start = (page - 1) * pageSize;
        return { items: rows.slice(start, start + pageSize), total: rows.length, page, pageSize };
      },
      async get(id) {
        await hop(latency(220));
        const found = store.leads.find((l) => l.id === id);
        if (!found) throw new ApiError("Lead not found.", 404);
        return found;
      },
      async create(input) {
        await hop(latency(520));
        const dupe = store.leads.find(
          (l) => l.phone.replace(/\D/g, "").slice(-10) === input.phone.replace(/\D/g, "").slice(-10)
        );
        if (dupe) throw new ApiError(`A lead with this phone already exists (${dupe.id}).`, 409);
        const now = (/* @__PURE__ */ new Date()).toISOString();
        const lead = {
          ...input,
          id: `LD-${1e3 + store.leads.length + Math.floor(Math.random() * 90)}`,
          createdAt: now,
          updatedAt: now
        };
        store.leads = [lead, ...store.leads];
        save();
        return lead;
      },
      async update(id, input) {
        await hop(latency(480));
        const idx = store.leads.findIndex((l) => l.id === id);
        if (idx === -1) throw new ApiError("Lead not found.", 404);
        const next = { ...store.leads[idx], ...input, id, updatedAt: (/* @__PURE__ */ new Date()).toISOString() };
        store.leads[idx] = next;
        save();
        return next;
      },
      async remove(id) {
        await hop(latency(420));
        const before2 = store.leads.length;
        store.leads = store.leads.filter((l) => l.id !== id);
        if (store.leads.length === before2) throw new ApiError("Lead not found.", 404);
        save();
      },
      async removeMany(ids) {
        await hop(latency(700));
        const set = new Set(ids);
        const before2 = store.leads.length;
        store.leads = store.leads.filter((l) => !set.has(l.id));
        save();
        return before2 - store.leads.length;
      },
      async exportAll(q) {
        await hop(latency(300));
        const needle = (q.q ?? "").trim().toLowerCase();
        return store.leads.filter((l) => {
          if (needle && ![l.name, l.businessName, l.phone, l.email, l.city].join(" ").toLowerCase().includes(needle))
            return false;
          if (q.status && l.status !== q.status) return false;
          if (q.niche && l.niche !== q.niche) return false;
          if (q.temperature && l.temperature !== q.temperature) return false;
          return true;
        });
      }
    },
    calls: {
      async list(q) {
        await hop(latency(420));
        const needle = (q.q ?? "").trim().toLowerCase();
        let rows = store.calls;
        if (needle) {
          rows = rows.filter(
            (c) => [c.id, c.leadName, c.businessName, c.leadId, c.outcome, c.intent, c.transcript].join(" ").toLowerCase().includes(needle)
          );
        }
        if (q.outcome) rows = rows.filter((c) => c.outcome === q.outcome);
        if (q.intent) rows = rows.filter((c) => c.intent === q.intent);
        if (q.sentiment) rows = rows.filter((c) => c.sentiment === q.sentiment);
        if (q.direction) rows = rows.filter((c) => c.direction === q.direction);
        rows = applySort(
          rows,
          q.sort,
          q.dir
        );
        const pageSize = q.pageSize ?? 10;
        const page = q.page ?? 1;
        const start = (page - 1) * pageSize;
        return { items: rows.slice(start, start + pageSize), total: rows.length, page, pageSize };
      }
    },
    metrics: {
      async overview(rangeDays) {
        await hop(latency(600));
        const since = Date.now() - rangeDays * 864e5;
        const recentLeads = store.leads.filter((l) => +new Date(l.createdAt) >= since);
        const recentCalls = store.calls.filter((c) => +new Date(c.startedAt) >= since);
        const connected = recentCalls.filter((c) => c.outcome === "connected" || c.outcome === "scheduled");
        const converted = store.leads.filter((l) => l.status === "converted");
        const minutesUsed = Math.round(
          recentCalls.reduce((sum, c) => sum + c.durationSec, 0) / 60
        );
        const contactRate = recentCalls.length ? connected.length / recentCalls.length * 100 : 0;
        const conversionRate = store.leads.length ? converted.length / store.leads.length * 100 : 0;
        const avgCallSeconds = connected.length ? connected.reduce((s, c) => s + c.durationSec, 0) / connected.length : 0;
        const dayLabels = [];
        for (let i = rangeDays - 1; i >= 0; i--) {
          const d = /* @__PURE__ */ new Date();
          d.setDate(d.getDate() - i);
          dayLabels.push(d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" }));
        }
        const leadsByDay = dayLabels.map((label) => ({
          label,
          value: recentLeads.filter(
            (l) => new Date(l.createdAt).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }) === label
          ).length
        }));
        const callsByDay = dayLabels.map((label) => ({
          label,
          value: recentCalls.filter(
            (c) => new Date(c.startedAt).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }) === label
          ).length
        }));
        const slice = (items, key) => {
          const counts = /* @__PURE__ */ new Map();
          items.forEach((it) => {
            const k = String(it[key]);
            counts.set(k, (counts.get(k) ?? 0) + 1);
          });
          return [...counts.entries()].map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value);
        };
        const niches = [
          "salon",
          "clinic",
          "gym",
          "real_estate",
          "coaching",
          "restaurant",
          "boutique",
          "automobile"
        ];
        return {
          totals: {
            leads: store.leads.length,
            calls: recentCalls.length,
            converted: converted.length,
            contactRate,
            conversionRate,
            avgCallSeconds,
            minutesUsed,
            minutesIncluded: 500
          },
          deltas: {
            leads: 12.4,
            calls: 8.1,
            converted: 21.7,
            contactRate: 3.2,
            conversionRate: 1.9,
            avgCallSeconds: -4.6
          },
          leadsByDay,
          callsByDay,
          leadsByStatus: slice(store.leads, "status"),
          leadsByNiche: niches.map((n) => ({ name: n, value: store.leads.filter((l) => l.niche === n).length })).sort((a, b) => b.value - a.value),
          outcomeSplit: slice(recentCalls, "outcome"),
          topCities: slice(store.leads, "city").slice(0, 6),
          funnel: [
            { stage: "Captured", count: store.leads.length },
            { stage: "Enriched", count: store.leads.filter((l) => l.status !== "new").length },
            { stage: "Contacted", count: store.leads.filter((l) => l.lastContactedAt).length },
            {
              stage: "Qualified",
              count: store.leads.filter((l) => l.status === "qualified" || l.status === "converted").length
            },
            { stage: "Converted", count: converted.length }
          ],
          generatedAt: (/* @__PURE__ */ new Date()).toISOString()
        };
      }
    },
    automations: {
      async list() {
        await hop(latency(320));
        return store.automations.map((a) => ({ ...a }));
      },
      async setEnabled(id, enabled) {
        await hop(latency(260));
        const def = findAutomation(id);
        def.enabled = enabled;
        save();
        return { ...def };
      },
      async trigger(id, params, opts) {
        const def = findAutomation(id);
        const startedAt = (/* @__PURE__ */ new Date()).toISOString();
        const runId = `RUN-${Date.now().toString(36).toUpperCase()}`;
        const dryRun = Boolean(opts?.dryRun ?? params.dryRun);
        const run = {
          id: runId,
          automationId: def.id,
          automationName: def.name,
          status: "running",
          triggeredBy: "manual",
          startedAt,
          finishedAt: null,
          recordsProcessed: 0,
          message: dryRun ? "Dry run in progress\u2026" : "Running\u2026"
        };
        pushRun(run);
        const duration = def.avgDurationMs * (0.7 + Math.random() * 0.7);
        await sleep(duration);
        if (failureRate > 0 && Math.random() < failureRate) {
          const failed = {
            ...run,
            status: "failed",
            finishedAt: (/* @__PURE__ */ new Date()).toISOString(),
            message: "Run failed.",
            error: "Upstream provider returned 503 after 3 retries."
          };
          pushRun(failed);
          throw new ApiError("Automation run failed: upstream provider returned 503.", 502);
        }
        const { processed, message } = runAutomation(def, params, dryRun);
        const finished = {
          ...run,
          status: "success",
          finishedAt: (/* @__PURE__ */ new Date()).toISOString(),
          recordsProcessed: processed,
          message: dryRun ? `Dry run \u2014 ${message}` : message
        };
        pushRun(finished);
        return finished;
      },
      async runs(limit = 30) {
        await hop(latency(200));
        return store.runs.slice(0, limit);
      }
    },
    setFailureRate(rate) {
      failureRate = Math.max(0, Math.min(1, rate));
    },
    getFailureRate() {
      return failureRate;
    },
    async resetData() {
      await hop(latency(400));
      store = freshStore();
      save();
    }
  };
}
var ApiError, STORE_KEY, DEMO_USERS, api;
var init_client = __esm({
  "src/api/client.ts"() {
    "use strict";
    init_seed();
    init_utils();
    ApiError = class extends Error {
      status;
      constructor(message, status = 500) {
        super(message);
        this.name = "ApiError";
        this.status = status;
      }
    };
    STORE_KEY = "lg_admin_store_v1";
    DEMO_USERS = {
      "admin@example.com": {
        password: "admin123",
        user: {
          id: "USR-1",
          name: "Sumit Revolt",
          email: "admin@example.com",
          role: "owner",
          initials: "SR"
        }
      },
      "ops@example.com": {
        password: "ops123",
        user: {
          id: "USR-2",
          name: "Riya Nair",
          email: "ops@example.com",
          role: "operator",
          initials: "RN"
        }
      }
    };
    api = createMockApiClient();
  }
});

// _smoke/api-check.ts
var mem = /* @__PURE__ */ new Map();
globalThis.localStorage = {
  getItem: (k) => mem.get(k) ?? null,
  setItem: (k, v) => {
    mem.set(k, v);
  },
  removeItem: (k) => {
    mem.delete(k);
  }
};
var { api: api2, ApiError: ApiError2 } = await Promise.resolve().then(() => (init_client(), client_exports));
api2.setFailureRate(0);
var results = [];
var ok = (m2) => results.push("PASS  " + m2);
var bad = (m2) => results.push("FAIL  " + m2);
try {
  await api2.auth.login({ email: "admin@example.com", password: "wrong" });
  bad("bad password rejected");
} catch (e) {
  e instanceof ApiError2 && e.status === 401 ? ok("bad password -> 401") : bad("bad password error type");
}
var session = await api2.auth.login({ email: "admin@example.com", password: "admin123" });
ok("login ok (" + session.user.role + ")");
var me = await api2.auth.me(session.token);
me.id === "USR-1" ? ok("me() resolves user") : bad("me() mismatch");
try {
  await api2.auth.me("garbage");
  bad("invalid token rejected");
} catch (e) {
  e instanceof ApiError2 && e.status === 401 ? ok("invalid token -> 401") : bad("invalid token error");
}
var p1 = await api2.leads.list({ page: 1, pageSize: 10, sort: "score", dir: "desc" });
p1.total > 200 && p1.items.length === 10 ? ok("list page1 (total " + p1.total + ")") : bad("list page1");
var descending = p1.items.every((l, i) => i === 0 || p1.items[i - 1].score >= l.score);
descending ? ok("sort score desc correct") : bad("sort score desc broken");
var searched = await api2.leads.list({ q: p1.items[0].phone, pageSize: 5 });
searched.total === 1 ? ok("global search by phone") : bad("search by phone -> " + searched.total);
var filtered = await api2.leads.list({ status: "converted", pageSize: 5 });
filtered.items.every((l) => l.status === "converted") ? ok("status filter (" + filtered.total + ")") : bad("status filter");
var before = (await api2.leads.list({ pageSize: 1 })).total;
var created = await api2.leads.create({
  name: "Test Contact",
  businessName: "QA Studio",
  phone: "9000000001",
  email: "qa@test.in",
  city: "Pune",
  state: "Maharashtra",
  niche: "salon",
  source: "manual",
  status: "new",
  temperature: "cold",
  score: 30,
  owner: "Unassigned",
  notes: "",
  lastContactedAt: null
});
ok("create lead " + created.id);
try {
  await api2.leads.create({ ...created, phone: "9000000001" });
  bad("duplicate phone rejected");
} catch (e) {
  e instanceof ApiError2 && e.status === 409 ? ok("duplicate phone -> 409") : bad("duplicate phone error");
}
var updated = await api2.leads.update(created.id, { ...created, status: "qualified", score: 80 });
updated.status === "qualified" && updated.temperature === "hot" ? ok("update lead + derived temperature") : bad("update lead");
await api2.leads.remove(created.id);
var after = (await api2.leads.list({ pageSize: 1 })).total;
after === before ? ok("delete lead restores count") : bad("delete lead (" + before + " -> " + after + ")");
var m = await api2.metrics.overview(30);
var sane = m.totals.leads > 0 && m.leadsByDay.length === 30 && m.funnel.length === 5 && m.totals.contactRate >= 0 && m.totals.contactRate <= 100 && Number.isFinite(m.totals.avgCallSeconds);
sane ? ok(
  "metrics sane (" + m.totals.leads + " leads, " + m.totals.minutesUsed + " min, contact " + m.totals.contactRate.toFixed(1) + "%)"
) : bad("metrics shape");
var defs = await api2.automations.list();
defs.length === 9 ? ok(defs.length + " automations registered") : bad("automation count " + defs.length);
for (const def of defs) {
  const params = {};
  def.params.forEach((p) => {
    params[p.name] = p.defaultValue;
  });
  try {
    const run = await api2.automations.trigger(def.id, params, { dryRun: def.destructive });
    run.status === "success" && typeof run.message === "string" ? ok(def.id + ": " + run.recordsProcessed + " rec \u2014 " + run.message) : bad(def.id + ": unexpected status " + run.status);
  } catch (e) {
    bad(def.id + ": " + (e instanceof Error ? e.message : "threw"));
  }
}
var preDedupe = (await api2.leads.list({ pageSize: 1 })).total;
var dedupe = await api2.automations.trigger("dedupe_leads", {
  strategy: "keep_newest",
  dryRun: false
});
var postDedupe = (await api2.leads.list({ pageSize: 1 })).total;
dedupe.recordsProcessed > 0 && preDedupe - postDedupe === dedupe.recordsProcessed ? ok("dedupe removed " + dedupe.recordsProcessed + " (" + preDedupe + " -> " + postDedupe + ")") : bad(
  "dedupe mismatch (" + preDedupe + " -> " + postDedupe + ", reported " + dedupe.recordsProcessed + ")"
);
var runs = await api2.automations.runs(30);
runs.length >= 10 ? ok("run history (" + runs.length + " entries)") : bad("run history " + runs.length);
api2.setFailureRate(1);
try {
  await api2.leads.list({ pageSize: 5 });
  bad("failure injection active");
} catch (e) {
  e instanceof ApiError2 && e.status === 503 ? ok("failure injection -> 503") : bad("failure injection error");
}
api2.setFailureRate(0);
await api2.resetData();
var fresh = await api2.leads.list({ pageSize: 1 });
fresh.total === 255 ? ok("resetData restores seed (" + fresh.total + ")") : bad("resetData -> " + fresh.total);
var calls = await api2.calls.list({ page: 1, pageSize: 10, sort: "durationSec", dir: "desc" });
calls.items.every((c, i) => i === 0 || calls.items[i - 1].durationSec >= c.durationSec) ? ok("calls sort desc (" + calls.total + " total)") : bad("calls sort");
var noAnswer = await api2.calls.list({ outcome: "no_answer", pageSize: 5 });
noAnswer.items.every((c) => c.outcome === "no_answer") ? ok("outcome filter (" + noAnswer.total + ")") : bad("outcome filter");
console.log(results.join("\n"));
console.log(
  "\n" + (results.some((r) => r.startsWith("FAIL")) ? "RESULT: FAILURES PRESENT" : "RESULT: ALL PASS")
);
