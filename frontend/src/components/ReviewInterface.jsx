import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import './ReviewInterface.css';

const EXAMPLE_DIFF = `diff --git a/src/server.ts b/src/server.ts
index abc123..def456 100644
--- a/src/server.ts
+++ b/src/server.ts
@@ -10,6 +10,7 @@ const app = express();
 app.use(express.json());
+app.use(helmet());
 app.use(cors());

 app.get("/health", (_req, res) => {`;

export default function ReviewInterface({ review, onSubmitDiff, onSubmitPr, isLoading }) {
  const [inputMode, setInputMode] = useState('pr');   // 'pr' or 'diff'
  const [prUrl, setPrUrl] = useState('');
  const [diffText, setDiffText] = useState('');
  const [repo, setRepo] = useState('');
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  useEffect(() => { scrollToBottom(); }, [review]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (isLoading) return;
    if (inputMode === 'pr' && prUrl.trim()) {
      onSubmitPr(prUrl.trim());
      setPrUrl('');
    } else if (inputMode === 'diff' && diffText.trim()) {
      onSubmitDiff(diffText, repo);
    }
  };

  // Empty state — show input form
  if (!review) {
    return (
      <div className="review-interface">
        <div className="empty-state">
          <h2>Review Council</h2>
          <p>Submit a pull request or paste a diff for council review</p>

          <div className="input-tabs">
            <button
              className={`input-tab ${inputMode === 'pr' ? 'active' : ''}`}
              onClick={() => setInputMode('pr')}
            >
              GitHub PR
            </button>
            <button
              className={`input-tab ${inputMode === 'diff' ? 'active' : ''}`}
              onClick={() => setInputMode('diff')}
            >
              Paste Diff
            </button>
          </div>

          <form className="review-form" onSubmit={handleSubmit}>
            {inputMode === 'pr' ? (
              <>
                <input
                  className="pr-input"
                  type="text"
                  placeholder="https://github.com/scholete/pulse/pull/42  or  owner/repo#42"
                  value={prUrl}
                  onChange={(e) => setPrUrl(e.target.value)}
                  disabled={isLoading}
                />
                <button type="submit" className="submit-btn" disabled={!prUrl.trim() || isLoading}>
                  Review PR
                </button>
              </>
            ) : (
              <>
                <input
                  className="repo-input"
                  type="text"
                  placeholder="Repository name (e.g. pulse, stride)"
                  value={repo}
                  onChange={(e) => setRepo(e.target.value)}
                  disabled={isLoading}
                />
                <textarea
                  className="diff-input"
                  placeholder="Paste your unified diff here..."
                  value={diffText}
                  onChange={(e) => setDiffText(e.target.value)}
                  disabled={isLoading}
                  rows={12}
                />
                <button type="submit" className="submit-btn" disabled={!diffText.trim() || isLoading}>
                  {isLoading ? 'Reviewing...' : 'Submit for Review'}
                </button>
                {!diffText && (
                  <p className="example-hint" onClick={() => setDiffText(EXAMPLE_DIFF)}>
                    Need an example diff? Click here.
                  </p>
                )}
              </>
            )}
          </form>
        </div>
      </div>
    );
  }

  // In-progress or completed review
  const msg = review?.messages?.[review.messages.length - 1] || {};
  const pr = review.pr || {};

  return (
    <div className="review-interface">
      <div className="review-header">
        <div className="review-title">{review.title || 'Code Review'}</div>
        {(pr.repo || pr.pr_number) && (
          <div className="review-location">
            {pr.repo && <span className="repo-tag">{pr.repo}</span>}
            {pr.pr_number && <span className="pr-number">#{pr.pr_number}</span>}
            {pr.title && <span className="pr-label">— {pr.title}</span>}
          </div>
        )}
        <span className={`status-badge status-${review.status}`}>{review.status}</span>
      </div>

      <div className="messages-container">
        {/* Previous messages (if any) */}
        {review.messages?.slice(0, -1).map((m, i) => (
          <div key={i} className="message-group">{renderMessage(m)}</div>
        ))}

        {/* Current review */}
        {renderMessage(msg)}

        {isLoading && (
          <div className="loading-indicator">
            <div className="spinner"></div>
            <span>Council reviewing...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>
    </div>
  );

  function renderMessage(msg) {
    if (msg.role === 'user') {
      return (
        <div className="user-message">
          <div className="message-label">You</div>
          <div className="message-content markdown-content">
            <ReactMarkdown>{msg.content}</ReactMarkdown>
          </div>
        </div>
      );
    }

    return (
      <div className="assistant-message">
        <div className="message-label">Review Council</div>

        {msg.loading?.stage1 && (
          <div className="stage-loading">
            <div className="spinner"></div>
            <span>Stage 1: Collecting individual reviews...</span>
          </div>
        )}
        {msg.stage1 && <Stage1 reviews={msg.stage1} />}

        {msg.loading?.stage2 && (
          <div className="stage-loading">
            <div className="spinner"></div>
            <span>Stage 2: Meta-review (evaluating reviews)...</span>
          </div>
        )}
        {msg.stage2 && (
          <Stage2
            rankings={msg.stage2}
            labelToModel={msg.metadata?.label_to_model}
            aggregateRankings={msg.metadata?.aggregate_rankings}
          />
        )}

        {msg.loading?.stage3 && (
          <div className="stage-loading">
            <div className="spinner"></div>
            <span>Stage 3: Final synthesis...</span>
          </div>
        )}
        {msg.stage3 && <Stage3 finalResponse={msg.stage3} repo={pr.repo} prNumber={pr.pr_number} />}
      </div>
    );
  }
}
