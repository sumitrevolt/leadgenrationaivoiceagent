
import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { DashboardIcon, MyCampaignIcon, ClientsIcon, VoiceAgentIcon, LogoIcon, SettingsIcon, ScriptIcon, TrainingIcon } from './components/ui/icons.tsx';
import Dashboard from './components/Dashboard.tsx';
import MyCampaign from './components/MyCampaign.tsx';
import Clients from './components/Clients.tsx';
import VoiceAgents from './components/VoiceAgents.tsx';
import Settings from './components/Settings.tsx';
import TrainingHub from './components/TrainingHub.tsx';
import AdminPanel from './components/AdminPanel.tsx';
import LoginPage from './components/LoginPage.tsx';
import AIAssistantModal from './components/AIAssistantModal.tsx';
import { useMockData } from './hooks/useMockData.ts';
import { AutomationSettings } from './types.ts';
import { getTokens, clearTokens, authApi } from './services/api.ts';

interface AuthUser {
  email: string;
  first_name: string;
  last_name?: string;
  role: string;
  profile_picture_url?: string;
}

// Admin icon
const AdminIcon = (props: React.SVGProps<SVGSVGElement>) => (
  <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
  </svg>
);

type View = 'dashboard' | 'voice-agents' | 'my-campaign' | 'clients' | 'settings' | 'training-hub' | 'admin';

export default function App() {
  const [currentView, setCurrentView] = useState<View>('dashboard');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  // Check authentication on mount
  useEffect(() => {
    const checkAuth = async () => {
      const { accessToken } = getTokens();
      if (accessToken) {
        try {
          const user = await authApi.getCurrentUser();
          setCurrentUser(user);
          setIsAuthenticated(true);
        } catch {
          clearTokens();
        }
      }
      setAuthLoading(false);
    };
    checkAuth();
  }, []);

  const handleLogin = (user: AuthUser) => {
    setCurrentUser(user);
    setIsAuthenticated(true);
  };

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch {
      // Ignore logout errors
    }
    clearTokens();
    setCurrentUser(null);
    setIsAuthenticated(false);
  };
  
  const [settings, setSettings] = useState<AutomationSettings>({
    targetIndustries: ['Digital Agency', 'SaaS', 'E-commerce'],
    monthlyLeadsGoal: 500,
    monthlyAppointmentsGoal: 25,
    agentAggressiveness: 'Balanced',
    autoOnboardTrials: true,
  });

  const { stats, activities, leads, clients, agents, callLogs, loading, chartData, trainingData } = useMockData(settings);

  const handleSettingsChange = useCallback((newSettings: AutomationSettings) => {
    setSettings(newSettings);
  }, []);

  const navigationItems = useMemo(() => {
    const items = [
      { id: 'dashboard', label: 'Dashboard', icon: DashboardIcon },
      { id: 'training-hub', label: 'Training Hub', icon: TrainingIcon },
      { id: 'voice-agents', label: 'Voice Agents', icon: VoiceAgentIcon },
      { id: 'my-campaign', label: 'My Campaign', icon: MyCampaignIcon },
      { id: 'clients', label: 'Clients', icon: ClientsIcon },
    ];
    // Only show admin panel for admins
    if (currentUser?.role === 'super_admin' || currentUser?.role === 'admin') {
      items.push({ id: 'admin', label: 'Admin Panel', icon: AdminIcon });
    }
    return items;
  }, [currentUser?.role]);

  const renderView = () => {
    switch (currentView) {
      case 'dashboard':
        return <Dashboard stats={stats} activities={activities} chartData={chartData} loading={loading} />;
      case 'training-hub':
        return <TrainingHub trainingData={trainingData} loading={loading} />;
      case 'voice-agents':
        return <VoiceAgents agents={agents} callLogs={callLogs} loading={loading} />;
      case 'my-campaign':
        return <MyCampaign leads={leads} onOpenScriptAssistant={() => setIsModalOpen(true)} loading={loading} />;
      case 'clients':
        return <Clients clients={clients} loading={loading} />;
      case 'settings':
        return <Settings settings={settings} onSettingsChange={handleSettingsChange} />;
      case 'admin':
        return <AdminPanel />;
      default:
        return <Dashboard stats={stats} activities={activities} chartData={chartData} loading={loading} />;
    }
  };

  // Show loading state
  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className="text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  // Show login page if not authenticated
  if (!isAuthenticated) {
    return <LoginPage onLoginSuccess={handleLogin} />;
  }

  return (
    <div className="flex h-screen bg-black text-gray-300">
      <AIAssistantModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} />
      
      <aside className="w-64 flex-shrink-0 bg-[#0a0a0a] border-r border-gray-800 flex flex-col">
        <div className="h-20 flex items-center px-6 border-b border-gray-800">
          <LogoIcon className="h-8 w-8 text-blue-500" />
          <h1 className="ml-3 text-xl font-bold text-white">AuraLeads AI</h1>
        </div>
        <nav className="flex-1 px-4 py-6 space-y-2 sidebar-scrollbar overflow-y-auto">
          {navigationItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setCurrentView(item.id as View)}
              className={`w-full flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors duration-200 ${
                currentView === item.id
                  ? 'bg-blue-600/20 text-blue-400'
                  : 'text-gray-400 hover:bg-gray-800/50 hover:text-gray-200'
              }`}
              aria-current={currentView === item.id ? 'page' : undefined}
            >
              <item.icon className="h-5 w-5 mr-3" />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="px-4 py-6 border-t border-gray-800 space-y-2">
           <button
              onClick={() => setIsModalOpen(true)}
              className="w-full flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors duration-200 text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"
            >
              <ScriptIcon className="h-5 w-5 mr-3" />
              <span>AI Script Assistant</span>
            </button>
            <button
              onClick={() => setCurrentView('settings')}
              className={`w-full flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors duration-200 ${
                currentView === 'settings'
                  ? 'bg-blue-600/20 text-blue-400'
                  : 'text-gray-400 hover:bg-gray-800/50 hover:text-gray-200'
              }`}
            >
              <SettingsIcon className="h-5 w-5 mr-3" />
              <span>Settings</span>
            </button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="h-20 flex-shrink-0 flex items-center justify-between px-8 border-b border-gray-800 bg-[#0a0a0a]">
          <h2 className="text-2xl font-bold text-white capitalize">{currentView.replace('-', ' ')}</h2>
          <div className="flex items-center space-x-4">
            {currentUser && (
              <div className="flex items-center space-x-3">
                {currentUser.profile_picture_url ? (
                  <img 
                    src={currentUser.profile_picture_url} 
                    alt={currentUser.first_name}
                    className="w-8 h-8 rounded-full object-cover"
                  />
                ) : (
                  <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white font-medium">
                    {currentUser.first_name?.[0]?.toUpperCase()}
                  </div>
                )}
                <span className="text-sm text-gray-300">{currentUser.first_name}</span>
                <button
                  onClick={handleLogout}
                  className="text-sm text-gray-400 hover:text-white transition-colors"
                >
                  Logout
                </button>
              </div>
            )}
            <div className="flex items-center space-x-2">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
              </span>
              <span className="text-sm font-medium text-green-400">Platform Active</span>
            </div>
          </div>
        </header>
        <div className="flex-1 overflow-y-auto content-scrollbar p-8">
          {renderView()}
        </div>
      </main>
    </div>
  );
}
