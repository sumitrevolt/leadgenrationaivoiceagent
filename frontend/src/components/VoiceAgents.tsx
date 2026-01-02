
import React from 'react';
import { VoiceAgent, CallLog } from '../types.ts';
import VoiceAgentCard from './agents/VoiceAgentCard.tsx';
import CallLogPanel from './agents/CallLogPanel.tsx';

interface VoiceAgentsProps {
  agents: VoiceAgent[];
  callLogs: CallLog[];
  loading: boolean;
}

const VoiceAgents: React.FC<VoiceAgentsProps> = ({ agents, callLogs, loading }) => {
  const renderAgentSkeletons = () => (
    [...Array(3)].map((_, i) => <VoiceAgentCard key={i} agent={null} loading={true} />)
  );

  return (
    <div className="space-y-8">
      <div>
        <h3 className="text-xl font-semibold text-white mb-4">AI Agent Status</h3>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {loading ? renderAgentSkeletons() : agents.map(agent => (
            <VoiceAgentCard key={agent.id} agent={agent} loading={false} />
          ))}
        </div>
      </div>
      
      <div>
        <h3 className="text-xl font-semibold text-white mb-4">Live Call Log</h3>
        <CallLogPanel callLogs={callLogs} loading={loading} />
      </div>
    </div>
  );
};

export default VoiceAgents;
