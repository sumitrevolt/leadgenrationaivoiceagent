import React from 'react';
import { ChartDataPoint } from '../types.ts';
import Card from './ui/Card.tsx';
import LeadsChart from './charts/LeadsChart.tsx';
import { useDashboardData } from '../hooks/useDashboardData.ts';
import type { AdminDashboardAgent, AdminDashboardCampaign } from '../services/api.ts';

/** ₹ ko compact Indian format me (L / Cr) dikhao. */
const formatINR = (n: number): string => {
  if (n >= 1_00_00_000) return `₹${(n / 1_00_00_000).toFixed(2)} Cr`;
  if (n >= 1_00_000) return `₹${(n / 1_00_000).toFixed(2)} L`;
  return `₹${new Intl.NumberFormat('en-IN').format(n)}`;
};

const StatCard: React.FC<{ title: string; value: string | number; sub?: string; loading: boolean }> = ({
  title, value, sub, loading,
}) => (
  <Card className="p-6">
    <h3 className="text-sm font-medium text-gray-400">{title}</h3>
    {loading ? (
      <div className="h-10 w-24 bg-gray-700/50 rounded-md animate-pulse mt-2"></div>
    ) : (
      <>
        <p className="mt-2 text-3xl font-bold text-white">
          {typeof value === 'number' ? value.toLocaleString('en-IN') : value}
        </p>
        {sub && <p className="mt-1 text-xs text-gray-500">{sub}</p>}
      </>
    )}
  </Card>
);

const HealthPill: React.FC<{ label: string; state: string }> = ({ label, state }) => {
  const up = (state || '').toLowerCase() === 'up';
  return (
    <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-gray-800/40">
      <span className={`h-2.5 w-2.5 rounded-full ${up ? 'bg-green-500' : 'bg-red-500'}`}></span>
      <span className="text-xs text-gray-300">{label}</span>
      <span className={`text-xs font-medium ${up ? 'text-green-400' : 'text-red-400'}`}>{up ? 'up' : 'down'}</span>
    </div>
  );
};

const agentDot = (status: string): string => {
  switch ((status || '').toLowerCase()) {
    case 'calling': return 'bg-green-500';
    case 'scraping': return 'bg-blue-500';
    case 'error': return 'bg-red-500';
    case 'idle': return 'bg-gray-500';
    default: return 'bg-gray-500';
  }
};

/** Live agents + active campaigns se ek readable activity feed banao. */
function buildActivity(agents: AdminDashboardAgent[], campaigns: AdminDashboardCampaign[]) {
  const items: { id: string; dot: string; text: string }[] = [];
  agents.forEach((a) => {
    const verb = a.status === 'calling' ? 'calling for' : a.status === 'scraping' ? 'scraping for' : a.status;
    items.push({
      id: `agent-${a.id}`,
      dot: agentDot(a.status),
      text: `${a.name} — ${verb} ${a.current_client} · ${a.calls_made} calls, ${a.leads_found} leads`,
    });
  });
  campaigns
    .filter((c) => c.status === 'active')
    .forEach((c) => {
      items.push({
        id: `camp-${c.campaign}`,
        dot: 'bg-blue-500',
        text: `${c.campaign} (${c.client}) — ${c.calls_done}/${c.calls_target} calls, ${c.leads} leads`,
      });
    });
  return items.slice(0, 10);
}

