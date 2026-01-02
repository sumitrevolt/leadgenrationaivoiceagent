
export type LeadStatus = 'Scraped' | 'Contacting' | 'Interested' | 'Trial' | 'Rejected';

export interface Lead {
  id: string;
  companyName: string;
  industry: string;
  status: LeadStatus;
  contactedAt: Date;
  contactPerson: string;
  website: string;
  score: number; // Lead score from 1-100
}

export type ClientStatus = 'Trial' | 'Active' | 'Paused' | 'Churned';

export interface Client {
  id: string;
  name: string;
  industry: string;
  status: ClientStatus;
  leadsGenerated: number;
  appointmentsBooked: number;
  campaignStartDate: Date;
  tier: 'Standard' | 'Premium' | 'Enterprise';
}

export type ActivityType = 'success' | 'info' | 'warning' | 'error';

export interface ActivityLog {
  id: string;
  timestamp: Date;
  message: string;
  type: ActivityType;
}

export interface PlatformStats {
  totalClients: number;
  activeCampaigns: number;
  leadsToday: number;
  appointmentsToday: number;
}

export interface ChartDataPoint {
  day: string;
  leads: number;
  appointments: number;
}

export type AgentStatus = 'Idle' | 'Dialing' | 'In Call' | 'Onboarding' | 'Training';

export interface VoiceAgent {
  id: string;
  name: string;
  avatarUrl: string;
  status: AgentStatus;
  currentTarget: string;
  callsMade: number;
  appointmentsBooked: number;
}

export type CallStatus = 'Completed' | 'Voicemail' | 'No Answer' | 'Appointment Set';

export interface CallLog {
  id: string;
  agent: VoiceAgent;
  companyName: string;
  industry: string;
  status: CallStatus;
  duration: number; // in seconds
  timestamp: Date;
  transcript?: string;
}

export type AgentAggressiveness = 'Cautious' | 'Balanced' | 'Aggressive';

export interface AutomationSettings {
    targetIndustries: string[];
    monthlyLeadsGoal: number;
    monthlyAppointmentsGoal: number;
    agentAggressiveness: AgentAggressiveness;
    autoOnboardTrials: boolean;
}

export interface KnowledgeBaseDocument {
    id: string;
    name: string;
    type: 'Product Spec' | 'Objection Handling' | 'Competitor Analysis';
    ingestedAt: Date;
    size: string; // e.g., "128 KB"
}

export interface ABTest {
    id: string;
    scriptA: { name: string; content: string; conversionRate: number; };
    scriptB: { name: string; content: string; conversionRate: number; };
    impressions: number;
    winner: 'A' | 'B' | null;
}

export interface ModelPerformanceDataPoint {
    date: string;
    accuracy: number;
}

export type TrainingStatus = 'Idle' | 'Ingesting Data' | 'Processing Embeddings' | 'Training Model' | 'Deploying';

export interface TrainingData {
    status: TrainingStatus;
    lastTrained: Date;
    performanceHistory: ModelPerformanceDataPoint[];
    knowledgeBase: KnowledgeBaseDocument[];
    activeABTest: ABTest;
}
