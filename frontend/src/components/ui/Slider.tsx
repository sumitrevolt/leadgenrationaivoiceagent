
import React from 'react';
import { AgentAggressiveness } from '../../types.ts';

interface SliderProps {
  value: AgentAggressiveness;
  onChange: (value: AgentAggressiveness) => void;
}

const options: AgentAggressiveness[] = ['Cautious', 'Balanced', 'Aggressive'];

const Slider: React.FC<SliderProps> = ({ value, onChange }) => {
  const selectedIndex = options.indexOf(value);

  return (
    <div className="w-full">
      <div className="relative h-2 bg-gray-700 rounded-full">
        <div 
          className="absolute top-0 left-0 h-2 bg-blue-600 rounded-full transition-all duration-300"
          style={{ width: `${(selectedIndex / (options.length - 1)) * 100}%` }}
        ></div>
        <div className="absolute w-full h-2 flex justify-between items-center">
          {options.map((opt, index) => (
            <div key={opt} className="relative">
              <button
                onClick={() => onChange(opt)}
                className={`h-4 w-4 rounded-full transition-all duration-300 ${
                  index <= selectedIndex ? 'bg-blue-500' : 'bg-gray-500'
                } border-2 border-[#101010] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-[#101010] focus:ring-blue-500`}
                aria-label={opt}
              ></button>
            </div>
          ))}
        </div>
      </div>
      <div className="flex justify-between mt-2 text-xs text-gray-400">
        {options.map(opt => (
          <span key={opt} className={`w-1/3 text-center ${value === opt ? 'font-bold text-white' : ''}`}>{opt}</span>
        ))}
      </div>
    </div>
  );
};

export default Slider;
