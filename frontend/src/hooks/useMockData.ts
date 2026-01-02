
import { useState, useEffect } from 'react';
import {
    Lead, Client, ActivityLog, PlatformStats, LeadStatus, ClientStatus, ActivityType,
    ChartDataPoint, VoiceAgent, AgentStatus, CallLog, CallStatus, AutomationSettings,
    AgentAggressiveness, TrainingData, TrainingStatus, ModelPerformanceDataPoint, ABTest, KnowledgeBaseDocument
} from '../types.ts';

const ALL_INDUSTRIES = ['Digital Agency', 'Solar', 'Real Estate', 'SaaS', 'E-commerce', 'Fintech', 'Healthcare', 'Construction', 'Manufacturing', 'Logistics', 'Hospitality'];
const companySuffixes = ['Solutions', 'Group', 'Inc.', 'LLC', 'Co.', 'Systems'];
const firstNames = ['Alex', 'Jordan', 'Taylor', 'Casey', 'Morgan', 'Jamie'];
const lastNames = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia'];

const generateRandomName = () => `${firstNames[Math.floor(Math.random() * firstNames.length)]} ${lastNames[Math.floor(Math.random() * lastNames.length)]}`;
const generateCompanyName = (industries: string[]) => {
    const industry = industries.length > 0 ? industries[Math.floor(Math.random() * industries.length)] : 'General';
    return `${firstNames[Math.floor(Math.random() * firstNames.length)]}'s ${industry} ${companySuffixes[Math.floor(Math.random() * companySuffixes.length)]}`;
};

const aggressivenessSettings: Record<AgentAggressiveness, { interval: number, callChance: number, appointmentChance: number }> = {
    'Cautious': { interval: 8000, callChance: 0.2, appointmentChance: 0.03 },
    'Balanced': { interval: 5000, callChance: 0.4, appointmentChance: 0.05 },
    'Aggressive': { interval: 3000, callChance: 0.6, appointmentChance: 0.07 },
};