const Dashboard: React.FC = () => {
  const { data, loading, error } = useDashboardData(30000); // live refresh every 30s

  // Hard error and no data at all → show a clear message (agar backend down ho).
  if (error && !data) {
    return (
      <Card className="p-8 text-center">
        <p className="text-red-400 font-medium">Dashboard data load nahi hua</p>
        <p className="text-gray-500 text-sm mt-2">{error}</p>
        <p className="text-gray-500 text-sm mt-1">Backend chal raha hai check karein (GET /api/admin/dashboard).</p>
      </Card>
    );
  }

  const kpis = data?.kpis;
  const charts = data?.charts;

  const chartData: ChartDataPoint[] = (charts?.calls_per_day.labels || []).map((day, i) => ({
    day,
    leads: charts?.calls_per_day.values[i] ?? 0,
    appointments: 0,
  }));

  const niche = charts?.leads_by_niche;
  const nicheMax = niche ? Math.max(1, ...niche.values) : 1;
  const activity = data ? buildActivity(data.agents, data.campaigns) : [];

  return (
    <div className="space-y-8">
      {/* Sample-data banner */}
      {data?.is_sample_data && (
        <div className="rounded-lg border border-yellow-700/40 bg-yellow-900/10 px-4 py-2 text-sm text-yellow-300">
          ⚠️ Sample data dikha raha hai — DB me abhi clients/leads nahi hain. Client onboard karte hi real data aa jayega.
        </div>
      )}

      {/* KPI grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <StatCard title="Total Clients" value={kpis?.total_clients ?? 0} loading={loading} />
        <StatCard title="Active Campaigns" value={kpis?.active_campaigns ?? 0} loading={loading} />
        <StatCard title="Calls Today" value={kpis?.calls_today ?? 0} loading={loading} />
        <StatCard title="Qualified Leads (Month)" value={kpis?.qualified_leads_month ?? 0} loading={loading} />
        <StatCard
          title="Revenue (Month)"
          value={kpis ? formatINR(kpis.revenue_month) : '—'}
          sub={kpis ? `Telephony cost ${formatINR(kpis.telephony_cost_month)}` : undefined}
          loading={loading}
        />
        <StatCard
          title="Net Margin"
          value={kpis ? `${kpis.net_margin_pct}%` : '—'}
          loading={loading}
        />
      </div>

      {/* System health */}
      {data && (
        <div className="flex flex-wrap gap-3">
          <HealthPill label="API" state={data.health.api} />
          <HealthPill label="Database" state={data.health.db} />
          <HealthPill label="Telephony" state={data.health.telephony} />
          <HealthPill label="Scrapers" state={data.health.scrapers} />
        </div>
      )}

      {/* Calls chart */}
      <div>
        <h3 className="text-xl font-semibold text-white mb-4">Calls — Last 7 Days</h3>
        <LeadsChart data={chartData} loading={loading} />
      </div>

      {/* Leads by niche + Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div>
          <h3 className="text-xl font-semibold text-white mb-4">Leads by Niche</h3>
          <Card className="p-6">
            {loading || !niche ? (
              <div className="space-y-3">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="h-5 bg-gray-700/50 rounded animate-pulse"></div>
                ))}
              </div>
            ) : (
              <ul className="space-y-3">
                {niche.labels.map((label, i) => (
                  <li key={label}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-gray-300">{label}</span>
                      <span className="text-gray-400">{niche.values[i]}</span>
                    </div>
                    <div className="h-2 rounded-full bg-gray-800">
                      <div
                        className="h-2 rounded-full bg-blue-500"
                        style={{ width: `${(niche.values[i] / nicheMax) * 100}%` }}
                      ></div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div>
          <h3 className="text-xl font-semibold text-white mb-4">Live Activity</h3>
          <Card className="p-6 max-h-[420px] overflow-y-auto content-scrollbar">
            {loading ? (
              <div className="space-y-4">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="flex items-center space-x-4 animate-pulse">
                    <div className="h-3 w-3 rounded-full bg-gray-700/50"></div>
                    <div className="h-4 bg-gray-700/50 rounded w-3/4"></div>
                  </div>
                ))}
              </div>
            ) : activity.length === 0 ? (
              <p className="text-sm text-gray-500">Abhi koi active agent/campaign nahi.</p>
            ) : (
              <ul className="space-y-4">
                {activity.map((a) => (
                  <li key={a.id} className="flex items-start space-x-3">
                    <span className={`mt-1.5 h-2.5 w-2.5 flex-shrink-0 rounded-full ${a.dot}`}></span>
                    <p className="text-sm text-gray-200">{a.text}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {data && (
        <p className="text-xs text-gray-600 text-right">
          Updated {new Date(data.generated_at).toLocaleString('en-IN')}
        </p>
      )}
    </div>
  );
};

export default Dashboard;
