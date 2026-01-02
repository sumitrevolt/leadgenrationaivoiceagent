
import React from 'react';
import { PlatformStats, ActivityLog, ActivityType, ChartDataPoint } from '../types.ts';
import Card from './ui/Card.tsx';
import { ActivitySuccessIcon, ActivityInfoIcon, ActivityWarningIcon, ActivityErrorIcon } from './ui/icons.tsx';
import LeadsChart from './charts/LeadsChart.tsx';

interface DashboardProps {
  stats: PlatformStats;
  activities: ActivityLog[];
  chartData: ChartDataPoint[];
  loading: boolean;
}

const StatCard: React.FC<{ title: string; value: string | number; loading: boolean }> = ({ title, value, loading }) => (
  <Card className="p-6">
    <h3 className="text-sm font-medium text-gray-400">{title}</h3>
    {loading ? (
      <div className="h-10 w-24 bg-gray-700/50 rounded-md animate-pulse mt-2"></div>
    ) : (
      <p className="mt-2 text-3xl font-bold text-white">{value.toLocaleString()}</p>
    )}
  </Card>
);

const ActivityIcon: React.FC<{type: ActivityType}> = ({ type }) => {
    switch (type) {
        case 'success': return <ActivitySuccessIcon />;
        case 'info': return <ActivityInfoIcon />;
        case 'warning': return <ActivityWarningIcon />;
        case 'error': return <ActivityErrorIcon />;
        default: return <ActivityInfoIcon />;
    }
};

const Dashboard: React.FC<DashboardProps> = ({ stats, activities, chartData, loading }) => {
  const timeAgo = (date: Date) => {
    const seconds = Math.floor((new Date().getTime() - date.getTime()) / 1000);
    if (seconds < 5) return "just now";
    let interval = seconds / 31536000;
    if (interval > 1) return Math.floor(interval) + " years ago";
    interval = seconds / 2592000;
    if (interval > 1) return Math.floor(interval) + " months ago";
    interval = seconds / 86400;
    if (interval > 1) return Math.floor(interval) + " days ago";
    interval = seconds / 3600;
    if (interval > 1) return Math.floor(interval) + " hours ago";
    interval = seconds / 60;
    if (interval > 1) return Math.floor(interval) + " minutes ago";
    return Math.floor(seconds) + " seconds ago";
  };

  return (
    <div className="space-y-8">
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard title="Total Clients" value={stats.totalClients} loading={loading} />
        <StatCard title="Active Campaigns" value={stats.activeCampaigns} loading={loading} />
        <StatCard title="Leads Generated (Today)" value={stats.leadsToday} loading={loading} />
        <StatCard title="Appointments Booked (Today)" value={stats.appointmentsToday} loading={loading} />
      </div>

      {/* Performance Chart */}
      <div>
        <h3 className="text-xl font-semibold text-white mb-4">Weekly Performance</h3>
        <LeadsChart data={chartData} loading={loading} />
      </div>

      {/* Real-time Activity Feed */}
      <div>
        <h3 className="text-xl font-semibold text-white mb-4">Real-time Activity Feed</h3>
        <Card className="p-6 max-h-[500px] overflow-y-auto content-scrollbar">
          {loading ? (
            <div className="space-y-4">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="flex items-center space-x-4 animate-pulse">
                  <div className="h-8 w-8 rounded-full bg-gray-700/50"></div>
                  <div className="flex-1 space-y-2">
                    <div className="h-4 bg-gray-700/50 rounded w-3/4"></div>
                    <div className="h-3 bg-gray-700/50 rounded w-1/4"></div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <ul className="space-y-6">
              {activities.map((activity) => (
                <li key={activity.id} className="flex space-x-4">
                  <ActivityIcon type={activity.type} />
                  <div className="flex-1">
                    <p className="text-sm text-gray-200">{activity.message}</p>
                    <p className="text-xs text-gray-500 mt-1">{timeAgo(activity.timestamp)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
};

export default Dashboard;
