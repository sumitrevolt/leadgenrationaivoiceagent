import { useState } from 'react';
import { ShieldAlert, Play, Pause, AlertTriangle, Activity } from 'lucide-react';
import { Card, CardHeader, Badge, Button, ConfirmDialog } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/Toast';

export interface AgentStatus {
  id: string;
  name: string;
  workstream: string;
  state: 'building' | 'verifying' | 'blocked' | 'idle';
  load: number;
}

export function OrchestrationView() {
  const toast = useToast();
  const [agents] = useState<AgentStatus[]>([
    { id: 'WS-01-001', name: 'Vikram', workstream: 'Engineering', state: 'building', load: 85 },
    { id: 'WS-02-005', name: 'Tara', workstream: 'Voice', state: 'blocked', load: 40 },
    { id: 'WS-03-012', name: 'Rohan', workstream: 'Leads', state: 'idle', load: 10 },
  ]);

  const [killTarget, setKillTarget] = useState<AgentStatus | null>(null);

  const handleKill = () => {
    toast.error('Emergency Shutdown', `Agent ${killTarget?.name} stopped immediately.`);
    setKillTarget(null);
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map((agent) => (
          <Card key={agent.id} className="p-4">
            <div className="flex justify-between items-start mb-3">
              <div>
                <p className="text-sm font-semibold">{agent.name}</p>
                <p className="text-xs text-muted">{agent.workstream} · {agent.id}</p>
              </div>
              <Badge tone={agent.state === 'blocked' ? 'danger' : 'neutral'}>{agent.state}</Badge>
            </div>
            
            <div className="flex items-center gap-2">
              <Button size="sm" variant="secondary" leftIcon={<Pause className="h-3 w-3" />}>Pause</Button>
              <Button size="sm" variant="danger" onClick={() => setKillTarget(agent)} leftIcon={<ShieldAlert className="h-3 w-3" />}>Kill</Button>
            </div>
          </Card>
        ))}
      </div>

      <ConfirmDialog
        open={!!killTarget}
        onClose={() => setKillTarget(null)}
        onConfirm={handleKill}
        destructive
        title={`Execute forced shutdown for ${killTarget?.name}?`}
        description="This will instantly terminate all active processes for this engineer agent."
        confirmLabel="Confirm Shutdown"
      />
    </div>
  );
}
