import React, { useState } from 'react';

// Types
interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone?: string;
  job_title?: string;
  role: string;
  status: string;
  profile_picture_url?: string;
  profile_picture_thumbnail_url?: string;
  is_verified: boolean;
  is_2fa_enabled: boolean;
  client_id?: string;
  created_at: string;
  last_login?: string;
}

interface AdminStats {
  total_users: number;
  active_users: number;
  total_clients: number;
  active_clients: number;
  total_leads: number;
  total_calls: number;
  total_appointments: number;
  total_revenue_inr: number;
  active_campaigns: number;
  system_health: string;
}

interface SystemHealth {
  overall: string;
  database: string;
  redis: string;
  vertex_ai: string;
  telephony: string;
  storage: string;
  last_checked: string;
}

interface AuditLog {
  id: string;
  user_id?: string;
  user_email?: string;
  action: string;
  resource_type?: string;
  resource_id?: string;
  ip_address?: string;
  created_at: string;
  severity: string;
}

// Mock data for development
const mockUsers: User[] = [
  {
    id: '1',
    email: 'admin@auraleads.ai',
    first_name: 'Super',
    last_name: 'Admin',
    full_name: 'Super Admin',
    job_title: 'Platform Administrator',
    role: 'super_admin',
    status: 'active',
    is_verified: true,
    is_2fa_enabled: true,
    created_at: '2024-01-01T00:00:00Z',
    last_login: '2026-01-03T10:00:00Z',
    profile_picture_url: 'https://ui-avatars.com/api/?name=Super+Admin&size=200&background=3b82f6&color=fff'
  },
  {
    id: '2',
    email: 'manager@client1.com',
    first_name: 'Priya',
    last_name: 'Sharma',
    full_name: 'Priya Sharma',
    phone: '+91 98765 43210',
    job_title: 'Sales Manager',
    role: 'manager',
    status: 'active',
    is_verified: true,
    is_2fa_enabled: false,
    client_id: 'client1',
    created_at: '2024-06-15T00:00:00Z',
    last_login: '2026-01-02T15:30:00Z',
    profile_picture_url: 'https://ui-avatars.com/api/?name=Priya+Sharma&size=200&background=10b981&color=fff'
  },
  {
    id: '3',
    email: 'agent@client1.com',
    first_name: 'Rahul',
    last_name: 'Verma',
    full_name: 'Rahul Verma',
    phone: '+91 87654 32109',
    job_title: 'Voice Agent',
    role: 'agent',
    status: 'active',
    is_verified: true,
    is_2fa_enabled: false,
    client_id: 'client1',
    created_at: '2024-08-20T00:00:00Z',
    last_login: '2026-01-03T09:00:00Z',
    profile_picture_url: 'https://ui-avatars.com/api/?name=Rahul+Verma&size=200&background=f59e0b&color=fff'
  }
];

const mockStats: AdminStats = {
  total_users: 156,
  active_users: 142,
  total_clients: 48,
  active_clients: 45,
  total_leads: 25847,
  total_calls: 52341,
  total_appointments: 2847,
  total_revenue_inr: 1584500,
  active_campaigns: 67,
  system_health: 'healthy'
};

const mockHealth: SystemHealth = {
  overall: 'healthy',
  database: 'healthy',
  redis: 'healthy',
  vertex_ai: 'healthy',
  telephony: 'healthy',
  storage: 'healthy',
  last_checked: new Date().toISOString()
};

const mockAuditLogs: AuditLog[] = [
  { id: '1', user_email: 'admin@auraleads.ai', action: 'user.create', resource_type: 'user', created_at: '2026-01-03T10:30:00Z', severity: 'info' },
  { id: '2', user_email: 'manager@client1.com', action: 'campaign.start', resource_type: 'campaign', created_at: '2026-01-03T10:15:00Z', severity: 'info' },
  { id: '3', user_email: 'admin@auraleads.ai', action: 'user.role.update', resource_type: 'user', created_at: '2026-01-03T09:45:00Z', severity: 'warning' },
  { id: '4', user_email: 'agent@client1.com', action: 'login.success', resource_type: 'user', created_at: '2026-01-03T09:00:00Z', severity: 'info' },
];

