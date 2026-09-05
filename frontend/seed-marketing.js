/* ============================================================
   ARCHIFY — Marketing Product Launch Dashboard
   Lifecycle management, social credentials, launch analytics.
   ============================================================ */

const SEED_MARKETING_ACCOUNTS = [
  { key: 'facebook-ads', name: 'Facebook Ads', icon: 'facebook', color: '#1877F2', status: 'connected', handle: 'archify.marketing', scopes: ['ads_read', 'ads_management', 'pages_show_list'], lastSync: '2026-09-05T04:00:00Z' },
  { key: 'instagram-ads', name: 'Instagram Ads', icon: 'instagram', color: '#E1306C', status: 'connected', handle: '@archify.io', scopes: ['ads_read', 'ads_management'], lastSync: '2026-09-05T03:30:00Z' },
  { key: 'x-ads', name: 'X (Twitter) Ads', icon: 'twitter', color: '#ffffff', status: 'connected', handle: '@archify', scopes: ['ads_read', 'tweet_read'], lastSync: '2026-09-05T02:15:00Z' },
  { key: 'linkedin-ads', name: 'LinkedIn Ads', icon: 'linkedin', color: '#0A66C2', status: 'connected', handle: 'archify-marketing', scopes: ['r_ads', 'r_ads_reporting', 'w_member_social'], lastSync: '2026-09-04T23:30:00Z' },
  { key: 'youtube-ads', name: 'YouTube Ads', icon: 'youtube', color: '#FF0000', status: 'pending', handle: null, scopes: ['adwords.readonly'], lastSync: null },
  { key: 'google-ads', name: 'Google Ads', icon: 'globe', color: '#4285F4', status: 'connected', handle: 'archify-bm', scopes: ['adwords'], lastSync: '2026-09-05T01:20:00Z' },
];

const SEED_CAMPAIGNS = [
  {
    id: 'cmp-001',
    name: 'Enterprise · Q4 Pipeline Push',
    stage: 'live',
    product: 'Archify Enterprise',
    audience: 'CTO · VP Eng · 500-5000 seats',
    budget: 180000,
    spent: 78420,
    channels: ['linkedin-ads', 'google-ads', 'x-ads'],
    start: '2026-09-01',
    end: '2026-09-21',
    kpi: { impressions: 1240000, ctr: 0.018, leads: 184, cpl: 426, mqls: 62 },
    owner: 'Anjali Rao',
    creative: ['Enterprise ROI Calculator · LP', '“From codebase to architecture in 60s” · 15s video', 'CTO testimonial · carousel'],
  },
  {
    id: 'cmp-002',
    name: 'Launch · Archify Studio',
    stage: 'build',
    product: 'Archify Studio',
    audience: 'Indie devs · agencies · SaaS founders',
    budget: 95000,
    spent: 4200,
    channels: ['x-ads', 'instagram-ads', 'youtube-ads'],
    start: '2026-09-12',
    end: '2026-10-12',
    kpi: { impressions: 24000, ctr: 0.024, leads: 12, cpl: 350, mqls: 4 },
    owner: 'Karan Bhatia',
    creative: ['Waitlist · LP', 'Founder AMA · 30s reel', 'Before/After · comparison post'],
  },
  {
    id: 'cmp-003',
    name: 'Always-On · Retargeting',
    stage: 'live',
    product: 'Archify OSS',
    audience: 'Site visitors · GitHub engagers',
    budget: 40000,
    spent: 28190,
    channels: ['google-ads', 'x-ads'],
    start: '2026-08-15',
    end: '2026-09-30',
    kpi: { impressions: 612000, ctr: 0.034, leads: 86, cpl: 328, mqls: 28 },
    owner: 'Riya Mukherjee',
    creative: ['Demo · 60s walkthrough', 'Free tier · LP', 'GitHub star · social proof'],
  },
  {
    id: 'cmp-004',
    name: 'A/B Test · Hero copy v3',
    stage: 'test',
    product: 'Archify Cloud',
    audience: 'Cold traffic · paid social',
    budget: 25000,
    spent: 8120,
    channels: ['linkedin-ads', 'x-ads'],
    start: '2026-09-03',
    end: '2026-09-13',
    kpi: { impressions: 88000, ctr: 0.022, leads: 22, cpl: 369, mqls: 7 },
    owner: 'Vikram Shah',
    creative: ['“Maps from a sentence” · LP', 'Architecture · LP', 'Pricing · LP'],
  },
  {
    id: 'cmp-005',
    name: 'Webinar · Enterprise Onboarding',
    stage: 'plan',
    product: 'Archify Enterprise',
    audience: 'Existing customers · ops leads',
    budget: 18000,
    spent: 0,
    channels: ['linkedin-ads', 'x-ads'],
    start: '2026-09-22',
    end: '2026-09-26',
    kpi: { impressions: 0, ctr: 0, leads: 0, cpl: 0, mqls: 0 },
    owner: 'Anjali Rao',
    creative: ['Webinar · LP', 'Speaker cards · carousel', 'Calendar · LP'],
  },
];

