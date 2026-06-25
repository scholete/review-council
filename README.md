# Review Council

![review-council](header.jpg)

An LLM-powered **code review council** for Scholete's repositories. Runs as a **GitHub Action** on every PR — no servers to maintain, no MacBook required. Multiple LLMs independently review every PR, evaluate each other's reviews, and a chairman synthesises a final verdict posted back as a PR comment + commit status.

## How It Works

```
PR opened / updated
    ↓  (GitHub Action trigger)
Stage 1: Two independent reviews (glm-5.2 + deepseek-v4-pro)
    ↓
Stage 2: Each model evaluates the other's review (anonymised meta-review)
    ↓
Stage 3: Chairman synthesises final consolidated review with verdict
    ↓
Result posted as PR comment + commit status check
```

### Stage 1: Individual Code Reviews
Each council model independently reviews the diff across: correctness, security, code quality, architecture, performance, and testing. Per-repo rules are injected into the prompt (Pulse vs Stride vs Stride-GPU each have different conventions).

### Stage 2: Meta-Review
Reviews are anonymised as "Response A", "Response B", etc. Each model evaluates the other reviews — which was more thorough? Caught more issues? Gave better recommendations?

### Stage 3: Final Synthesis
The Chairman (glm-5.2) produces a consolidated, actionable review with priority levels and a verdict: ✅ Approve | ⚠️ Changes Requested | ❌ Deny

## One-Time Setup

### 1. Add Secrets to Each Scholete Repo

For each repo you want the council to review (pulse, stride, stride-gpu, etc.):

1. Go to `Settings → Secrets and variables → Actions`
2. Add these **repository secrets** (not env vars):

| Secret | Value |
|--------|-------|
| `NEURALWATT_API_KEY` | Your NeuralWatt API key |
| `DEEPSEEK_API_KEY` | Your DeepSeek API key |

That's it. `GITHUB_TOKEN` is auto-generated — no setup needed.

### 2. Install the Workflow

Copy the workflow into each Scholete repo:

```bash
# For each repo:
cp .github/workflows/review-council.yml /path/to/repo/.github/workflows/
```

Or better — add this repo as a reusable workflow and reference it. (Happy to set that up.)

## What Happens on Every PR

- Trigger: `opened`, `synchronize` (new commit), `reopened`
- The Action runs `review.py` which:
  1. Fetches the PR diff via the GitHub API
  2. Runs all 3 stages against NeuralWatt + DeepSeek
  3. Posts a consolidated review comment on the PR
  4. Sets a commit status check (success/failure)
- Newer commits on the same PR cancel any in-progress review

## Repository-Specific Rules

The council knows about each Scholete repo's conventions:

- **Pulse** — Python/FastAPI, PHI data privacy, OCR pipelines
- **Stride** — Node.js/TypeScript, student data, gamification config
- **Stride-GPU** — Python/MLX, GPU memory management
- **Scholete Website** — React/TypeScript, SEO, analytics
- **AgenticWhales** — Python agent orchestration

Rules are in `backend/rules/__init__.py` and injected into Stage 1 prompts.

## Local Dev (Optional)

The frontend + FastAPI backend still work for interactive testing of prompts and debugging:

```bash
cp .env.example .env    # fill in NEURALWATT_API_KEY + DEEPSEEK_API_KEY
uv sync
cd frontend && npm install && cd ..
./start.sh
# Opens at http://localhost:5173
```

This is not needed for production — the Action handles everything.

## Providers

| Model | Provider | Role |
|-------|----------|------|
| `glm-5.2` | NeuralWatt | Council member + Chairman |
| `deepseek-v4-pro` | DeepSeek | Council member |

## Tech Stack

- **Runtime:** GitHub Actions (Ubuntu), reviewed by Python
- **Dependencies:** httpx, python-dotenv (everything else is stdlib)
- **Models:** NeuralWatt + DeepSeek APIs (OpenAI-compatible)
- **Repo:** monorepo for the council logic; workflow file gets copied to each Scholete repo