// Status badge component
const StatusBadge: React.FC<{ status: string; type?: 'status' | 'role' | 'health' }> = ({ status, type = 'status' }) => {
  const getColors = () => {
    if (type === 'health') {
      switch (status) {
        case 'healthy': return 'bg-green-500/20 text-green-400 border-green-500/30';
        case 'degraded': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
        case 'critical': return 'bg-red-500/20 text-red-400 border-red-500/30';
        default: return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
      }
    }
    if (type === 'role') {
      switch (status) {
        case 'super_admin': return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
        case 'admin': return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
        case 'manager': return 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30';
        case 'agent': return 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30';
        default: return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
      }
    }
    switch (status) {
      case 'active': return 'bg-green-500/20 text-green-400 border-green-500/30';
      case 'pending': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
      case 'suspended': return 'bg-red-500/20 text-red-400 border-red-500/30';
      case 'inactive': return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
      default: return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
    }
  };

  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full border ${getColors()}`}>
      {status.replace('_', ' ').toUpperCase()}
    </span>
  );
};

// User Avatar component
const UserAvatar: React.FC<{ user: User; size?: 'sm' | 'md' | 'lg' }> = ({ user, size = 'md' }) => {
  const sizeClasses = {
    sm: 'w-8 h-8 text-xs',
    md: 'w-10 h-10 text-sm',
    lg: 'w-16 h-16 text-lg'
  };

  if (user.profile_picture_url) {
    return (
      <img
        src={user.profile_picture_thumbnail_url || user.profile_picture_url}
        alt={user.full_name}
        className={`${sizeClasses[size]} rounded-full object-cover border-2 border-gray-700`}
      />
    );
  }

  const initials = `${user.first_name[0]}${user.last_name[0]}`.toUpperCase();
  return (
    <div className={`${sizeClasses[size]} rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center font-bold text-white border-2 border-gray-700`}>
      {initials}
    </div>
  );
};

// Stats Card component
const StatsCard: React.FC<{ title: string; value: string | number; subtitle?: string; icon: React.ReactNode; trend?: number }> = ({
  title, value, subtitle, icon, trend
}) => (
  <div className="bg-[#111111] border border-gray-800 rounded-xl p-6 hover:border-gray-700 transition-colors">
    <div className="flex items-center justify-between">
      <div>
        <p className="text-gray-400 text-sm font-medium">{title}</p>
        <p className="text-2xl font-bold text-white mt-1">{value}</p>
        {subtitle && <p className="text-gray-500 text-xs mt-1">{subtitle}</p>}
        {trend !== undefined && (
          <p className={`text-xs mt-2 ${trend >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {trend >= 0 ? '↑' : '↓'} {Math.abs(trend)}% from last month
          </p>
        )}
      </div>
      <div className="w-12 h-12 rounded-lg bg-blue-500/10 flex items-center justify-center text-blue-400">
        {icon}
      </div>
    </div>
  </div>
);

