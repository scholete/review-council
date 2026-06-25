/**
 * API client for the Review Council backend.
 */

const API_BASE = 'http://localhost:8001';

export const api = {
  // ── Reviews ──────────────────────────────────────

  async listReviews() {
    const res = await fetch(`${API_BASE}/api/reviews`);
    if (!res.ok) throw new Error('Failed to list reviews');
    return res.json();
  },

  async getReview(id) {
    const res = await fetch(`${API_BASE}/api/reviews/${id}`);
    if (!res.ok) throw new Error('Failed to get review');
    return res.json();
  },

  async deleteReview(id) {
    const res = await fetch(`${API_BASE}/api/reviews/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete review');
    return res.json();
  },

  // ── Submit a raw diff ────────────────────────────

  async submitDiff(diffText, repo = '', prTitle = '', prDescription = '') {
    const res = await fetch(`${API_BASE}/api/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ diff_text: diffText, repo, pr_title: prTitle, pr_description: prDescription }),
    });
    if (!res.ok) throw new Error('Failed to submit diff');
    return res.json();
  },

  // ── Submit a GitHub PR ───────────────────────────

  async submitPr(prUrl) {
    const res = await fetch(`${API_BASE}/api/review/pr`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pr_url: prUrl }),
    });
    if (!res.ok) throw new Error('Failed to submit PR');
    return res.json();
  },

  // ── Streamed review ──────────────────────────────

  async submitDiffStream(diffText, repo = '', prTitle = '', prDescription = '', onEvent) {
    const res = await fetch(`${API_BASE}/api/review/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ diff_text: diffText, repo, pr_title: prTitle, pr_description: prDescription }),
    });
    if (!res.ok) throw new Error('Failed to submit diff');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data: ')) {
          try {
            const event = JSON.parse(line.slice(6));
            onEvent(event.type, event);
          } catch { /* skip parse errors */ }
        }
      }
    }
  },

  // ── List open PRs ────────────────────────────────

  async listOpenPrs() {
    const res = await fetch(`${API_BASE}/api/prs`);
    if (!res.ok) throw new Error('Failed to list PRs');
    return res.json();
  },
};
