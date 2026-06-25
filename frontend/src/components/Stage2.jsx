import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import './Stage2.css';

function deAnonymizeText(text, labelToModel) {
  if (!labelToModel) return text;
  let result = text;
  Object.entries(labelToModel).forEach(([label, reviewer]) => {
    result = result.replace(new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), `**${reviewer}**`);
  });
  return result;
}

export default function Stage2({ rankings, labelToModel, aggregateRankings }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!rankings || rankings.length === 0) return null;

  return (
    <div className="stage stage2">
      <h3 className="stage-title">Stage 2: Meta-Review (Peer Evaluation)</h3>

      <h4>Raw Evaluations</h4>
      <p className="stage-description">
        Each reviewer evaluated all other reviews (anonymised as Response A, B, C, etc.)
        and ranked them by thoroughness and insight.
        Reviewer names are shown in <strong>bold</strong> for readability.
      </p>

      <div className="tabs">
        {rankings.map((r, i) => (
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
        <div className="ranking-reviewer">{rankings[activeTab].provider}/{rankings[activeTab].model}</div>
        <div className="ranking-content markdown-content">
          <ReactMarkdown>
            {deAnonymizeText(rankings[activeTab].ranking, labelToModel)}
          </ReactMarkdown>
        </div>

        {rankings[activeTab].parsed_ranking?.length > 0 && (
          <div className="parsed-ranking">
            <strong>Extracted Ranking:</strong>
            <ol>
              {rankings[activeTab].parsed_ranking.map((label, i) => (
                <li key={i}>
                  {labelToModel?.[label] || label}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {aggregateRankings?.length > 0 && (
        <div className="aggregate-rankings">
          <h4>Aggregate Rankings (Street Cred)</h4>
          <p className="stage-description">
            Combined results across all peer evaluations (lower score is better):
          </p>
          <div className="aggregate-list">
            {aggregateRankings.map((agg, i) => (
              <div key={i} className="aggregate-item">
                <span className="rank-position">#{i + 1}</span>
                <span className="rank-reviewer">{agg.reviewer}</span>
                <span className="rank-score">Avg: {agg.average_rank.toFixed(2)}</span>
                <span className="rank-count">({agg.rankings_count} votes)</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
