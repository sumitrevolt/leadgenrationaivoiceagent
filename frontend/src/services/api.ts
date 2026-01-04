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

// ============================================================================
// Billing API
// ============================================================================

export interface PricingPlan {
  id: string;
  name: string;
  pricing_model: string;
  monthly_price: number;
  calls_per_month: number | string;
  leads_per_month: number | string;
  concurrent_campaigns: number | string;
  features: string[];
  quarterly_discount: number;
  yearly_discount: number;
}

export interface Subscription {
  id: string;
  plan_id: string;
  plan_name: string;
  status: string;
  billing_cycle: string;
  base_price: number;
  currency: string;
  current_period_start?: string;
  current_period_end?: string;
  trial_ends_at?: string;
  usage: {
    calls_used: number;
    calls_limit: number | string;
    leads_generated: number;
    leads_limit: number | string;
    appointments_booked: number;
  };
  payment_gateway?: string;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  status: string;
  total: number;
  amount_paid: number;
  amount_due: number;
  currency: string;
  invoice_date: string;
  due_date?: string;
  pdf_url?: string;
  hosted_url?: string;
}

export interface CheckoutSession {
  checkout_url?: string;
  order_id?: string;
  session_id?: string;
  key_id?: string;
  amount: number;
  currency: string;
  gateway: string;
}

export interface UsageStats {
  calls_used: number;
  calls_limit: number | string;
  calls_remaining: number | string;
  leads_generated: number;
  leads_limit: number | string;
  leads_remaining: number | string;
  appointments_booked: number;
  period_start?: string;
  period_end?: string;
}

export interface PaymentMethod {
  id: string;
  payment_gateway: string;
  type: string;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
  card?: {
    brand?: string;
    last4?: string;
    exp_month?: number;
    exp_year?: number;
    funding?: string;
  };
  upi?: {
    id_masked?: string;
  };
  bank?: {
    name?: string;
  };
}

export const billingApi = {
  // Get all pricing plans
  getPlans: async (): Promise<PricingPlan[]> => {
    return apiRequest<PricingPlan[]>('/billing/plans');
  },

  // Get specific plan details
  getPlan: async (planId: string): Promise<PricingPlan> => {
    return apiRequest<PricingPlan>(`/billing/plans/${planId}`);
  },

  // Calculate plan pricing with discounts
  calculatePricing: async (planId: string, billingCycle: string = 'monthly'): Promise<{
    plan_id: string;
    billing_cycle: string;
    subtotal: number;
    discount: number;
    discount_percentage: number;
    taxable: number;
    tax: number;
    tax_rate: number;
    total: number;
    per_month: number;
    currency: string;
  }> => {
    return apiRequest(`/billing/plans/${planId}/pricing?billing_cycle=${billingCycle}`);
  },

  // Create checkout session
  createCheckout: async (
    clientId: string,
    planId: string,
    billingCycle: string = 'monthly',
    successUrl: string,
    cancelUrl: string,
    currency?: string
  ): Promise<CheckoutSession> => {
    return apiRequest<CheckoutSession>(`/billing/checkout?client_id=${clientId}`, {
      method: 'POST',
      body: JSON.stringify({
        plan_id: planId,
        billing_cycle: billingCycle,
        success_url: successUrl,
        cancel_url: cancelUrl,
        currency,
      }),
    });
  },

  // Verify Razorpay payment (called after frontend payment)
  verifyPayment: async (
    clientId: string,
    orderId: string,
    paymentId: string,
    signature: string
  ): Promise<{ success: boolean; payment_id: string; message: string }> => {
    return apiRequest(`/billing/verify-payment?client_id=${clientId}`, {
      method: 'POST',
      body: JSON.stringify({
        order_id: orderId,
        payment_id: paymentId,
        signature,
      }),
    });
  },

  // Get current subscription
  getSubscription: async (clientId: string): Promise<Subscription> => {
    return apiRequest<Subscription>(`/billing/subscription?client_id=${clientId}`);
  },

  // Cancel subscription
  cancelSubscription: async (
    clientId: string,
    reason?: string,
    cancelImmediately: boolean = false
  ): Promise<{ success: boolean; subscription_id: string; effective_until: string; message: string }> => {
    return apiRequest(`/billing/subscription/cancel?client_id=${clientId}`, {
      method: 'POST',
      body: JSON.stringify({
        reason,
        cancel_immediately: cancelImmediately,
      }),
    });
  },

  // Get invoices
  getInvoices: async (clientId: string, limit: number = 10, offset: number = 0): Promise<Invoice[]> => {
    return apiRequest<Invoice[]>(`/billing/invoices?client_id=${clientId}&limit=${limit}&offset=${offset}`);
  },

  // Get invoice details
  getInvoice: async (clientId: string, invoiceId: string): Promise<Invoice> => {
    return apiRequest<Invoice>(`/billing/invoices/${invoiceId}?client_id=${clientId}`);
  },

  // Get current usage
  getUsage: async (clientId: string): Promise<UsageStats> => {
    return apiRequest<UsageStats>(`/billing/usage?client_id=${clientId}`);
  },

  // Get usage history
  getUsageHistory: async (clientId: string, days: number = 30): Promise<Array<{
    id: string;
    usage_date: string;
    calls_made: number;
    calls_connected: number;
    qualified_leads: number;
    appointments_booked: number;
    billable_amount: number;
    billed: boolean;
  }>> => {
    return apiRequest(`/billing/usage/history?client_id=${clientId}&days=${days}`);
  },

  // Get saved payment methods
  getPaymentMethods: async (clientId: string): Promise<PaymentMethod[]> => {
    return apiRequest<PaymentMethod[]>(`/billing/payment-methods?client_id=${clientId}`);
  },

  // Get account balance (for per-lead model)
  getBalance: async (clientId: string): Promise<{ balance: number; currency: string }> => {
    return apiRequest(`/billing/balance?client_id=${clientId}`);
  },

  // Add balance
  addBalance: async (
    clientId: string,
    amount: number,
    successUrl: string,
    cancelUrl: string,
    currency: string = 'INR'
  ): Promise<CheckoutSession> => {
    return apiRequest(`/billing/balance/add?client_id=${clientId}&success_url=${encodeURIComponent(successUrl)}&cancel_url=${encodeURIComponent(cancelUrl)}`, {
      method: 'POST',
      body: JSON.stringify({ amount, currency }),
    });
  },

  // Upgrade subscription
  upgradeSubscription: async (clientId: string, newPlanId: string): Promise<{
    success: boolean;
    subscription_id: string;
    new_plan: string;
    message: string;
  }> => {
    return apiRequest(`/billing/subscription/upgrade?client_id=${clientId}&new_plan_id=${newPlanId}`, {
      method: 'POST',
    });
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
  billing: billingApi,
};
