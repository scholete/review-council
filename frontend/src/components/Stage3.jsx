import ReactMarkdown from 'react-markdown';
import './Stage3.css';

function extractVerdict(text) {
  if (!text) return null;
  const lower = text.toLowerCase();
  if (lower.includes('✅ approve')) return { icon: '✅', label: 'Approved' };
  if (lower.includes('⚠️ changes requested')) return { icon: '⚠️', label: 'Changes Requested' };
  if (lower.includes('❌ deny')) return { icon: '❌', label: 'Denied' };
  return null;
}

export default function Stage3({ finalResponse, repo, prNumber }) {
  if (!finalResponse) return null;

  const verdict = extractVerdict(finalResponse.response);

  return (
    <div className="stage stage3">
      <h3 className="stage-title">Stage 3: Final Council Review</h3>

      <div className="final-response">
        <div className="council-header">
          <div className="chairman-label">
            Chairman: {finalResponse.provider}/{finalResponse.model}
          </div>
          {verdict && (
            <div className={`verdict-badge verdict-${verdict.label.toLowerCase().replace(' ', '-')}`}>
              {verdict.icon} {verdict.label}
            </div>
          )}
        </div>

        <div className="final-text markdown-content">
          <ReactMarkdown>{finalResponse.response}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
