
import React from 'react';
import { Lead, LeadStatus } from '../types.ts';
import Card from './ui/Card.tsx';
import { ScriptIcon, LeadScoreIcon } from './ui/icons.tsx';

interface MyCampaignProps {
  leads: Lead[];
  onOpenScriptAssistant: () => void;
  loading: boolean;
}

const statusColors: Record<LeadStatus, string> = {
  Scraped: 'bg-gray-600/20 text-gray-300',
  Contacting: 'bg-blue-600/20 text-blue-300',
  Interested: 'bg-yellow-600/20 text-yellow-300',
  Trial: 'bg-green-600/20 text-green-300',
  Rejected: 'bg-red-600/20 text-red-300',
};

const StatusBadge: React.FC<{ status: LeadStatus }> = ({ status }) => (
  <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${statusColors[status]}`}>
    {status}
  </span>
);

const LeadScoreBadge: React.FC<{ score: number }> = ({ score }) => {
  const getColor = () => {
    if (score > 85) return 'text-green-400';
    if (score > 65) return 'text-yellow-400';
    return 'text-red-400';
  };
  return (
    <div className="flex items-center space-x-2">
      <LeadScoreIcon className={`h-5 w-5 ${getColor()}`} />
      <span className={`font-semibold ${getColor()}`}>{score}</span>
    </div>
  );
};

const MyCampaign: React.FC<MyCampaignProps> = ({ leads, onOpenScriptAssistant, loading }) => {
  const renderSkeleton = () => (
    [...Array(10)].map((_, i) => (
      <tr key={i} className="border-b border-gray-800 animate-pulse">
        <td className="px-6 py-4"><div className="h-4 bg-gray-700/50 rounded w-3/4"></div></td>
        <td className="px-6 py-4"><div className="h-4 bg-gray-700/50 rounded w-1/2"></div></td>
        <td className="px-6 py-4"><div className="h-6 w-20 bg-gray-700/50 rounded-full"></div></td>
        <td className="px-6 py-4"><div className="h-4 bg-gray-700/50 rounded w-1/4"></div></td>
        <td className="px-6 py-4"><div className="h-5 w-10 bg-gray-700/50 rounded"></div></td>
      </tr>
    ))
  );

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-center">
        <h3 className="text-xl font-semibold text-white">My Lead Generation Funnel</h3>
        <button
          onClick={onOpenScriptAssistant}
          className="flex items-center justify-center px-4 py-2 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors duration-200 shadow-md"
        >
          <ScriptIcon className="h-5 w-5 mr-2" />
          AI Script Assistant
        </button>
      </div>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left text-gray-400">
            <thead className="text-xs text-gray-400 uppercase bg-[#181818]">
              <tr>
                <th scope="col" className="px-6 py-3">Company</th>
                <th scope="col" className="px-6 py-3">Industry</th>
                <th scope="col" className="px-6 py-3">Status</th>
                <th scope="col" className="px-6 py-3">Last Contact</th>
                <th scope="col" className="px-6 py-3">Lead Score</th>
              </tr>
            </thead>
            <tbody>
              {loading ? renderSkeleton() : leads.map((lead) => (
                <tr key={lead.id} className="border-b border-gray-800 hover:bg-gray-800/40 transition-colors duration-150">
                  <th scope="row" className="px-6 py-4 font-medium text-white whitespace-nowrap">
                    <div className="font-bold">{lead.companyName}</div>
                    <div className="text-xs text-gray-500">{lead.website}</div>
                  </th>
                  <td className="px-6 py-4">{lead.industry}</td>
                  <td className="px-6 py-4">
                    <StatusBadge status={lead.status} />
                  </td>
                  <td className="px-6 py-4">{lead.contactedAt.toLocaleDateString()}</td>
                  <td className="px-6 py-4">
                    <LeadScoreBadge score={lead.score} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {!loading && leads.length === 0 && (
        <Card className="p-8 text-center">
          <h4 className="text-lg font-medium text-white">No leads yet.</h4>
          <p className="text-gray-400 mt-2">The platform is warming up. Your scraped leads will appear here shortly.</p>
        </Card>
      )}
    </div>
  );
};

export default MyCampaign;
