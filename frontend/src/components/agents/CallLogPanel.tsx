
import React, { useState } from 'react';
import { CallLog, CallStatus } from '../../types.ts';
import Card from '../ui/Card.tsx';
import { PhoneIcon, VoicemailIcon, NoAnswerIcon, AppointmentSetIcon } from '../ui/icons.tsx';
import { generateCallTranscript } from '../../services/geminiService.ts';

interface CallLogPanelProps {
  callLogs: CallLog[];
  loading: boolean;
}

const statusInfo: Record<CallStatus, { icon: React.FC<any>; color: string }> = {
  'Completed': { icon: PhoneIcon, color: 'text-blue-400' },
  'Voicemail': { icon: VoicemailIcon, color: 'text-yellow-400' },
  'No Answer': { icon: NoAnswerIcon, color: 'text-gray-500' },
  'Appointment Set': { icon: AppointmentSetIcon, color: 'text-green-400' },
};

const TranscriptViewer: React.FC<{ call: CallLog }> = ({ call }) => {
    const [transcript, setTranscript] = useState(call.transcript || '');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');

    const fetchTranscript = async () => {
        if (transcript) return;
        setIsLoading(true);
        setError('');
        try {
            const generatedTranscript = await generateCallTranscript(call.agent.name, call.companyName, call.industry, call.status);
            setTranscript(generatedTranscript);
            call.transcript = generatedTranscript; // Cache for session
        } catch (err: any) {
            setError(err.message || 'Failed to load transcript.');
        } finally {
            setIsLoading(false);
        }
    };

    React.useEffect(() => {
        fetchTranscript();
    }, []);

    return (
        <div className="mt-4 pt-4 border-t border-gray-700/50">
            {isLoading && <div className="text-sm text-gray-400 animate-pulse">Generating transcript...</div>}
            {error && <div className="text-sm text-red-400">{error}</div>}
            {transcript && (
                <div className="text-xs text-gray-400 font-mono space-y-2">
                    {transcript.split('\n').map((line, i) => (
                        <p key={i} className={line.startsWith(call.agent.name) ? 'text-gray-300' : ''}>
                            {line}
                        </p>
                    ))}
                </div>
            )}
        </div>
    );
};

const CallLogRow: React.FC<{ call: CallLog }> = ({ call }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const { icon: Icon, color } = statusInfo[call.status];
  
  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <li className="py-4 px-2 -mx-2 rounded-lg hover:bg-gray-800/40 transition-colors duration-150">
      <div className="flex items-center space-x-4 cursor-pointer" onClick={() => setIsExpanded(!isExpanded)}>
        <div className="flex-shrink-0">
          <Icon className={`h-5 w-5 ${color}`} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">{call.companyName}</p>
          <p className="text-sm text-gray-500 truncate">
            {call.agent.name} • {call.timestamp.toLocaleTimeString()}
          </p>
        </div>
        <div className="text-right">
          <p className={`text-sm font-semibold ${color}`}>{call.status}</p>
          <p className="text-sm text-gray-500">{formatDuration(call.duration)}</p>
        </div>
      </div>
      {isExpanded && <TranscriptViewer call={call} />}
    </li>
  );
};

const CallLogPanel: React.FC<CallLogPanelProps> = ({ callLogs, loading }) => {
  const renderSkeleton = () => (
    <div className="space-y-4">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="flex items-center space-x-4 animate-pulse">
          <div className="h-6 w-6 rounded-full bg-gray-700/50"></div>
          <div className="flex-1 space-y-2">
            <div className="h-4 bg-gray-700/50 rounded w-3/4"></div>
            <div className="h-3 bg-gray-700/50 rounded w-1/2"></div>
          </div>
          <div className="w-24 h-4 bg-gray-700/50 rounded"></div>
        </div>
      ))}
    </div>
  );

  return (
    <Card className="p-6">
      {loading ? renderSkeleton() : (
        <ul className="divide-y divide-gray-800">
          {callLogs.map(log => <CallLogRow key={log.id} call={log} />)}
        </ul>
      )}
    </Card>
  );
};

export default CallLogPanel;
