
import React from 'react';
import { TrainingStatus } from '../../types.ts';
import Card from '../ui/Card.tsx';

interface PipelineVisualizerProps {
  status: TrainingStatus;
  lastTrained: Date;
}

const pipelineSteps: TrainingStatus[] = ['Ingesting Data', 'Processing Embeddings', 'Training Model', 'Deploying'];

const PipelineVisualizer: React.FC<PipelineVisualizerProps> = ({ status, lastTrained }) => {
  const currentStepIndex = pipelineSteps.indexOf(status);
  const isIdle = status === 'Idle';

  const timeAgo = (date: Date) => {
    const seconds = Math.floor((new Date().getTime() - date.getTime()) / 1000);
    if (seconds < 60) return "less than a minute ago";
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours} hour${hours > 1 ? 's' : ''} ago`;
  };

  return (
    <Card className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h4 className="text-lg font-semibold text-white">Live Pipeline Status</h4>
          <p className="text-sm text-gray-400">
            Status: <span className={`font-semibold ${isIdle ? 'text-green-400' : 'text-yellow-400'}`}>{status}</span>
          </p>
        </div>
        <div className="text-right">
            <p className="text-sm text-gray-400">Last Trained</p>
            <p className="font-semibold text-gray-200">{timeAgo(lastTrained)}</p>
        </div>
      </div>
      <div className="flex items-center space-x-2 md:space-x-4">
        {pipelineSteps.map((step, index) => (
          <React.Fragment key={step}>
            <div className={`flex-1 p-3 rounded-lg text-center transition-all duration-300 ${
              currentStepIndex === index ? 'bg-blue-600/30 border-blue-500' : 'bg-gray-800/50'
            } border border-transparent`}>
              <p className="text-xs sm:text-sm font-medium text-white">{step}</p>
            </div>
            {index < pipelineSteps.length - 1 && (
              <div className="text-gray-600">
                <svg className="w-4 h-4 sm:w-6 sm:h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
    </Card>
  );
};

export default PipelineVisualizer;
