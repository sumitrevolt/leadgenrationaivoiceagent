"use strict";

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
var rand = mulberry32(20260831);
var pick = (arr) => arr[Math.floor(rand() * arr.length)];
var int = (min, max) => Math.floor(rand() * (max - min + 1)) + min;
var chance = (p) => rand() < p;
var FIRST = [
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
var LAST = [
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
var CITIES = [
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
var NICHE_PREFIX = {
  salon: ["Glow", "Luxe", "Mirror", "Blush", "Radiant", "Styles", "Crown"],
  clinic: ["Care", "Health", "Arogya", "Vital", "Smile", "Prime", "Sanjeevani"],
  gym: ["Iron", "Pulse", "Titan", "Core", "Beast", "Apex", "Sweat"],
  real_estate: ["Skyline", "Nest", "Homeland", "Vertex", "Griha", "Estates", "Address"],
  coaching: ["Bright", "Aspire", "Genius", "Pathfinder", "Udaan", "Scholar", "Mentor"],
  restaurant: ["Spice", "Zaika", "Saffron", "Tandoor", "Basil", "Swad", "Flavours"],
  boutique: ["Ethereal", "Vastra", "Thread", "Couture", "Rang", "Silk", "Aura"],
  automobile: ["Motors", "Wheels", "Drive", "Auto", "Torque", "Cars", "Ride"]
};
var NICHE_SUFFIX = {
  salon: ["Salon", "Unisex Salon", "Studio", "Hair & Beauty"],
  clinic: ["Clinic", "Dental Care", "Multi-speciality", "Diagnostics"],
  gym: ["Fitness", "Gym", "Fitness Studio", "CrossFit"],
  real_estate: ["Realty", "Properties", "Homes", "Realtors"],
  coaching: ["Academy", "Classes", "Institute", "Tutorials"],
  restaurant: ["Kitchen", "Restaurant", "Cafe", "Bistro"],
  boutique: ["Boutique", "Design Studio", "Collection", "Emporium"],
  automobile: ["Garage", "Service Centre", "Motors", "Auto Care"]
};
var NICHES = Object.keys(NICHE_PREFIX);
var SOURCES = [
  "google_maps",
  "website_audit",
  "seo_page",
  "referral",
  "campaign",
  "manual"
];
var OWNERS = ["Sumit", "Riya", "Field Agent", "Unassigned"];
var NOTES = [
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
var STATUSES = [
  "new",
  "enriched",
  "contacted",
  "qualified",
  "nurturing",
  "converted",
  "disqualified"
];
var OUTCOMES = [
  "connected",
  "connected",
  "connected",
  "no_answer",
  "busy",
  "voicemail",
  "failed",
  "scheduled"
];
var INTENTS = [
  "interested",
  "callback",
  "not_interested",
  "wrong_number",
  "unknown"
];
var TRANSCRIPTS = [
  "AI: Namaste, main LeadsGen AI se bol rahi hoon. Kya aap apne business ke liye naye customers dhoondh rahe hain? / Prospect: Haan, batayiye.",
  "AI: Aapki website par 3 issues mile hain. Kya main free audit report bhejoon? / Prospect: Haan bhej dijiye, WhatsApp par.",
  "Prospect: Abhi busy hoon. / AI: Theek hai, main kal shaam 6 baje call karti hoon.",
  "Prospect: Humein nahi chahiye. / AI: Samajh gayi. Dhanyavaad.",
  "AI: Kya aap appointment reminders automate karna chahenge? / Prospect: Ha, pricing batao.",
  "Wrong number \u2014 recipient is not a business owner."
];
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
  const leads2 = Array.from({ length: count }, (_, i) => makeLead(i));
  const dupes = Math.round(count * 0.03);
  for (let i = 0; i < dupes; i++) {
    const src = leads2[int(0, leads2.length - 1)];
    leads2.push({
      ...src,
      id: `LD-${9e3 + i}`,
      createdAt: isoDaysAgo(int(0, 89)),
      updatedAt: isoDaysAgo(int(0, 20))
    });
  }
  return leads2;
}
function sentimentFor(intent) {
  if (intent === "interested") return chance(0.85) ? "positive" : "neutral";
  if (intent === "callback") return chance(0.55) ? "positive" : "neutral";
  if (intent === "not_interested") return chance(0.7) ? "negative" : "neutral";
  if (intent === "wrong_number") return "neutral";
  return chance(0.5) ? "neutral" : "positive";
}
function buildCalls(leads2, count = 600) {
  const calls2 = [];
  for (let i = 0; i < count; i++) {
    const lead = pick(leads2);
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

// _smoke/seed-check.ts
var leads = buildLeads();
var calls = buildCalls(leads);
var bad = (l) => !l.id || !l.name || !l.phone || !l.city || !Number.isFinite(l.score) || l.score < 0 || l.score > 100 || Number.isNaN(+new Date(l.createdAt));
var badCall = (c) => !c.id || !c.leadId || !Number.isFinite(c.durationSec) || Number.isNaN(+new Date(c.startedAt));
var statuses = {};
leads.forEach((l) => statuses[l.status] = (statuses[l.status] ?? 0) + 1);
var outcomes = {};
calls.forEach((c) => outcomes[c.outcome] = (outcomes[c.outcome] ?? 0) + 1);
console.log(JSON.stringify({
  leads: leads.length,
  calls: calls.length,
  invalidLeads: leads.filter(bad).length,
  invalidCalls: calls.filter(badCall).length,
  uniqueIds: new Set(leads.map((l) => l.id)).size,
  uniquePhones: new Set(leads.map((l) => l.phone)).size,
  statuses,
  outcomes,
  sampleLead: leads[0],
  callsSorted: calls.every((c, i) => i === 0 || +new Date(calls[i - 1].startedAt) >= +new Date(c.startedAt)),
  totalMinutes: Math.round(calls.reduce((s, c) => s + c.durationSec, 0) / 60)
}, null, 2));
