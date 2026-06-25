import './Sidebar.css';

function repoColor(repo) {
  const colors = {
    pulse: '#e74c3c',
    stride: '#3498db',
    'stride-gpu': '#9b59b6',
    'stride_gpu': '#9b59b6',
    'scholete-website': '#2ecc71',
    AgenticWhales: '#f39c12',
    agenticwhales: '#f39c12',
  };
  return colors[repo] || '#888';
}

export default function Sidebar({ reviews, currentReviewId, onSelectReview, onNewReview }) {
  // Group reviews by repo
  const grouped = {};
  for (const r of reviews) {
    const key = r.repo || 'other';
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(r);
  }

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-title-bar">
          <h1 className="sidebar-logo">Review Council</h1>
          <div className="sidebar-subtitle">Scholete</div>
        </div>
        <button className="new-review-btn" onClick={onNewReview}>
          + New Review
        </button>
      </div>

      <div className="review-list">
        {Object.keys(grouped).length === 0 ? (
          <div className="empty-reviews">No reviews yet</div>
        ) : (
          Object.entries(grouped).map(([repo, items]) => (
            <div key={repo} className="repo-group">
              <div className="repo-label" style={{ borderLeftColor: repoColor(repo) }}>
                {repo === 'other' ? 'Other' : repo}
              </div>
              {items.map((r) => (
                <div
                  key={r.id}
                  className={`review-item ${r.id === currentReviewId ? 'active' : ''}`}
                  onClick={() => onSelectReview(r.id)}
                >
                  <div className="review-item-title">{r.title}</div>
                  <div className="review-item-meta">
                    {r.pr_number && <span className="pr-badge">#{r.pr_number}</span>}
                    {r.pr_title && <span className="pr-title">{r.pr_title}</span>}
                    <span className={`status-badge status-${r.status}`}>{r.status}</span>
                  </div>
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
