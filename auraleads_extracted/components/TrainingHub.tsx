
import React from 'react';
import { TrainingData } from '../types.ts';
import Card from './ui/Card.tsx';
import PipelineVisualizer from './training/PipelineVisualizer.tsx';
import PerformanceChart from './training/PerformanceChart.tsx';
import ABTestingPanel from './training/ABTestingPanel.tsx';
import KnowledgeBasePanel from './training/KnowledgeBasePanel.tsx';

interface TrainingHubProps {
  trainingData: TrainingData | null;
  loading: boolean;
}

const TrainingHub: React.FC<TrainingHubProps> = ({ trainingData, loading }) => {
  if (loading || !trainingData) {
    return (
        <div className="space-y-8">
            <div className="h-10 bg-gray-800/50 rounded-md w-1/3 animate-pulse"></div>
            <div className="h-40 bg-gray-800/50 rounded-xl animate-pulse"></div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <div className="h-80 bg-gray-800/50 rounded-xl animate-pulse"></div>
                <div className="h-80 bg-gray-800/50 rounded-xl animate-pulse"></div>
            </div>
        </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h3 className="text-xl font-semibold text-white mb-4">ML Training Pipeline</h3>
        <PipelineVisualizer status={trainingData.status} lastTrained={trainingData.lastTrained} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
        <div className="lg:col-span-3">
            <h3 className="text-xl font-semibold text-white mb-4">Model Performance</h3>
            <PerformanceChart data={trainingData.performanceHistory} />
        </div>
        <div className="lg:col-span-2">
            <h3 className="text-xl font-semibold text-white mb-4">RAG Knowledge Base</h3>
            <KnowledgeBasePanel documents={trainingData.knowledgeBase} />
        </div>
      </div>

      <div>
        <h3 className="text-xl font-semibold text-white mb-4">Live A/B Script Testing</h3>
        <ABTestingPanel test={trainingData.activeABTest} />
      </div>
    </div>
  );
};

export default TrainingHub;
