import type {
  CallIntent,
  CallOutcome,
  CallRecord,
  CallSentiment,
  Lead,
  LeadSource,
  LeadStatus,
  LeadTemperature,
  Niche,
} from '@/types';

/* Deterministic PRNG so the demo dataset is stable across reloads. */
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return function rand() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rand = mulberry32(20260831);

const pick = <T,>(arr: readonly T[]): T => arr[Math.floor(rand() * arr.length)];
const int = (min: number, max: number) => Math.floor(rand() * (max - min + 1)) + min;
const chance = (p: number) => rand() < p;

const FIRST = [
  'Aarav', 'Vivaan', 'Aditya', 'Vihaan', 'Arjun', 'Sai', 'Reyansh', 'Ayaan', 'Krishna', 'Ishaan',
  'Ananya', 'Diya', 'Isha', 'Kavya', 'Meera', 'Sara', 'Pooja', 'Neha', 'Riya', 'Anika',
  'Rohan', 'Karan', 'Nikhil', 'Siddharth', 'Manish', 'Deepak', 'Priya', 'Sneha', 'Tanvi', 'Nisha',
] as const;

const LAST = [
  'Sharma', 'Verma', 'Gupta', 'Mehta', 'Patel', 'Reddy', 'Nair', 'Iyer', 'Joshi', 'Kulkarni',
  'Singh', 'Yadav', 'Mishra', 'Chawla', 'Bhatia', 'Sethi', 'Rane', 'Desai', 'Kaur', 'Malhotra',
] as const;

const CITIES = [
  { city: 'Mumbai', state: 'Maharashtra' },
  { city: 'Pune', state: 'Maharashtra' },
  { city: 'Bengaluru', state: 'Karnataka' },
  { city: 'Delhi', state: 'Delhi' },
  { city: 'Hyderabad', state: 'Telangana' },
  { city: 'Chennai', state: 'Tamil Nadu' },
  { city: 'Ahmedabad', state: 'Gujarat' },
  { city: 'Jaipur', state: 'Rajasthan' },
  { city: 'Kolkata', state: 'West Bengal' },
  { city: 'Lucknow', state: 'Uttar Pradesh' },
  { city: 'Indore', state: 'Madhya Pradesh' },
  { city: 'Surat', state: 'Gujarat' },
] as const;

const NICHE_PREFIX: Record<Niche, string[]> = {
  salon: ['Glow', 'Luxe', 'Mirror', 'Blush', 'Radiant', 'Styles', 'Crown'],
  clinic: ['Care', 'Health', 'Arogya', 'Vital', 'Smile', 'Prime', 'Sanjeevani'],
  gym: ['Iron', 'Pulse', 'Titan', 'Core', 'Beast', 'Apex', 'Sweat'],
  real_estate: ['Skyline', 'Nest', 'Homeland', 'Vertex', 'Griha', 'Estates', 'Address'],
  coaching: ['Bright', 'Aspire', 'Genius', 'Pathfinder', 'Udaan', 'Scholar', 'Mentor'],
  restaurant: ['Spice', 'Zaika', 'Saffron', 'Tandoor', 'Basil', 'Swad', 'Flavours'],
  boutique: ['Ethereal', 'Vastra', 'Thread', 'Couture', 'Rang', 'Silk', 'Aura'],
  automobile: ['Motors', 'Wheels', 'Drive', 'Auto', 'Torque', 'Cars', 'Ride'],
};

const NICHE_SUFFIX: Record<Niche, string[]> = {
  salon: ['Salon', 'Unisex Salon', 'Studio', 'Hair & Beauty'],
  clinic: ['Clinic', 'Dental Care', 'Multi-speciality', 'Diagnostics'],
  gym: ['Fitness', 'Gym', 'Fitness Studio', 'CrossFit'],
  real_estate: ['Realty', 'Properties', 'Homes', 'Realtors'],
  coaching: ['Academy', 'Classes', 'Institute', 'Tutorials'],
  restaurant: ['Kitchen', 'Restaurant', 'Cafe', 'Bistro'],
  boutique: ['Boutique', 'Design Studio', 'Collection', 'Emporium'],
  automobile: ['Garage', 'Service Centre', 'Motors', 'Auto Care'],
};

const NICHES = Object.keys(NICHE_PREFIX) as Niche[];
const SOURCES: LeadSource[] = [
  'google_maps',
  'website_audit',
  'seo_page',
  'referral',
  'campaign',
  'manual',
];
const OWNERS = ['Sumit', 'Riya', 'Field Agent', 'Unassigned'] as const;

const NOTES = [
  'Owner replied on WhatsApp, prefers evening calls.',
  'Asked for pricing PDF; shared over email.',
  'Has an existing agency, open to switching if ROI improves.',
  'Website has no SSL — strong audit hook.',
  'Requested a demo before committing.',
  'Interested in the voice agent for appointment reminders.',
  'Budget constrained; revisit next quarter.',
  'Runs 3 branches — multi-location opportunity.',
  'No response on two attempts. Mark for nurture.',
  'Reference from Jiya Makeover (existing customer).',
] as const;

const STATUSES: LeadStatus[] = [
  'new',
  'enriched',
  'contacted',
  'qualified',
  'nurturing',
  'converted',
  'disqualified',
];

