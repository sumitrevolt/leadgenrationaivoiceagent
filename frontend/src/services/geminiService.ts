/**
 * Gemini AI Service
 * 
 * SECURITY NOTE: AI API calls are proxied through the backend to keep API keys secure.
 * The frontend never directly accesses AI services - all requests go through /api/ai endpoints.
 */

import { CallStatus, AutomationSettings } from '../types.ts';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

// Helper to call the backend AI endpoint
const callBackendAI = async (endpoint: string, payload: object): Promise<string> => {
    const accessToken = localStorage.getItem('accessToken');
    
    try {
        const response = await fetch(`${API_BASE_URL}/ai${endpoint}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {}),
            },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'AI service error' }));
            throw new Error(error.detail || 'AI request failed');
        }

        const data = await response.json();
        return data.content || data.response || '';
    } catch (error) {
        console.error("Error calling AI service:", error);
        if (error instanceof Error) {
            throw new Error(`AI Service Error: ${error.message}`);
        }
        throw new Error("An unknown error occurred while communicating with the AI service.");
    }
};

export const generateSaleScript = async (productInfo: string, targetAudience: string): Promise<string> => {
  return callBackendAI('/generate-script', {
    product_info: productInfo,
    target_audience: targetAudience
  });
};

export const generateCallTranscript = async (agentName: string, companyName: string, industry: string, outcome: CallStatus): Promise<string> => {
    return callBackendAI('/generate-transcript', {
        agent_name: agentName,
        company_name: companyName,
        industry: industry,
        outcome: outcome
    });
};

export const getAIStrategySuggestion = async (settings: AutomationSettings): Promise<string> => {
    return callBackendAI('/strategy-suggestion', {
        target_industries: settings.targetIndustries,
        monthly_leads_goal: settings.monthlyLeadsGoal,
        monthly_appointments_goal: settings.monthlyAppointmentsGoal,
        agent_aggressiveness: settings.agentAggressiveness
    });
};

export const generateABTestVariant = async (originalScript: string, winning: boolean): Promise<string> => {
    return callBackendAI('/ab-test-variant', {
        original_script: originalScript,
        was_winning: winning
    });
};
