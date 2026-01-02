
import React from 'react';
import { VoiceAgent, AgentStatus } from '../../types.ts';
import Card from '../ui/Card.tsx';

interface VoiceAgentCardProps {
  agent: VoiceAgent | null;
  loading: boolean;
}

const statusStyles: Record<AgentStatus, { bg: string; text: string; ring: string }> = {
  'Idle': { bg: 'bg-gray-500/10', text: 'text-gray-400', ring: 'ring-gray-500/20' },
  'Dialing': { bg: 'bg-blue-500/10', text: 'text-blue-400', ring: 'ring-blue-500/20' },
  'In Call': { bg: 'bg-red-500/10', text: 'text-red-400', ring: 'ring-red-500/20' },
  'Onboarding': { bg: 'bg-green-500/10', text: 'text-green-400', ring: 'ring-green-500/20' },
  'Training': { bg: 'bg-yellow-500/10', text: 'text-yellow-400', ring: 'ring-yellow-500/20' },
};

const Skeleton: React.FC = () => (
  <Card className="p-6 animate-pulse">
    <div className="flex items-center space-x-4">
      <div className="w-16 h-16 rounded-full bg-gray-700/50"></div>
      <div className="flex-1 space-y-2">
        <div className="h-6 bg-gray-700/50 rounded w-3/5"></div>
        <div className="h-5 w-24 bg-gray-700/50 rounded-full"></div>
      </div>
    </div>
    <div className="mt-6 space-y-3">
      <div className="h-4 bg-gray-700/50 rounded w-full"></div>
      <div className="h-4 bg-gray-700/50 rounded w-3/4"></div>
      <div className="h-4 bg-gray-700/50 rounded w-1/2"></div>
    </div>
  </Card>
);

const VoiceAgentCard: React.FC<VoiceAgentCardProps> = ({ agent, loading }) => {
  if (loading || !agent) {
    return <Skeleton />;
  }

  const styles = statusStyles[agent.status];
  const isBusy = agent.status === 'Dialing' || agent.status === 'In Call';

  return (
    <Card className="p-6 flex flex-col justify-between transition-all duration-300 hover:bg-gray-900/50">
      <div>
        <div className="flex items-center space-x-4">
          <div className={`relative w-16 h-16 rounded-full flex-shrink-0 ${styles.ring} ring-4`}>
            <img src={`https://api.dicebear.com/8.x/bottts-neutral/svg?seed=${agent.name}`} alt={`${agent.name} avatar`} className="rounded-full" />
            {isBusy && <span className="absolute bottom-0 right-0 block h-4 w-4 rounded-full bg-red-500 border-2 border-[#101010] animate-pulse"></span>}
          </div>
          <div>
            <h4 className="font-bold text-xl text-white">{agent.name}</h4>
            <span className={`px-2.5 py-0.5 text-xs font-semibold rounded-full ${styles.bg} ${styles.text}`}>
              {agent.status}
            </span>
          </div>
        </div>
        <div className="mt-6 text-sm space-y-2">
          <div className="flex justify-between">
            <span className="text-gray-400">Current Target:</span>
            <span className="font-medium text-gray-200 truncate" title={agent.currentTarget}>{agent.currentTarget}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Calls Today:</span>
            <span className="font-medium text-white">{agent.callsMade}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Appointments Set:</span>
            <span className="font-medium text-green-400">{agent.appointmentsBooked}</span>
          </div>
        </div>
      </div>
      <div className="mt-4 h-6 flex items-center">
        {agent.status === 'In Call' && (
          <div className="w-full flex items-center space-x-2">
            <span className="text-red-400 text-xs font-mono">LIVE</span>
            <svg className="w-full h-6 waveform" viewBox="0 0 40 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M 0 12 C 5 12, 5 4, 10 4 C 15 4, 15 12, 20 12 C 25 12, 25 20, 30 20 C 35 20, 35 12, 40 12" stroke="#ef4444" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </div>
        )}
      </div>
    </Card>
  );
};

export default VoiceAgentCard;
