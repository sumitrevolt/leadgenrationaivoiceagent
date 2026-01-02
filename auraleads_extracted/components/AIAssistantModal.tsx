
import React, { useState, useEffect } from 'react';
import { CloseIcon, CopyIcon } from './ui/icons.tsx';
import { generateSaleScript } from '../services/geminiService.ts';

interface AIAssistantModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const MarkdownRenderer: React.FC<{ content: string }> = ({ content }) => {
  const createMarkup = (line: string) => {
    const bolded = line.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white">$1</strong>');
    return { __html: bolded };
  };

  const lines = content.split('\n').filter(line => line.trim() !== '');

  return (
    <div className="space-y-3">
      {lines.map((line, index) => {
        if (line.startsWith('#### ')) {
          return <h4 key={index} className="text-md font-semibold mt-2 text-gray-200" dangerouslySetInnerHTML={createMarkup(line.substring(5))} />;
        }
        if (line.startsWith('### ')) {
          return <h3 key={index} className="text-lg font-semibold mt-3 text-gray-100" dangerouslySetInnerHTML={createMarkup(line.substring(4))} />;
        }
        if (line.startsWith('## ')) {
          return <h2 key={index} className="text-xl font-semibold mt-4 text-white" dangerouslySetInnerHTML={createMarkup(line.substring(3))} />;
        }
        if (line.startsWith('# ')) {
          return <h1 key={index} className="text-2xl font-semibold mt-4 text-white" dangerouslySetInnerHTML={createMarkup(line.substring(2))} />;
        }

        if (line.trim().startsWith('* ') || line.trim().startsWith('- ')) {
          return (
            <div key={index} className="flex items-start">
              <span className="mr-3 mt-1 text-blue-400">•</span>
              <p className="flex-1" dangerouslySetInnerHTML={createMarkup(line.substring(line.indexOf(' ') + 1))} />
            </div>
          );
        }

        return <p key={index} dangerouslySetInnerHTML={createMarkup(line)} />;
      })}
    </div>
  );
};


const AIAssistantModal: React.FC<AIAssistantModalProps> = ({ isOpen, onClose }) => {
  const [productInfo, setProductInfo] = useState('An automated B2B lead generation platform that finds prospects and makes AI-powered calls to book appointments for our clients.');
  const [targetAudience, setTargetAudience] = useState('Digital marketing agencies, solar companies, and real estate agencies.');
  const [generatedScript, setGeneratedScript] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [isCopied, setIsCopied] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      // Reset state on close
      setGeneratedScript('');
      setError('');
      setIsLoading(false);
    }
  }, [isOpen]);

  const handleGenerate = async () => {
    if (!productInfo || !targetAudience) {
      setError('Please fill in both product information and target audience.');
      return;
    }
    setIsLoading(true);
    setError('');
    setGeneratedScript('');
    try {
      const script = await generateSaleScript(productInfo, targetAudience);
      setGeneratedScript(script);
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(generatedScript);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex justify-center items-center z-50 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="ai-assistant-title"
    >
      <div 
        className="bg-[#101010] border border-gray-800 rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="p-6 flex justify-between items-center border-b border-gray-800">
          <h2 id="ai-assistant-title" className="text-xl font-bold text-white">AI Script Assistant</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
            <CloseIcon className="h-6 w-6" />
          </button>
        </header>
        
        <div className="p-6 flex-1 overflow-y-auto content-scrollbar space-y-6">
          <div>
            <label htmlFor="productInfo" className="block text-sm font-medium text-gray-300 mb-2">
              Your Product/Service Description
            </label>
            <textarea
              id="productInfo"
              rows={3}
              className="w-full bg-[#0a0a0a] border border-gray-700 rounded-md p-3 text-gray-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
              value={productInfo}
              onChange={(e) => setProductInfo(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="targetAudience" className="block text-sm font-medium text-gray-300 mb-2">
              Target Audience
            </label>
            <input
              id="targetAudience"
              type="text"
              className="w-full bg-[#0a0a0a] border border-gray-700 rounded-md p-3 text-gray-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
              value={targetAudience}
              onChange={(e) => setTargetAudience(e.target.value)}
            />
          </div>
          
          {error && <p className="text-red-400 text-sm">{error}</p>}

          {isLoading && (
            <div className="text-center py-8">
              <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-current border-r-transparent align-[-0.125em] text-blue-500" role="status">
                <span className="!absolute !-m-px !h-px !w-px !overflow-hidden !whitespace-nowrap !border-0 !p-0 ![clip:rect(0,0,0,0)]">Loading...</span>
              </div>
              <p className="mt-4 text-gray-400">Generating your script... this may take a moment.</p>
            </div>
          )}

          {generatedScript && (
            <div>
              <div className="flex justify-between items-center mb-2">
                <h3 className="text-lg font-semibold text-white">Generated Script</h3>
                <button onClick={handleCopy} className="flex items-center text-sm text-gray-400 hover:text-white transition-colors">
                  <CopyIcon className="h-4 w-4 mr-1.5" />
                  {isCopied ? 'Copied!' : 'Copy'}
                </button>
              </div>
              <div className="prose prose-invert prose-sm max-w-none bg-[#0a0a0a] border border-gray-700 rounded-md p-4 text-gray-300">
                <MarkdownRenderer content={generatedScript} />
              </div>
            </div>
          )}
        </div>

        <footer className="p-6 border-t border-gray-800">
          <button
            onClick={handleGenerate}
            disabled={isLoading}
            className="w-full bg-blue-600 text-white font-semibold py-3 rounded-lg hover:bg-blue-700 transition-colors duration-200 disabled:bg-blue-800/50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Generating...' : '✨ Generate Script'}
          </button>
        </footer>
      </div>
    </div>
  );
};

export default AIAssistantModal;
