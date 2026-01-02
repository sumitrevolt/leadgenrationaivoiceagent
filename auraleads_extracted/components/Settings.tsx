
import React, { useState, useEffect } from 'react';
import { AutomationSettings, AgentAggressiveness } from '../types.ts';
import Card from './ui/Card.tsx';
import MultiSelect from './ui/MultiSelect.tsx';
import Slider from './ui/Slider.tsx';
import Toggle from './ui/Toggle.tsx';
import { getAIStrategySuggestion } from '../services/geminiService.ts';
import { LogoIcon } from './ui/icons.tsx';

interface SettingsProps {
  settings: AutomationSettings;
  onSettingsChange: (newSettings: AutomationSettings) => void;
}

const ALL_INDUSTRIES = ['Digital Agency', 'Solar', 'Real Estate', 'SaaS', 'E-commerce', 'Fintech', 'Healthcare', 'Construction', 'Manufacturing', 'Logistics', 'Hospitality'];

const Settings: React.FC<SettingsProps> = ({ settings, onSettingsChange }) => {
  const [localSettings, setLocalSettings] = useState<AutomationSettings>(settings);
  const [aiSuggestion, setAiSuggestion] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setLocalSettings(settings);
  }, [settings]);

  const handleSave = () => {
    onSettingsChange(localSettings);
    // Optional: Add a success notification
  };

  const handleGenerateSuggestion = async () => {
    setIsGenerating(true);
    setError('');
    setAiSuggestion('');
    try {
      const suggestion = await getAIStrategySuggestion(localSettings);
      setAiSuggestion(suggestion);
    } catch (err: any) {
      setError(err.message || 'Failed to get suggestion.');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleFieldChange = (field: keyof AutomationSettings, value: any) => {
    setLocalSettings(prev => ({ ...prev, [field]: value }));
  };

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <h3 className="text-2xl font-bold text-white">Automation Settings</h3>
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
          <Card>
            <div className="p-6">
              <h4 className="text-lg font-semibold text-white">Campaign Targeting</h4>
              <p className="text-sm text-gray-400 mt-1">Define the focus of your lead generation efforts.</p>
            </div>
            <div className="p-6 border-t border-gray-800 space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Target Industries</label>
                <MultiSelect
                  options={ALL_INDUSTRIES}
                  selected={localSettings.targetIndustries}
                  onChange={(selected) => handleFieldChange('targetIndustries', selected)}
                />
              </div>
            </div>
          </Card>

          <Card>
            <div className="p-6">
              <h4 className="text-lg font-semibold text-white">Performance Goals</h4>
              <p className="text-sm text-gray-400 mt-1">Set monthly targets for the automation platform.</p>
            </div>
            <div className="p-6 border-t border-gray-800 grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label htmlFor="leadsGoal" className="block text-sm font-medium text-gray-300 mb-2">Monthly Leads Goal</label>
                <input
                  type="number"
                  id="leadsGoal"
                  value={localSettings.monthlyLeadsGoal}
                  onChange={(e) => handleFieldChange('monthlyLeadsGoal', parseInt(e.target.value, 10))}
                  className="w-full bg-[#0a0a0a] border border-gray-700 rounded-md p-3 text-gray-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              <div>
                <label htmlFor="appointmentsGoal" className="block text-sm font-medium text-gray-300 mb-2">Monthly Appointments Goal</label>
                <input
                  type="number"
                  id="appointmentsGoal"
                  value={localSettings.monthlyAppointmentsGoal}
                  onChange={(e) => handleFieldChange('monthlyAppointmentsGoal', parseInt(e.target.value, 10))}
                  className="w-full bg-[#0a0a0a] border border-gray-700 rounded-md p-3 text-gray-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
            </div>
          </Card>

          <Card>
            <div className="p-6">
              <h4 className="text-lg font-semibold text-white">Agent Behavior</h4>
              <p className="text-sm text-gray-400 mt-1">Adjust how your AI voice agents operate.</p>
            </div>
            <div className="p-6 border-t border-gray-800 space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Call Aggressiveness</label>
                <Slider
                  value={localSettings.agentAggressiveness}
                  onChange={(value) => handleFieldChange('agentAggressiveness', value)}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300">Auto-Onboard Trial Clients</label>
                <p className="text-xs text-gray-500 mb-3">Automatically convert 'Interested' leads into 'Trial' clients.</p>
                <Toggle
                  enabled={localSettings.autoOnboardTrials}
                  onChange={(enabled) => handleFieldChange('autoOnboardTrials', enabled)}
                />
              </div>
            </div>
          </Card>
          
          <div className="flex justify-end">
            <button
              onClick={handleSave}
              className="px-6 py-2 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors duration-200 shadow-md"
            >
              Save Settings
            </button>
          </div>
        </div>

        <div className="lg:col-span-1">
          <div className="sticky top-8 space-y-6">
            <Card>
              <div className="p-6">
                <div className="flex items-center space-x-3">
                  <LogoIcon className="h-8 w-8 text-blue-400" />
                  <h4 className="text-lg font-semibold text-white">AI Strategy Assistant</h4>
                </div>
                <p className="text-sm text-gray-400 mt-2">Get intelligent suggestions to optimize your campaign based on your current settings.</p>
                <button
                  onClick={handleGenerateSuggestion}
                  disabled={isGenerating}
                  className="w-full mt-4 px-4 py-2 bg-blue-600/20 text-blue-300 font-semibold rounded-lg hover:bg-blue-600/40 transition-colors duration-200 disabled:opacity-50"
                >
                  {isGenerating ? 'Analyzing...' : '✨ Get Suggestions'}
                </button>
              </div>
            </Card>
            
            {(isGenerating || aiSuggestion || error) && (
              <Card className="p-6">
                {isGenerating && <div className="text-sm text-gray-400 animate-pulse">Generating suggestions...</div>}
                {error && <div className="text-sm text-red-400">{error}</div>}
                {aiSuggestion && (
                  <div className="prose prose-invert prose-sm max-w-none text-gray-300" dangerouslySetInnerHTML={{ __html: aiSuggestion.replace(/\n/g, '<br />') }} />
                )}
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;