// Main Admin Panel Component
const AdminPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'overview' | 'users' | 'health' | 'audit'>('overview');
  const [users, setUsers] = useState<User[]>(mockUsers);
  const [stats] = useState<AdminStats>(mockStats);
  const [health] = useState<SystemHealth>(mockHealth);
  const [auditLogs] = useState<AuditLog[]>(mockAuditLogs);
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);

  // Create User Modal
  const CreateUserModal: React.FC<{ onClose: () => void }> = ({ onClose }) => {
    const [formData, setFormData] = useState({
      email: '',
      password: '',
      first_name: '',
      last_name: '',
      phone: '',
      job_title: '',
      role: 'viewer'
    });

    const handleSubmit = (e: React.FormEvent) => {
      e.preventDefault();
      // TODO: API call to create user
      const newUser: User = {
        id: Date.now().toString(),
        ...formData,
        full_name: `${formData.first_name} ${formData.last_name}`,
        status: 'pending',
        is_verified: false,
        is_2fa_enabled: false,
        created_at: new Date().toISOString(),
        profile_picture_url: `https://ui-avatars.com/api/?name=${formData.first_name}+${formData.last_name}&size=200&background=3b82f6&color=fff`
      };
      setUsers([...users, newUser]);
      onClose();
    };

    return (
      <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
        <div className="bg-[#111111] border border-gray-800 rounded-2xl w-full max-w-lg p-6">
          <h3 className="text-xl font-bold text-white mb-6">Create New User</h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <input
                type="text"
                placeholder="First Name"
                value={formData.first_name}
                onChange={(e) => setFormData({...formData, first_name: e.target.value})}
                className="bg-black border border-gray-800 rounded-lg px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
                required
              />
              <input
                type="text"
                placeholder="Last Name"
                value={formData.last_name}
                onChange={(e) => setFormData({...formData, last_name: e.target.value})}
                className="bg-black border border-gray-800 rounded-lg px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
                required
              />
            </div>
            <input
              type="email"
              placeholder="Email Address"
              value={formData.email}
              onChange={(e) => setFormData({...formData, email: e.target.value})}
              className="w-full bg-black border border-gray-800 rounded-lg px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
              required
            />
            <input
              type="password"
              placeholder="Password"
              value={formData.password}
              onChange={(e) => setFormData({...formData, password: e.target.value})}
              className="w-full bg-black border border-gray-800 rounded-lg px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
              required
              minLength={8}
            />
            <div className="grid grid-cols-2 gap-4">
              <input
                type="tel"
                placeholder="Phone Number"
                value={formData.phone}
                onChange={(e) => setFormData({...formData, phone: e.target.value})}
                className="bg-black border border-gray-800 rounded-lg px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
              />
              <input
                type="text"
                placeholder="Job Title"
                value={formData.job_title}
                onChange={(e) => setFormData({...formData, job_title: e.target.value})}
                className="bg-black border border-gray-800 rounded-lg px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
              />
            </div>
            <select
              value={formData.role}
              onChange={(e) => setFormData({...formData, role: e.target.value})}
              className="w-full bg-black border border-gray-800 rounded-lg px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
              aria-label="Select user role"
            >
              <option value="viewer">Viewer</option>
              <option value="agent">Agent</option>
              <option value="manager">Manager</option>
              <option value="admin">Admin</option>
            </select>
            <div className="flex gap-4 mt-6">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-4 py-2 border border-gray-700 text-gray-400 rounded-lg hover:bg-gray-800 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                Create User
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  };

  // User Detail Modal
  const UserDetailModal: React.FC<{ user: User; onClose: () => void }> = ({ user, onClose }) => {
    const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        // Upload to API
        const reader = new FileReader();
        reader.onload = (e) => {
          const updatedUser = { ...user, profile_picture_url: e.target?.result as string };
          setUsers(users.map(u => u.id === user.id ? updatedUser : u));
        };
        reader.readAsDataURL(file);
      }
    };

    return (
      <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
        <div className="bg-[#111111] border border-gray-800 rounded-2xl w-full max-w-2xl p-6">
          <div className="flex items-start justify-between mb-6">
            <div className="flex items-center gap-4">
              <div className="relative">
                <UserAvatar user={user} size="lg" />
                <label className="absolute -bottom-1 -right-1 w-6 h-6 bg-blue-600 rounded-full flex items-center justify-center cursor-pointer hover:bg-blue-700">
                  <input type="file" accept="image/*" onChange={handleImageUpload} className="hidden" aria-label="Upload profile picture" />
                  <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </label>
              </div>
              <div>
                <h3 className="text-xl font-bold text-white">{user.full_name}</h3>
                <p className="text-gray-400">{user.job_title || 'No title'}</p>
              </div>
            </div>
            <button onClick={onClose} className="text-gray-500 hover:text-white" aria-label="Close modal">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-4">
              <div>
                <label className="text-xs text-gray-500 uppercase">Email</label>
                <p className="text-white">{user.email}</p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase">Phone</label>
                <p className="text-white">{user.phone || 'Not provided'}</p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase">Role</label>
                <div className="mt-1"><StatusBadge status={user.role} type="role" /></div>
              </div>
            </div>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-gray-500 uppercase">Status</label>
                <div className="mt-1"><StatusBadge status={user.status} /></div>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase">Last Login</label>
                <p className="text-white">{user.last_login ? new Date(user.last_login).toLocaleString() : 'Never'}</p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase">2FA Enabled</label>
                <p className="text-white">{user.is_2fa_enabled ? '✅ Yes' : '❌ No'}</p>
              </div>
            </div>
          </div>

          <div className="flex gap-4 mt-8">
            <button className="flex-1 px-4 py-2 border border-yellow-600 text-yellow-400 rounded-lg hover:bg-yellow-600/10 transition-colors">
              Reset Password
            </button>
            <button className="flex-1 px-4 py-2 border border-red-600 text-red-400 rounded-lg hover:bg-red-600/10 transition-colors">
              Suspend User
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-black text-gray-300 p-6">
      {showCreateUser && <CreateUserModal onClose={() => setShowCreateUser(false)} />}
      {selectedUser && <UserDetailModal user={selectedUser} onClose={() => setSelectedUser(null)} />}

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">Admin Panel</h1>
        <p className="text-gray-500 mt-1">Manage users, monitor system health, and view audit logs</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-8 border-b border-gray-800 pb-4">
        {[
          { id: 'overview', label: 'Overview' },
          { id: 'users', label: 'User Management' },
          { id: 'health', label: 'System Health' },
          { id: 'audit', label: 'Audit Logs' }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-8">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <StatsCard
              title="Total Users"
              value={stats.total_users}
              subtitle={`${stats.active_users} active`}
              trend={12}
              icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>}
            />
            <StatsCard
              title="Active Clients"
              value={stats.active_clients}
              subtitle={`of ${stats.total_clients} total`}
              trend={8}
              icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>}
            />
            <StatsCard
              title="Total Leads"
              value={stats.total_leads.toLocaleString()}
              subtitle={`${stats.total_appointments.toLocaleString()} appointments`}
              trend={23}
              icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>}
            />
            <StatsCard
              title="Revenue (INR)"
              value={`₹${(stats.total_revenue_inr / 100000).toFixed(2)}L`}
              subtitle="This month"
              trend={15}
              icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* System Health Card */}
            <div className="bg-[#111111] border border-gray-800 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white">System Health</h3>
                <StatusBadge status={health.overall} type="health" />
              </div>
              <div className="space-y-3">
                {Object.entries(health).filter(([k]) => !['overall', 'last_checked'].includes(k)).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between">
                    <span className="text-gray-400 capitalize">{key.replace('_', ' ')}</span>
                    <StatusBadge status={value} type="health" />
                  </div>
                ))}
              </div>
            </div>

            {/* Recent Activity */}
            <div className="bg-[#111111] border border-gray-800 rounded-xl p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Recent Activity</h3>
              <div className="space-y-3">
                {auditLogs.slice(0, 4).map(log => (
                  <div key={log.id} className="flex items-center gap-3 text-sm">
                    <div className={`w-2 h-2 rounded-full ${log.severity === 'warning' ? 'bg-yellow-500' : 'bg-blue-500'}`} />
                    <span className="text-gray-400">{log.user_email}</span>
                    <span className="text-white">{log.action}</span>
                    <span className="text-gray-600 ml-auto">{new Date(log.created_at).toLocaleTimeString()}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Users Tab */}
      {activeTab === 'users' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div className="flex gap-4">
              <input
                type="search"
                placeholder="Search users..."
                className="bg-black border border-gray-800 rounded-lg px-4 py-2 text-white w-64 focus:border-blue-500 focus:outline-none"
              />
              <select className="bg-black border border-gray-800 rounded-lg px-4 py-2 text-white focus:border-blue-500 focus:outline-none" aria-label="Filter by role">
                <option value="">All Roles</option>
                <option value="admin">Admin</option>
                <option value="manager">Manager</option>
                <option value="agent">Agent</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>
            <button
              onClick={() => setShowCreateUser(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
              </svg>
              Add User
            </button>
          </div>

          <div className="bg-[#111111] border border-gray-800 rounded-xl overflow-hidden">
            <table className="w-full">
              <thead className="bg-black/50">
                <tr>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-400 uppercase">User</th>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-400 uppercase">Role</th>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-400 uppercase">Status</th>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-400 uppercase">Last Login</th>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-400 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {users.map(user => (
                  <tr key={user.id} className="hover:bg-gray-800/30 transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <UserAvatar user={user} size="sm" />
                        <div>
                          <p className="text-white font-medium">{user.full_name}</p>
                          <p className="text-gray-500 text-sm">{user.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4"><StatusBadge status={user.role} type="role" /></td>
                    <td className="px-6 py-4"><StatusBadge status={user.status} /></td>
                    <td className="px-6 py-4 text-gray-400 text-sm">
                      {user.last_login ? new Date(user.last_login).toLocaleDateString() : 'Never'}
                    </td>
                    <td className="px-6 py-4">
                      <button
                        onClick={() => setSelectedUser(user)}
                        className="text-blue-400 hover:text-blue-300 text-sm font-medium"
                      >
                        View Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Health Tab */}
      {activeTab === 'health' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {Object.entries(health).filter(([k]) => !['last_checked'].includes(k)).map(([key, value]) => (
            <div key={key} className="bg-[#111111] border border-gray-800 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white capitalize">{key.replace('_', ' ')}</h3>
                <StatusBadge status={value} type="health" />
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Response Time</span>
                  <span className="text-white">{Math.floor(Math.random() * 50) + 10}ms</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Uptime</span>
                  <span className="text-green-400">99.9%</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Last Check</span>
                  <span className="text-white">{new Date(health.last_checked).toLocaleTimeString()}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Audit Logs Tab */}
      {activeTab === 'audit' && (
        <div className="bg-[#111111] border border-gray-800 rounded-xl overflow-hidden">
          <div className="p-4 border-b border-gray-800 flex gap-4">
            <input
              type="search"
              placeholder="Search actions..."
              className="bg-black border border-gray-800 rounded-lg px-4 py-2 text-white w-64 focus:border-blue-500 focus:outline-none"
            />
            <select className="bg-black border border-gray-800 rounded-lg px-4 py-2 text-white focus:border-blue-500 focus:outline-none" aria-label="Filter by severity">
              <option value="">All Severities</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          <table className="w-full">
            <thead className="bg-black/50">
              <tr>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-400 uppercase">Time</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-400 uppercase">User</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-400 uppercase">Action</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-400 uppercase">Resource</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-400 uppercase">Severity</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {auditLogs.map(log => (
                <tr key={log.id} className="hover:bg-gray-800/30 transition-colors">
                  <td className="px-6 py-4 text-gray-400 text-sm">
                    {new Date(log.created_at).toLocaleString()}
                  </td>
                  <td className="px-6 py-4 text-white text-sm">{log.user_email || 'System'}</td>
                  <td className="px-6 py-4 text-white text-sm font-mono">{log.action}</td>
                  <td className="px-6 py-4 text-gray-400 text-sm">{log.resource_type || '-'}</td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 text-xs rounded ${
                      log.severity === 'warning' ? 'bg-yellow-500/20 text-yellow-400' :
                      log.severity === 'critical' ? 'bg-red-500/20 text-red-400' :
                      'bg-blue-500/20 text-blue-400'
                    }`}>
                      {log.severity}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default AdminPanel;
