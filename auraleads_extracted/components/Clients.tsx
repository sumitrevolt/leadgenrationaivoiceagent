
import React from 'react';
import { Client, ClientStatus } from '../types.ts';
import Card from './ui/Card.tsx';

interface ClientsProps {
  clients: Client[];
  loading: boolean;
}

const statusStyles: Record<ClientStatus, { bg: string; text: string; border: string }> = {
  Active: { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/30' },
  Trial: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30' },
  Paused: { bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/30' },
  Churned: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30' },
};

const ClientCard: React.FC<{ client: Client }> = ({ client }) => {
  const styles = statusStyles[client.status];
  return (
    <Card className={`p-6 flex flex-col justify-between border-t-4 ${styles.border} hover:bg-[#181818] transition-all duration-200`}>
      <div>
        <div className="flex justify-between items-start">
          <h4 className="font-bold text-lg text-white">{client.name}</h4>
          <span className={`px-2.5 py-1 text-xs font-semibold rounded-full ${styles.bg} ${styles.text}`}>
            {client.status}
          </span>
        </div>
        <p className="text-sm text-gray-400 mt-1">{client.industry}</p>
      </div>
      <div className="mt-6 space-y-4">
        <div className="flex justify-between items-baseline">
          <span className="text-sm text-gray-400">Leads Generated</span>
          <span className="font-semibold text-white">{client.leadsGenerated.toLocaleString()}</span>
        </div>
        <div className="flex justify-between items-baseline">
          <span className="text-sm text-gray-400">Appointments Booked</span>
          <span className="font-semibold text-white">{client.appointmentsBooked.toLocaleString()}</span>
        </div>
        <div className="flex justify-between items-baseline">
          <span className="text-sm text-gray-400">Subscription Tier</span>
          <span className="font-semibold text-white">{client.tier}</span>
        </div>
      </div>
      <div className="mt-6 pt-4 border-t border-gray-800 text-xs text-gray-500">
        Campaign Started: {client.campaignStartDate.toLocaleDateString()}
      </div>
    </Card>
  );
};

const SkeletonCard: React.FC = () => (
  <Card className="p-6 animate-pulse">
    <div className="flex justify-between items-start">
      <div className="h-6 bg-gray-700/50 rounded w-3/5"></div>
      <div className="h-6 w-16 bg-gray-700/50 rounded-full"></div>
    </div>
    <div className="h-4 bg-gray-700/50 rounded w-2/5 mt-2"></div>
    <div className="mt-6 space-y-4">
      <div className="flex justify-between items-center">
        <div className="h-4 bg-gray-700/50 rounded w-1/3"></div>
        <div className="h-5 bg-gray-700/50 rounded w-1/4"></div>
      </div>
      <div className="flex justify-between items-center">
        <div className="h-4 bg-gray-700/50 rounded w-1/2"></div>
        <div className="h-5 bg-gray-700/50 rounded w-1/6"></div>
      </div>
    </div>
    <div className="mt-6 pt-4 border-t border-gray-800">
      <div className="h-3 bg-gray-700/50 rounded w-1/3"></div>
    </div>
  </Card>
);

const Clients: React.FC<ClientsProps> = ({ clients, loading }) => {
  return (
    <div>
      <h3 className="text-xl font-semibold text-white mb-6">Client Management</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {loading ? (
          [...Array(8)].map((_, i) => <SkeletonCard key={i} />)
        ) : (
          clients.map(client => <ClientCard key={client.id} client={client} />)
        )}
      </div>
      {!loading && clients.length === 0 && (
        <Card className="p-8 text-center col-span-full">
          <h4 className="text-lg font-medium text-white">No clients onboarded yet.</h4>
          <p className="text-gray-400 mt-2">Once a lead converts to a trial, they will appear here.</p>
        </Card>
      )}
    </div>
  );
};

export default Clients;
