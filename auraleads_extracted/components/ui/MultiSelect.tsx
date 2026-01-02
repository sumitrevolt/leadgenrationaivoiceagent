
import React, { useState, useRef, useEffect } from 'react';
import { CloseIcon } from './icons.tsx';

interface MultiSelectProps {
  options: string[];
  selected: string[];
  onChange: (selected: string[]) => void;
}

const MultiSelect: React.FC<MultiSelectProps> = ({ options, selected, onChange }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [wrapperRef]);

  const toggleOption = (option: string) => {
    if (selected.includes(option)) {
      onChange(selected.filter(item => item !== option));
    } else {
      onChange([...selected, option]);
    }
  };

  const filteredOptions = options.filter(option => 
    option.toLowerCase().includes(searchTerm.toLowerCase()) && !selected.includes(option)
  );

  return (
    <div className="relative" ref={wrapperRef}>
      <div className="w-full bg-[#0a0a0a] border border-gray-700 rounded-md p-2 flex flex-wrap gap-2 items-center" onClick={() => setIsOpen(true)}>
        {selected.map(option => (
          <span key={option} className="flex items-center gap-1.5 bg-blue-600/30 text-blue-300 text-xs font-medium px-2 py-1 rounded-md">
            {option}
            <button
              onClick={(e) => {
                e.stopPropagation();
                toggleOption(option);
              }}
              className="text-blue-300 hover:text-white"
            >
              <CloseIcon className="h-3 w-3" />
            </button>
          </span>
        ))}
        <span className="text-gray-500 text-sm flex-1 min-w-[100px]">
          {selected.length === 0 ? 'Select industries...' : ''}
        </span>
      </div>
      {isOpen && (
        <div className="absolute z-10 mt-1 w-full bg-[#101010] border border-gray-700 rounded-md shadow-lg max-h-60 overflow-y-auto content-scrollbar">
          <div className="p-2">
            <input
              type="text"
              placeholder="Search..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-gray-600 rounded-md px-3 py-2 text-gray-200 focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <ul className="py-1">
            {filteredOptions.map(option => (
              <li
                key={option}
                onClick={() => toggleOption(option)}
                className="px-3 py-2 text-sm text-gray-300 hover:bg-blue-600/20 cursor-pointer"
              >
                {option}
              </li>
            ))}
            {filteredOptions.length === 0 && searchTerm && (
                <li className="px-3 py-2 text-sm text-gray-500">No results found.</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
};

export default MultiSelect;