const STAGES = [
  { id: 'plan', name: 'Plan', desc: 'Audience, channel mix, budget' },
  { id: 'build', name: 'Build', desc: 'Creative assets, copy, landing pages' },
  { id: 'test', name: 'Test', desc: 'A/B variants, segment proofs' },
  { id: 'live', name: 'Launch', desc: 'Spend on, monitor vitals' },
  { id: 'wrap', name: 'Wrap-up', desc: 'Report, archive, learnings' },
];

const SEED_AUDIENCES = [
  { id: 'a-1', name: 'CTO · APAC · 500+ seats', size: 14200, source: 'LinkedIn', updated: '2026-09-04T10:00:00Z' },
  { id: 'a-2', name: 'VP Eng · India', size: 4800, source: 'LinkedIn + intent', updated: '2026-09-03T18:30:00Z' },
  { id: 'a-3', name: 'GitHub stargazers · 30d', size: 9200, source: 'Custom import', updated: '2026-09-05T02:00:00Z' },
  { id: 'a-4', name: 'Site visitors · pricing page', size: 3140, source: 'Pixel', updated: '2026-09-05T03:15:00Z' },
  { id: 'a-5', name: 'Lookalike · top customers', size: 22000, source: 'Modelled', updated: '2026-09-02T14:00:00Z' },
];

const SEED_CREATIVES = [
  { id: 'cr-1', title: 'Enterprise ROI Calculator', type: 'LP', format: 'Web', size: '1.2 MB', updated: '2026-09-02T14:00:00Z', tags: ['LP', 'enterprise', 'calculator'] },
  { id: 'cr-2', title: '“From codebase to architecture in 60s”', type: 'Video', format: 'MP4 1080p', size: '14 MB', updated: '2026-09-01T09:30:00Z', tags: ['video', 'demo', '15s'] },
  { id: 'cr-3', title: 'CTO testimonial carousel', type: 'Carousel', format: 'JPG · 5 cards', size: '4.2 MB', updated: '2026-09-03T11:00:00Z', tags: ['social proof', 'carousel'] },
  { id: 'cr-4', title: 'Founder AMA reel', type: 'Video', format: 'MP4 1080p', size: '22 MB', updated: '2026-09-04T16:00:00Z', tags: ['video', 'founder', '30s'] },
  { id: 'cr-5', title: 'Before/After comparison post', type: 'Image', format: 'PNG 1080×1080', size: '780 KB', updated: '2026-09-04T18:00:00Z', tags: ['comparison', 'static'] },
  { id: 'cr-6', title: 'Architecture map sample · LP', type: 'LP', format: 'Web', size: '900 KB', updated: '2026-09-05T01:00:00Z', tags: ['LP', 'demo', 'sample'] },
];