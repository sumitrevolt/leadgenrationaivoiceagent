/**
 * API Service
 * Production-ready API client for AuraLeads backend
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

// Token management
let accessToken: string | null = null;
let refreshToken: string | null = null;

export const setTokens = (access: string, refresh: string) => {
  accessToken = access;
  refreshToken = refresh;
  localStorage.setItem('accessToken', access);
  localStorage.setItem('refreshToken', refresh);
};

export const getTokens = () => {
  if (!accessToken) {
    accessToken = localStorage.getItem('accessToken');
    refreshToken = localStorage.getItem('refreshToken');
  }
  return { accessToken, refreshToken };
};

export const clearTokens = () => {
  accessToken = null;
  refreshToken = null;
  localStorage.removeItem('accessToken');
  localStorage.removeItem('refreshToken');
};

// API request helper
async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const { accessToken } = getTokens();

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (accessToken) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${accessToken}`;
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    // Token expired, try refresh
    const newToken = await refreshAccessToken();
    if (newToken) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${newToken}`;
      const retryResponse = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...options,
        headers,
      });
      if (!retryResponse.ok) {
        throw new Error(`API Error: ${retryResponse.status}`);
      }
      return retryResponse.json();
    }
    clearTokens();
    window.location.href = '/login';
    throw new Error('Session expired');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `API Error: ${response.status}`);
  }

  return response.json();
}

async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken } = getTokens();
  if (!refreshToken) return null;

  try {
    const response = await fetch(`${API_BASE_URL}/admin/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) return null;

    const data = await response.json();
    setTokens(data.access_token, data.refresh_token);
    return data.access_token;
  } catch {
    return null;
  }
}

// ============================================================================
// Auth API
// ============================================================================

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface User {
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

export const authApi = {
  login: async (request: LoginRequest): Promise<LoginResponse> => {
    const response = await apiRequest<LoginResponse>('/admin/auth/login', {
      method: 'POST',
      body: JSON.stringify(request),
    });
    setTokens(response.access_token, response.refresh_token);
    return response;
  },

  logout: async (): Promise<void> => {
    try {
      await apiRequest('/admin/auth/logout', { method: 'POST' });
    } finally {
      clearTokens();
    }
  },

  getCurrentUser: async (): Promise<User> => {
    return apiRequest<User>('/admin/me');
  },
};

// ============================================================================
// Users API
// ============================================================================

export interface CreateUserRequest {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  phone?: string;
  job_title?: string;
  role?: string;
  client_id?: string;
}

export interface UpdateUserRequest {
  first_name?: string;
  last_name?: string;
  phone?: string;
  job_title?: string;
  department?: string;
  bio?: string;
  role?: string;
  status?: string;
}

export const usersApi = {
  list: async (params?: {
    skip?: number;
    limit?: number;
    role?: string;
    status?: string;
    search?: string;
  }): Promise<User[]> => {
    const searchParams = new URLSearchParams();
    if (params?.skip) searchParams.set('skip', params.skip.toString());
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    if (params?.role) searchParams.set('role', params.role);
    if (params?.status) searchParams.set('status', params.status);
    if (params?.search) searchParams.set('search', params.search);
    return apiRequest<User[]>(`/admin/users?${searchParams.toString()}`);
  },

  get: async (userId: string): Promise<User> => {
    return apiRequest<User>(`/admin/users/${userId}`);
  },

  create: async (request: CreateUserRequest): Promise<User> => {
    return apiRequest<User>('/admin/users', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  update: async (userId: string, request: UpdateUserRequest): Promise<User> => {
    return apiRequest<User>(`/admin/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(request),
    });
  },

  delete: async (userId: string): Promise<void> => {
    await apiRequest(`/admin/users/${userId}`, { method: 'DELETE' });
  },

  uploadProfilePicture: async (userId: string, file: File): Promise<{ profile_picture_url: string }> => {
    const formData = new FormData();
    formData.append('file', file);

    const { accessToken } = getTokens();
    const response = await fetch(`${API_BASE_URL}/admin/users/${userId}/picture`, {
      method: 'POST',
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
      body: formData,
    });

    if (!response.ok) throw new Error('Upload failed');
    return response.json();
  },

  deleteProfilePicture: async (userId: string): Promise<void> => {
    await apiRequest(`/admin/users/${userId}/picture`, { method: 'DELETE' });
  },
};

// ============================================================================
// Admin Stats API
// ============================================================================

export interface AdminStats {
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

export interface SystemHealth {
  overall: string;
  database: string;
  redis: string;
  vertex_ai: string;
  telephony: string;
  storage: string;
  last_checked: string;
}

export interface AuditLog {
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

export const adminApi = {
  getStats: async (): Promise<AdminStats> => {
    return apiRequest<AdminStats>('/admin/stats');
  },

  getHealth: async (): Promise<SystemHealth> => {
    return apiRequest<SystemHealth>('/admin/health');
  },

  getAuditLogs: async (params?: {
    skip?: number;
    limit?: number;
    action?: string;
    user_id?: string;
    resource_type?: string;
    severity?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<AuditLog[]> => {
    const searchParams = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value) searchParams.set(key, value.toString());
    });
    return apiRequest<AuditLog[]>(`/admin/audit-logs?${searchParams.toString()}`);
  },

  getSettings: async (): Promise<Record<string, unknown>> => {
    return apiRequest('/admin/settings');
  },
};

// ============================================================================
// Leads API
// ============================================================================

export interface Lead {
  id: string;
  business_name: string;
  contact_name: string;
  phone: string;
  email?: string;
  industry?: string;
  city?: string;
  status: string;
  temperature: string;
  source: string;
  created_at: string;
  last_contact?: string;
}

export const leadsApi = {
  list: async (params?: {
    skip?: number;
    limit?: number;
    status?: string;
    temperature?: string;
    search?: string;
  }): Promise<Lead[]> => {
    const searchParams = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value) searchParams.set(key, value.toString());
    });
    return apiRequest<Lead[]>(`/leads?${searchParams.toString()}`);
  },

  get: async (leadId: string): Promise<Lead> => {
    return apiRequest<Lead>(`/leads/${leadId}`);
  },

  create: async (data: Partial<Lead>): Promise<Lead> => {
    return apiRequest<Lead>('/leads', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  update: async (leadId: string, data: Partial<Lead>): Promise<Lead> => {
    return apiRequest<Lead>(`/leads/${leadId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  delete: async (leadId: string): Promise<void> => {
    await apiRequest(`/leads/${leadId}`, { method: 'DELETE' });
  },
};

// ============================================================================
// Campaigns API
// ============================================================================

export interface Campaign {
  id: string;
  name: string;
  status: string;
  type: string;
  target_industry?: string;
  target_cities: string[];
  total_leads: number;
  calls_made: number;
  appointments: number;
  start_date?: string;
  end_date?: string;
  created_at: string;
}

export const campaignsApi = {
  list: async (params?: {
    skip?: number;
    limit?: number;
    status?: string;
  }): Promise<Campaign[]> => {
    const searchParams = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value) searchParams.set(key, value.toString());
    });
    return apiRequest<Campaign[]>(`/campaigns?${searchParams.toString()}`);
  },

  get: async (campaignId: string): Promise<Campaign> => {
    return apiRequest<Campaign>(`/campaigns/${campaignId}`);
  },

  create: async (data: Partial<Campaign>): Promise<Campaign> => {
    return apiRequest<Campaign>('/campaigns', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  start: async (campaignId: string): Promise<Campaign> => {
    return apiRequest<Campaign>(`/campaigns/${campaignId}/start`, {
      method: 'POST',
    });
  },

  pause: async (campaignId: string): Promise<Campaign> => {
    return apiRequest<Campaign>(`/campaigns/${campaignId}/pause`, {
      method: 'POST',
    });
  },

  stop: async (campaignId: string): Promise<Campaign> => {
    return apiRequest<Campaign>(`/campaigns/${campaignId}/stop`, {
      method: 'POST',
    });
  },
};

// ============================================================================
// Platform API
// ============================================================================

export interface PlatformStats {
  total_tenants: number;
  active_tenants: number;
  trial_tenants: number;
  total_calls_made: number;
  total_leads_generated: number;
  is_running: boolean;
}

export const platformApi = {
  getStats: async (): Promise<PlatformStats> => {
    return apiRequest<PlatformStats>('/platform/stats');
  },

  start: async (): Promise<{ status: string; message: string }> => {
    return apiRequest('/platform/start', { method: 'POST' });
  },

  stop: async (): Promise<{ status: string; message: string }> => {
    return apiRequest('/platform/stop', { method: 'POST' });
  },
};

// ============================================================================
// Analytics API
// ============================================================================

export interface AnalyticsSummary {
  total_leads: number;
  total_calls: number;
  total_appointments: number;
  conversion_rate: number;
  avg_call_duration: number;
  calls_today: number;
  leads_today: number;
}

export const analyticsApi = {
  getSummary: async (period?: string): Promise<AnalyticsSummary> => {
    const params = period ? `?period=${period}` : '';
    return apiRequest<AnalyticsSummary>(`/analytics/summary${params}`);
  },

  getCallStats: async (startDate?: string, endDate?: string): Promise<Record<string, unknown>> => {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    return apiRequest(`/analytics/calls?${params.toString()}`);
  },

  getLeadStats: async (startDate?: string, endDate?: string): Promise<Record<string, unknown>> => {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    return apiRequest(`/analytics/leads?${params.toString()}`);
  },
};

// Export all APIs
export default {
  auth: authApi,
  users: usersApi,
  admin: adminApi,
  leads: leadsApi,
  campaigns: campaignsApi,
  platform: platformApi,
  analytics: analyticsApi,
};