export const useMockData = (settings: AutomationSettings) => {
    const [loading, setLoading] = useState(true);
    const [leads, setLeads] = useState<Lead[]>([]);
    const [clients, setClients] = useState<Client[]>([]);
    const [activities, setActivities] = useState<ActivityLog[]>([]);
    const [chartData, setChartData] = useState<ChartDataPoint[]>([]);
    const [agents, setAgents] = useState<VoiceAgent[]>([]);
    const [callLogs, setCallLogs] = useState<CallLog[]>([]);
    const [trainingData, setTrainingData] = useState<TrainingData | null>(null);
    const [stats, setStats] = useState<PlatformStats>({
        totalClients: 0,
        activeCampaigns: 0,
        leadsToday: 0,
        appointmentsToday: 0,
    });
    const [modelPerformanceBonus, setModelPerformanceBonus] = useState(0);

    const generateInitialData = (currentSettings: AutomationSettings) => {
        const targetIndustries = currentSettings.targetIndustries.length > 0 ? currentSettings.targetIndustries : ALL_INDUSTRIES;

        const initialLeads: Lead[] = Array.from({ length: 20 }, (_, i) => ({
            id: `lead_${i}`,
            companyName: generateCompanyName(targetIndustries),
            industry: targetIndustries[Math.floor(Math.random() * targetIndustries.length)],
            status: 'Scraped',
            contactedAt: new Date(),
            contactPerson: generateRandomName(),
            website: `example${i}.com`,
            score: Math.floor(Math.random() * 60) + 40,
        }));

        const initialClients: Client[] = Array.from({ length: 8 }, (_, i) => ({
            id: `client_${i}`,
            name: generateCompanyName(targetIndustries),
            industry: targetIndustries[Math.floor(Math.random() * targetIndustries.length)],
            status: (['Active', 'Trial', 'Paused'] as ClientStatus[])[i % 3],
            leadsGenerated: Math.floor(Math.random() * 500),
            appointmentsBooked: Math.floor(Math.random() * 50),
            campaignStartDate: new Date(Date.now() - Math.random() * 30 * 24 * 60 * 60 * 1000),
            tier: (['Standard', 'Premium', 'Enterprise'] as const)[i % 3],
        }));

        const initialAgents: VoiceAgent[] = [
            { id: 'agent_1', name: 'Apollo', avatarUrl: '/avatars/apollo.svg', status: 'Idle', currentTarget: 'N/A', callsMade: 128, appointmentsBooked: 7 },
            { id: 'agent_2', name: 'Athena', avatarUrl: '/avatars/athena.svg', status: 'Idle', currentTarget: 'N/A', callsMade: 142, appointmentsBooked: 9 },
            { id: 'agent_3', name: 'Orion', avatarUrl: '/avatars/orion.svg', status: 'Idle', currentTarget: 'N/A', callsMade: 110, appointmentsBooked: 5 },
        ];

        const initialCallLogs: CallLog[] = Array.from({ length: 5 }, (_, i) => {
            const agent = initialAgents[i % initialAgents.length];
            const companyName = generateCompanyName(targetIndustries);
            const statusOptions: CallStatus[] = ['Completed', 'Voicemail', 'No Answer', 'Appointment Set'];
            const status = statusOptions[Math.floor(Math.random() * statusOptions.length)];
            return {
                id: `call_${i}`, agent, companyName, industry: targetIndustries[Math.floor(Math.random() * targetIndustries.length)],
                status, duration: Math.floor(Math.random() * 180) + 20, timestamp: new Date(Date.now() - Math.random() * 60 * 60 * 1000),
            };
        });

        const initialActivities: ActivityLog[] = [
            { id: 'act_1', timestamp: new Date(), message: 'Orchestrator started. System is online.', type: 'success' },
            { id: 'act_2', timestamp: new Date(Date.now() - 10000), message: `Scraping new leads for industries: ${targetIndustries.join(', ')}.`, type: 'info' },
        ];

        const initialChartData = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(day => ({
            day, leads: Math.floor(Math.random() * 25) + 10, appointments: Math.floor(Math.random() * 8) + 1,
        }));

        const initialTrainingData: TrainingData = {
            status: 'Idle',
            lastTrained: new Date(Date.now() - 24 * 60 * 60 * 1000),
            performanceHistory: Array.from({ length: 7 }, (_, i) => ({ date: `Day ${i + 1}`, accuracy: 0.85 + i * 0.01 + Math.random() * 0.01 })),
            knowledgeBase: [
                { id: 'kb_1', name: 'Product Spec v2.1', type: 'Product Spec', ingestedAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000), size: '128 KB' },
                { id: 'kb_2', name: 'Objection Handling Guide', type: 'Objection Handling', ingestedAt: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000), size: '64 KB' },
            ],
            activeABTest: {
                id: 'ab_1',
                scriptA: { name: 'Standard Opener', content: 'Hi, this is [Agent Name] from AuraLeads...', conversionRate: 5.1 },
                scriptB: { name: 'Question Opener', content: 'Hi, quick question - who handles your lead generation?', conversionRate: 5.8 },
                impressions: 1450, winner: 'B',
            }
        };

        setLeads(initialLeads.sort((a, b) => b.score - a.score));
        setClients(initialClients);
        setActivities(initialActivities);
        setChartData(initialChartData);
        setAgents(initialAgents);
        setCallLogs(initialCallLogs.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime()));
        setTrainingData(initialTrainingData);
        setStats({
            totalClients: initialClients.length,
            activeCampaigns: initialClients.filter(c => c.status === 'Active').length,
            leadsToday: initialChartData[initialChartData.length - 1].leads,
            appointmentsToday: initialChartData[initialChartData.length - 1].appointments,
        });
        setLoading(false);
    };

    useEffect(() => {
        setLoading(true);
        const timer = setTimeout(() => {
            generateInitialData(settings);
            fetchRealLeads();
        }, 1000);
        return () => clearTimeout(timer);
    }, [settings]);

    const fetchRealLeads = async () => {
        try {
            const response = await fetch('http://localhost:8000/api/leads/');
            if (!response.ok) throw new Error('Failed to fetch');

            const data = await response.json();
            const realLeads: Lead[] = data.map((l: any) => ({
                id: l.id,
                companyName: l.company_name,
                industry: l.category,
                status: l.status === 'new' ? 'Scraped' : l.status,
                contactedAt: new Date(l.created_at),
                contactPerson: l.contact_name || 'N/A',
                website: l.website || 'N/A',
                score: l.lead_score
            }));

            if (realLeads.length > 0) {
                setLeads(prev => [...realLeads, ...prev].slice(0, 100)); // Keep mock leads too? No, let's prioritize real
                setLeads(realLeads);
                setStats(prev => ({ ...prev, leadsToday: realLeads.length, activeCampaigns: prev.activeCampaigns + 1 }));
                setActivities(prev => [{ id: `act_real_${Date.now()}`, timestamp: new Date(), message: `Loaded ${realLeads.length} real leads from Growth Engine.`, type: 'success' }, ...prev]);
            }
        } catch (error) {
            console.error("Failed to fetch real leads:", error);
            setActivities(prev => [{ id: `act_err_${Date.now()}`, timestamp: new Date(), message: `Connected to API but no leads found yet. Check Growth Engine.`, type: 'warning' }, ...prev]);
        }
    };

    useEffect(() => {
        if (loading) return;

        const { interval, callChance, appointmentChance } = aggressivenessSettings[settings.agentAggressiveness];

        const agentActivityInterval = setInterval(() => {
            setAgents(prevAgents => {
                const agentToUpdateIndex = Math.floor(Math.random() * prevAgents.length);
                const agentToUpdate = { ...prevAgents[agentToUpdateIndex] };
                const newAgents = [...prevAgents];
                const targetIndustries = settings.targetIndustries.length > 0 ? settings.targetIndustries : ALL_INDUSTRIES;

                if (agentToUpdate.status === 'Idle' && Math.random() < callChance) {
                    agentToUpdate.status = 'Dialing';
                    agentToUpdate.currentTarget = generateCompanyName(targetIndustries);
                    setActivities(prev => [{ id: `act_${Date.now()}`, timestamp: new Date(), message: `${agentToUpdate.name} is dialing ${agentToUpdate.currentTarget}.`, type: 'info' }, ...prev.slice(0, 49)]);
                } else if (agentToUpdate.status === 'Dialing') {
                    agentToUpdate.status = 'In Call';
                } else if (agentToUpdate.status === 'In Call') {
                    agentToUpdate.status = 'Idle';
                    const isAppointment = Math.random() < (appointmentChance + modelPerformanceBonus);
                    const statusOptions: CallStatus[] = isAppointment ? ['Appointment Set'] : ['Completed', 'Voicemail', 'No Answer'];
                    const callStatus = statusOptions[Math.floor(Math.random() * statusOptions.length)];

                    const newCallLog: CallLog = {
                        id: `call_${Date.now()}`, agent: agentToUpdate, companyName: agentToUpdate.currentTarget,
                        industry: targetIndustries[Math.floor(Math.random() * targetIndustries.length)],
                        status: callStatus, duration: Math.floor(Math.random() * 180) + 20, timestamp: new Date(),
                    };
                    setCallLogs(prev => [newCallLog, ...prev.slice(0, 49)]);

                    agentToUpdate.callsMade += 1;
                    if (callStatus === 'Appointment Set') {
                        agentToUpdate.appointmentsBooked += 1;
                        setStats(s => ({ ...s, appointmentsToday: s.appointmentsToday + 1 }));
                        setActivities(prev => [{ id: `act_${Date.now()}`, timestamp: new Date(), message: `Appointment set by ${agentToUpdate.name} with ${agentToUpdate.currentTarget}!`, type: 'success' }, ...prev.slice(0, 49)]);
                    }
                    agentToUpdate.currentTarget = 'N/A';
                }

                newAgents[agentToUpdateIndex] = agentToUpdate;
                return newAgents;
            });
        }, interval);

        const trainingInterval = setInterval(() => {
            const trainingCycle: TrainingStatus[] = ['Ingesting Data', 'Processing Embeddings', 'Training Model', 'Deploying', 'Idle'];
            let i = 0;
            const cycle = () => {
                setTrainingData(prev => prev ? ({ ...prev, status: trainingCycle[i] }) : null);
                setActivities(prev => [{ id: `act_train_${Date.now()}`, timestamp: new Date(), message: `ML Pipeline: ${trainingCycle[i]}...`, type: 'info' }, ...prev.slice(0, 49)]);
                i++;
                if (i < trainingCycle.length) {
                    setTimeout(cycle, 4000);
                } else {
                    const perfGain = Math.random() * 0.005;
                    setModelPerformanceBonus(prev => prev + perfGain);
                    setTrainingData(prev => {
                        if (!prev) return null;
                        const newPerf = [...prev.performanceHistory, { date: `Day ${prev.performanceHistory.length + 1}`, accuracy: prev.performanceHistory[prev.performanceHistory.length - 1].accuracy + perfGain * 2 }];
                        return { ...prev, lastTrained: new Date(), performanceHistory: newPerf.slice(-7) };
                    });
                    setActivities(prev => [{ id: `act_train_done_${Date.now()}`, timestamp: new Date(), message: `Nightly model training complete. Performance improved by ${(perfGain * 100).toFixed(2)}%.`, type: 'success' }, ...prev.slice(0, 49)]);
                }
            };
            cycle();
        }, 60000); // Run training cycle every minute

        return () => {
            clearInterval(agentActivityInterval);
            clearInterval(trainingInterval);
        };
    }, [loading, settings, modelPerformanceBonus]);

    return { loading, leads, clients, activities, stats, chartData, agents, callLogs, trainingData };
};
