# CLAUDE.md — Review Council

## Project Overview

Review Council is a 3-stage code review system where two AI models (neuralwatt/glm-5.2 and deepseek/deepseek-v4-pro) independently review code diffs, then evaluate each other's reviews, and a chairman synthesises the final answer. Supports both GitHub PRs and pasted diffs. All models are open — no closed provider dependencies.

## Architecture

### Backend Structure (`backend/`)

**`config.py`**
- `COUNCIL_MODELS` — list of `{"provider", "model"}` dicts
- `CHAIRMAN_MODEL` — model that synthesises final review
- `PROVIDER_CONFIGS` — per-provider API key + base URL
- `GITHUB_TOKEN`, `MONITORED_REPOS` — GitHub integration
- Environment variables: `NEURALWATT_API_KEY`, `DEEPSEEK_API_KEY`, `GITHUB_TOKEN`

**`llm_client.py`** (replaces old `openrouter.py`)
- `query_model(model_cfg, messages)` — Single async query via the right provider
- `query_models_parallel(model_cfgs, messages)` — Parallel queries via `asyncio.gather`
- Routes to provider-specific OpenAI-compatible endpoints
- Returns `{"content", "reasoning_details"}` or `None` on failure

**`council.py`** — The Core Logic
- `stage1_collect_reviews(diff_text, ...)` — Each model independently reviews the diff
  - Code-review-specific prompt covering: correctness, security, quality, architecture, performance, testing
  - Returns list of `{"model", "provider", "response"}`
- `stage2_collect_rankings(diff_text, stage1_results, ...)` — Anonymised meta-review
  - Anonymises as "Response A, B, ..."
  - Creates `label_to_model` mapping
  - Each model evaluates and ranks the reviews
  - Returns `(rankings_list, label_to_model_dict)`
- `stage3_synthesize_final(...)` — Chairman consolidates into final review with verdict
- `parse_ranking_from_text()` — Extracts FINAL RANKING: section
- `calculate_aggregate_rankings()` — Average rank across peer evaluations
- `run_full_review()` — Complete 3-stage pipeline
- `generate_review_title()` — Short title for review

**`diff_analyzer.py`** — Diff parsing
- `parse_diff(diff_text)` — Returns list of `DiffFile` objects with hunks
- `diff_summary(diff_text)` — Human-readable summary (e.g. "3 file(s), +42/-12 lines")

**`github_integration.py`** — GitHub API
- `parse_pr_url(url)` — Parse PR URL into `(owner, repo, number)`
- `fetch_pr_diff(owner, repo, number)` — Fetch diff + PR metadata
- `post_pr_review(owner, repo, number, body)` — Post review comment
- `set_commit_status(owner, repo, sha, state, description)` — Commit status checks
- `parse_webhook_payload(body, signature, secret)` — Webhook validation
- `extract_pr_info_from_webhook(payload)` — Extract PR from webhook event
- `list_open_prs()` — List open PRs across monitored repos

**`rules/__init__.py`** — Per-repo review guidelines
- `get_repo_rules(repo)` — Returns rules snippet for Pulse, Stride, Stride-GPU, etc.
- Injected into Stage 1 prompts to customise reviews per repo

**`storage.py`**
- JSON-based review storage in `data/reviews/`
- Each review: `{id, created_at, title, status, pr, diff_text, messages[]}`
- Methods: `create_review`, `get_review`, `list_reviews`, `delete_review`, `update_review`, `add_user_message`, `add_review_result`

**`main.py`**
- FastAPI app on **port 8001**
- CORS for localhost:5173 and localhost:3000
- Endpoints:
  - `GET /api/reviews` — list reviews
  - `GET /api/reviews/{id}` — get review detail
  - `DELETE /api/reviews/{id}` — delete review
  - `POST /api/review` — submit raw diff for review
  - `POST /api/review/pr` — submit GitHub PR for review
  - `POST /api/review/stream` — streamed review with SSE events
  - `POST /webhooks/github` — webhook receiver for auto-review
  - `GET /api/prs` — list open PRs from monitored repos

### Frontend Structure (`frontend/src/`)

**`App.jsx`**
- Manages reviews list and current review
- Handles diff submission (streaming) and PR submission (batch)

**`api.js`**
- `listReviews()`, `getReview()`, `deleteReview()`
- `submitDiff(diffText, repo, ...)` — batch diff submission
- `submitPr(prUrl)` — batch PR submission
- `submitDiffStream(..., onEvent)` — SSE streaming
- `listOpenPrs()` — open PRs from monitored repos

**Components:**
- `Sidebar.jsx` — Review list grouped by repo, repo-colour badges
- `ReviewInterface.jsx` — Main UI: PR URL input / diff paste + 3-stage display
- `Stage1.jsx` — Tab view of individual code reviews (per reviewer)
- `Stage2.jsx` — Tab view of meta-reviews with aggregate rankings
- `Stage3.jsx` — Final review with verdict badge (✅/⚠️/❌)

