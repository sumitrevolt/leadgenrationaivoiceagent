import React from 'react';
import Card from './ui/Card.tsx';
import { useDashboardData } from '../hooks/useDashboardData.ts';
import type { AdminDashboardClient } from '../services/api.ts';

const statusStyles: Record<string, { bg: string; text: string; border: string }> = {
  active: { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/30' },
  trial: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30' },
  paused: { bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/30' },
  churned: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30' },
};

const fmtMRR = (n: number): string => {
  if (n >= 1_00_000) return `₹${(n / 1_00_000).toFixed(2)} L`;
  return `₹${new Intl.NumberFormat('en-IN').format(n)}`;
};

const ClientCard: React.FC<{ client: AdminDashboardClient }> = ({ client }) => {
  const key = (client.status || 'active').toLowerCase();
  const styles = statusStyles[key] || statusStyles.active;
  return (
    <Card className={`p-6 flex flex-col justify-between border-t-4 ${styles.border} hover:bg-[#181818] transition-all duration-200`}>
      <div>
        <div className="flex justify-between items-start">
          <h4 className="font-bold text-lg text-white">{client.company}</h4>
          <span className={`px-2.5 py-1 text-xs font-semibold rounded-full capitalize ${styles.bg} ${styles.text}`}>
            {client.status}
          </span>
        </div>
        <p className="text-sm text-gray-400 mt-1 capitalize">{client.niche}</p>
      </div>
      <div className="mt-6 space-y-4">
        <div className="flex justify-between items-baseline">
          <span className="text-sm text-gray-400">Leads Delivered</span>
          <span className="font-semibold text-white">{client.leads_delivered.toLocaleString('en-IN')}</span>
        </div>
        <div className="flex justify-between items-baseline">
          <span className="text-sm text-gray-400">MRR</span>
          <span className="font-semibold text-white">{fmtMRR(client.mrr)}</span>
        </div>
        <div className="flex justify-between items-baseline">
          <span className="text-sm text-gray-400">Plan</span>
          <span className="font-semibold text-white">{client.plan}</span>
        </div>
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
  </Card>
);

const Clients: React.FC = () => {
  const { data, loading, error } = useDashboardData(30000);
  const clients = data?.clients ?? [];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-xl font-semibold text-white">Client Management</h3>
        {data?.is_sample_data && (
          <span className="text-xs text-yellow-300/90 bg-yellow-900/10 border border-yellow-700/40 rounded-full px-3 py-1">
            sample data
          </span>
        )}
      </div>

      {error && !data ? (
        <Card className="p-8 text-center">
          <h4 className="text-lg font-medium text-red-400">Clients load nahi hue</h4>
          <p className="text-gray-500 mt-2 text-sm">{error}</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {loading ? (
            [...Array(8)].map((_, i) => <SkeletonCard key={i} />)
          ) : (
            clients.map((client, i) => <ClientCard key={`${client.company}-${i}`} client={client} />)
          )}
        </div>
      )}

      {!loading && !error && clients.length === 0 && (
        <Card className="p-8 text-center">
          <h4 className="text-lg font-medium text-white">No clients onboarded yet.</h4>
          <p className="text-gray-400 mt-2">Client onboard hote hi yahan dikhenge.</p>
        </Card>
      )}
    </div>
  );
};

export default Clients;
