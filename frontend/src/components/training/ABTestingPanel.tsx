
import React from 'react';
import { ABTest } from '../../types.ts';
import Card from '../ui/Card.tsx';

interface ABTestingPanelProps {
  test: ABTest;
}

const ScriptCard: React.FC<{ script: ABTest['scriptA'], title: string, isWinner: boolean }> = ({ script, title, isWinner }) => (
  <div className={`p-4 rounded-lg ${isWinner ? 'bg-green-500/10 border-green-500/50' : 'bg-gray-800/50 border-gray-700'} border`}>
    <div className="flex justify-between items-center">
      <h5 className="font-semibold text-white">{title}: "{script.name}"</h5>
      {isWinner && <span className="text-xs font-bold text-green-400 bg-green-500/20 px-2 py-1 rounded-full">WINNER</span>}
    </div>
    <p className="mt-2 text-sm text-gray-400 italic">"{script.content}"</p>
    <p className="mt-3 text-right text-lg font-bold text-white">{script.conversionRate.toFixed(2)}% <span className="text-sm font-normal text-gray-400">CVR</span></p>
  </div>
);

const ABTestingPanel: React.FC<ABTestingPanelProps> = ({ test }) => {
  const totalWidth = 500;
  const aWidth = test.scriptA.conversionRate / (test.scriptA.conversionRate + test.scriptB.conversionRate) * totalWidth;

  return (
    <Card className="p-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <ScriptCard script={test.scriptA} title="Script A" isWinner={test.winner === 'A'} />
        <ScriptCard script={test.scriptB} title="Script B" isWinner={test.winner === 'B'} />
      </div>
      <div className="mt-6">
        <p className="text-sm text-center text-gray-400 mb-2">Performance Split ({test.impressions.toLocaleString()} Impressions)</p>
        <div className="flex w-full h-4 rounded-full overflow-hidden bg-gray-700">
          <div className="bg-blue-500 transition-all duration-500" style={{ width: `${aWidth}px` }}></div>
          <div className="bg-teal-500"></div>
        </div>
      </div>
    </Card>
  );
};

export default ABTestingPanel;