### Key Design Decisions

**Provider Architecture**
- Not using OpenRouter — direct provider calls to NeuralWatt + DeepSeek
- Each provider has its own API key and base URL
- Models run in parallel via separate HTTP clients
- Graceful degradation per model

**Stage 1 Prompt Focus**
Code review covers: correctness, security, quality, architecture, performance, testing
Each issue must include file path + line number
Ends with a verdict: Approve / Changes Requested / Deny

**Stage 2 Meta-Review**
Same anonymisation pattern as original LLM Council
Evaluates quality of the reviews, not answers to questions

**Per-Repo Rules**
Rules injected into Stage 1 prompt
Separate guidelines for: Pulse (Python/PHI), Stride (TS/student-data), Stride-GPU (MLX), etc.

**GitHub Integration**
- PR URL parsing accepts full URLs and shorthand
- Fetches diff via GitHub REST API
- Posts review comment + sets commit status
- Webhook auto-review on `opened`/`synchronize` events
- Only reviews monitored repos (configurable)

### Data Flow Summary
```
PR opened / updated
    ↓  (GitHub Action trigger: .github/workflows/review-council.yml)
review.py fetches diff via GH API
    ↓
Stage 1: Parallel review by glm-5.2 + deepseek-v4-pro
    ↓
Stage 2: Anonymised → Parallel meta-review → rankings
    ↓
Aggregate Rankings
    ↓
Stage 3: Chairman synthesis with verdict
    ↓
PR comment posted + commit status set (success/failure)
```

### Important Implementation Details

**Dual-Mode Architecture**
The council runs in two modes:

1. **GitHub Action (production)** — `review.py` is the entry point. Runs on every PR via `.github/workflows/review-council.yml`. No server, no frontend. Posts results as PR comments + commit status checks. Deps: `httpx`, `python-dotenv`. Secrets stored in GH repo settings.

2. **Local dev (optional)** — `backend/main.py` via FastAPI + React frontend. Used for prompt debugging, testing rules, local experiments. Run with `./start.sh`.

**`review.py`** — GitHub Action entry point (repo root)
- Reads env vars set by workflow: `PR_NUMBER`, `PR_TITLE`, `PR_BODY`, `REPO`, `SHA`, `GITHUB_TOKEN`, `NEURALWATT_API_KEY`, `DEEPSEEK_API_KEY`
- Inserts repo root into `sys.path` to import `backend.*` modules
- Falls back to `list_open_prs()` if no `PR_NUMBER` is provided
- Posts review to PR via `post_pr_review()`
- Sets commit status via `set_commit_status()`
- `_post_failure_comment()` — synchronous fallback using `httpx.Client()`

**`.github/workflows/review-council.yml`**
- Trigger: `pull_request: [opened, synchronize, reopened]`
- Concurrency group per PR — newer commits cancel in-progress reviews
- Timeout: 10 minutes
- Steps: checkout (fetch-depth: 0) → setup Python 3.10 → pip install httpx python-dotenv → run review.py
- Env vars passed from `github.event` context + repo secrets

**Relative Imports**
All backend modules use relative imports (`from .config import ...`). Run as `python -m backend.main`.

**Port Configuration**
- Backend: 8001
- Frontend: 5173

**Model Config Format**
```python
COUNCIL_MODELS = [
    {"provider": "neuralwatt", "model": "glm-5.2"},
    {"provider": "deepseek", "model": "deepseek-v4-pro"},
]
```

**Error Handling**
- Graceful degradation per model (returns None, continues)
- Never fail entire request due to single model failure
- Failed reviews get `status: "failed"` in storage
- 502 on GitHub fetch failure, 400 on bad PR URL

### Common Gotchas

1. **API Keys**: Must set `NEURALWATT_API_KEY` and `DEEPSEEK_API_KEY` as repo secrets in GitHub. Without them, the providers raise `ValueError` at query time.
2. **Action secrets, not env vars**: The workflow uses `${{ secrets.NEURALWATT_API_KEY }}` — these must be configured under Settings → Secrets and variables → Actions, not in .env.
3. **No .env in Action**: `python-dotenv` loads `.env` which doesn't exist in CI. That's fine — `load_dotenv()` is a no-op when the file is missing, and the Action sets env vars directly.
4. **Python 3.10+ required**: The Action uses `python-version: "3.10"`, but the code runs on 3.10–3.13.
5. **Module Import Errors**: Run `python review.py` or `python -m backend.main` from project root.
6. **Port Configuration**: Local dev only — backend: 8001, frontend: 5173.
7. **CORS**: Frontend origins must match `main.py` CORS middleware (local dev only).
8. **Data Directory**: `data/reviews/` is gitignored — auto-created on first use.