const OUTCOMES: CallOutcome[] = [
  'connected',
  'connected',
  'connected',
  'no_answer',
  'busy',
  'voicemail',
  'failed',
  'scheduled',
];

const INTENTS: CallIntent[] = [
  'interested',
  'callback',
  'not_interested',
  'wrong_number',
  'unknown',
];

const TRANSCRIPTS = [
  'AI: Namaste, main LeadsGen AI se bol rahi hoon. Kya aap apne business ke liye naye customers dhoondh rahe hain? / Prospect: Haan, batayiye.',
  'AI: Aapki website par 3 issues mile hain. Kya main free audit report bhejoon? / Prospect: Haan bhej dijiye, WhatsApp par.',
  'Prospect: Abhi busy hoon. / AI: Theek hai, main kal shaam 6 baje call karti hoon.',
  'Prospect: Humein nahi chahiye. / AI: Samajh gayi. Dhanyavaad.',
  'AI: Kya aap appointment reminders automate karna chahenge? / Prospect: Ha, pricing batao.',
  'Wrong number — recipient is not a business owner.',
] as const;

function isoDaysAgo(days: number, hourJitter = true) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  if (hourJitter) {
    d.setHours(int(9, 20), int(0, 59), int(0, 59), 0);
  }
  return d.toISOString();
}

function makeLead(i: number): Lead {
  const niche = pick(NICHES);
  const loc = pick(CITIES);
  const first = pick(FIRST);
  const last = pick(LAST);
  const businessName = `${pick(NICHE_PREFIX[niche])} ${pick(NICHE_SUFFIX[niche])}`;
  const status = pick(STATUSES);
  const createdDaysAgo = int(0, 89);

  const statusScore: Record<LeadStatus, number> = {
    new: int(20, 45),
    enriched: int(35, 60),
    contacted: int(45, 72),
    qualified: int(70, 88),
    nurturing: int(50, 70),
    converted: int(85, 99),
    disqualified: int(5, 25),
  };
  const score = statusScore[status];
  const temperature: LeadTemperature = score >= 72 ? 'hot' : score >= 45 ? 'warm' : 'cold';
  const contacted = status === 'new' || status === 'enriched' ? null : isoDaysAgo(int(0, 20));
  const slug = businessName.toLowerCase().replace(/[^a-z0-9]+/g, '');

  return {
    id: `LD-${String(1000 + i)}`,
    name: `${first} ${last}`,
    businessName,
    phone: `9${int(100000000, 999999999)}`,
    email: `${first.toLowerCase()}.${last.toLowerCase()}@${slug.slice(0, 12)}.in`,
    city: loc.city,
    state: loc.state,
    niche,
    source: pick(SOURCES),
    status,
    temperature,
    score,
    owner: pick(OWNERS),
    notes: chance(0.65) ? pick(NOTES) : '',
    lastContactedAt: contacted,
    createdAt: isoDaysAgo(createdDaysAgo),
    updatedAt: isoDaysAgo(Math.max(0, createdDaysAgo - int(0, 5))),
  };
}

export function buildLeads(count = 248): Lead[] {
  const leads = Array.from({ length: count }, (_, i) => makeLead(i));

  // Seed a handful of realistic duplicates (~3%) so Duplicate Cleanup has real work.
  const dupes = Math.round(count * 0.03);
  for (let i = 0; i < dupes; i++) {
    const src = leads[int(0, leads.length - 1)];
    leads.push({
      ...src,
      id: `LD-${9000 + i}`,
      createdAt: isoDaysAgo(int(0, 89)),
      updatedAt: isoDaysAgo(int(0, 20)),
    });
  }

  return leads;
}

function sentimentFor(intent: CallIntent): CallSentiment {
  if (intent === 'interested') return chance(0.85) ? 'positive' : 'neutral';
  if (intent === 'callback') return chance(0.55) ? 'positive' : 'neutral';
  if (intent === 'not_interested') return chance(0.7) ? 'negative' : 'neutral';
  if (intent === 'wrong_number') return 'neutral';
  return chance(0.5) ? 'neutral' : 'positive';
}

export function buildCalls(leads: Lead[], count = 600): CallRecord[] {
  const calls: CallRecord[] = [];
  for (let i = 0; i < count; i++) {
    const lead = pick(leads);
    const outcome = pick(OUTCOMES);
    const connected = outcome === 'connected' || outcome === 'scheduled';
    // Talk time is deliberately realistic (15-140s) so the 500-minute plan
    // allowance stays meaningful on a 30-day window.
    const durationSec = connected ? int(15, 140) : int(0, 18);
    const intent: CallIntent = connected
      ? pick(INTENTS)
      : outcome === 'failed'
        ? 'unknown'
        : 'unknown';
    const startedAt = isoDaysAgo(int(0, 29));

    calls.push({
      id: `CL-${String(50000 + i)}`,
      leadId: lead.id,
      leadName: lead.name,
      businessName: lead.businessName,
      direction: chance(0.82) ? 'outbound' : 'inbound',
      outcome,
      intent,
      sentiment: sentimentFor(intent),
      durationSec,
      costInr: connected ? Number(((durationSec / 60) * 1.9).toFixed(2)) : 0,
      transcript: connected ? pick(TRANSCRIPTS) : '',
      startedAt,
    });
  }
  return calls.sort((a, b) => +new Date(b.startedAt) - +new Date(a.startedAt));
}
