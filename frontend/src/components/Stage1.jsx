import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import './Stage1.css';

export default function Stage1({ reviews }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!reviews || reviews.length === 0) return null;

  return (
    <div className="stage stage1">
      <h3 className="stage-title">Stage 1: Individual Reviews</h3>

      <div className="tabs">
        {reviews.map((r, i) => (
          <button
            key={i}
            className={`tab ${activeTab === i ? 'active' : ''}`}
            onClick={() => setActiveTab(i)}
          >
            {r.provider}/{r.model}
          </button>
        ))}
      </div>

      <div className="tab-content">
        <div className="reviewer-name">
          {reviews[activeTab].provider}/{reviews[activeTab].model}
        </div>
        <div className="response-text markdown-content">
          <ReactMarkdown>{reviews[activeTab].response}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
