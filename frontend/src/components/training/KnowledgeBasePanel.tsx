
import React from 'react';
import { KnowledgeBaseDocument } from '../../types.ts';
import Card from '../ui/Card.tsx';

interface KnowledgeBasePanelProps {
  documents: KnowledgeBaseDocument[];
}

const typeColors: Record<KnowledgeBaseDocument['type'], string> = {
  'Product Spec': 'bg-blue-600/20 text-blue-300',
  'Objection Handling': 'bg-yellow-600/20 text-yellow-300',
  'Competitor Analysis': 'bg-red-600/20 text-red-300',
};

const KnowledgeBasePanel: React.FC<KnowledgeBasePanelProps> = ({ documents }) => {
  return (
    <Card className="p-6 h-full">
      <ul className="space-y-3">
        {documents.map(doc => (
          <li key={doc.id} className="p-3 bg-gray-800/50 rounded-lg flex justify-between items-center">
            <div>
              <p className="font-medium text-sm text-white">{doc.name}</p>
              <p className="text-xs text-gray-500">Ingested: {doc.ingestedAt.toLocaleDateString()}</p>
            </div>
            <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${typeColors[doc.type]}`}>
              {doc.type}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
};

export default KnowledgeBasePanel;
