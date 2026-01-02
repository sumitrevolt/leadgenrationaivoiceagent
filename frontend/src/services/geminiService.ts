
import { GoogleGenAI } from '@google/genai';
import { CallStatus, AutomationSettings } from '../types.ts';

// This function assumes that process.env.API_KEY is set in the environment.
// In a real-world browser environment, this would need to be handled securely,
// typically by making a request to a backend server that holds the key.
// For this self-contained example, we proceed assuming it's available.
const getApiKey = () => {
    try {
        return process.env.API_KEY;
    } catch (e) {
        console.error("API_KEY environment variable not found.");
        return undefined;
    }
};

const apiKey = getApiKey();
let ai: GoogleGenAI | null = null;
if (apiKey) {
    ai = new GoogleGenAI({ apiKey, vertexai: true });
} else {
    console.warn("Gemini API key not available. AI features will be disabled.");
}

const callGemini = async (model: string, systemInstruction: string, prompt: string): Promise<string> => {
    if (!ai) {
        throw new Error("AI Service is not initialized. Please check your API key.");
    }
    try {
        const response = await ai.models.generateContent({
            model,
            contents: { role: 'user', parts: [{ text: prompt }] },
            config: { systemInstruction, temperature: 0.8, topP: 0.95, topK: 40 }
        });
        return response.text;
    } catch (error) {
        console.error("Error generating content from Gemini API:", error);
        if (error instanceof Error) {
            throw new Error(`Gemini API Error: ${error.message}`);
        }
        throw new Error("An unknown error occurred while communicating with the Gemini API.");
    }
};

export const generateSaleScript = async (productInfo: string, targetAudience: string): Promise<string> => {
  const systemInstruction = `You are an expert B2B sales scriptwriter. Your task is to create a compelling, concise, and effective cold call script. The script should be structured into four parts:
1.  **Opener:** A brief, engaging introduction that builds rapport and states the call's purpose.
2.  **Pitch:** A clear and concise value proposition explaining the service and its key benefit for the target audience.
3.  **Objection Handling:** Briefly mention one common objection and a smart way to handle it.
4.  **Call to Action:** A clear next step, like booking a short demo or discovery call.

Generate the script based on the user's product description and target audience. Format the output in Markdown.`;

  const prompt = `
    **Product/Service Description:**
    ${productInfo}

    **Target Audience:**
    ${targetAudience}

    Please generate the sales script now.
  `;

  return callGemini('gemini-2.5-flash', systemInstruction, prompt);
};

export const generateCallTranscript = async (agentName: string, companyName: string, industry: string, outcome: CallStatus): Promise<string> => {
    const systemInstruction = `You are a call transcript generator. Your task is to create a realistic, brief call transcript between an AI sales agent and a human prospect. The transcript should reflect the provided call outcome.
- The AI agent's name is ${agentName}.
- The AI agent is calling from "AuraLeads AI".
- The prospect is from "${companyName}", a company in the ${industry} industry.
- The call should be concise.
- Format the transcript with speaker labels (e.g., "${agentName}:" and "Prospect:").`;

    const prompt = `
    Generate a call transcript with the following details:
    - **AI Agent:** ${agentName}
    - **Prospect Company:** ${companyName} (${industry})
    - **Call Outcome:** ${outcome}

    Create a plausible conversation that leads to this outcome. For example:
    - If 'Appointment Set', the prospect should agree to a meeting.
    - If 'Voicemail', the agent should leave a concise message.
    - If 'Completed', the prospect might be interested but needs to talk to a partner, or it's not a good fit.
    - If 'No Answer', the transcript should just say "[No Answer]".
    `;

    return callGemini('gemini-2.5-flash', systemInstruction, prompt);
};

export const getAIStrategySuggestion = async (settings: AutomationSettings): Promise<string> => {
    const systemInstruction = `You are a world-class B2B marketing strategist. Your task is to analyze a user's lead generation campaign settings and provide 2-3 actionable, concise suggestions for improvement. Focus on expanding their target market and optimizing their approach. Format the output in Markdown with clear headings for each suggestion.`;

    const prompt = `
    Here are the current campaign settings for an automated lead generation platform:

    - **Target Industries:** ${settings.targetIndustries.join(', ')}
    - **Monthly Leads Goal:** ${settings.monthlyLeadsGoal}
    - **Monthly Appointments Goal:** ${settings.monthlyAppointmentsGoal}
    - **Agent Call Aggressiveness:** ${settings.agentAggressiveness}

    Based on this, provide strategic suggestions. For example, if they are targeting 'Real Estate', suggest 'Property Management' or 'Mortgage Brokers' as related industries. If their goals are high and aggressiveness is low, suggest adjusting the agent behavior. Be creative and insightful.
    `;

    return callGemini('gemini-2.5-flash', systemInstruction, prompt);
};

export const generateABTestVariant = async (originalScript: string, winning: boolean): Promise<string> => {
    const systemInstruction = `You are an expert A/B testing copywriter for B2B sales. Your task is to create a new variant of a sales script opener.
- If the original script was the winner, create a new challenger that tries a completely different angle (e.g., question-based vs. statement-based, more direct vs. more consultative).
- If the original script was the loser, analyze its potential weakness and create an improved version that addresses it.
- The output should be ONLY the new script opener text, no extra explanations.`;

    const prompt = `
    The original script opener is:
    "${originalScript}"

    This script was the ${winning ? 'WINNER' : 'LOSER'} of the last A/B test.

    Generate a new, creative, and concise opener to test against it.
    `;

    return callGemini('gemini-2.5-flash', systemInstruction, prompt);
};
