"""Per-repo review guidelines for the Review Council.

Each module returns a string snippet that gets injected into the
Stage 1 review prompt to specialise the review for the repo's
language, framework, and conventions.
"""

from typing import Optional


def get_repo_rules(repo: str) -> Optional[str]:
    """Return the review-rules snippet for *repo*, or ``None``."""
    return {
        "pulse": _PULSE_RULES,
        "stride": _STRIDE_RULES,
        "stride-gpu": _STRIDE_GPU_RULES,
        "stride_gpu": _STRIDE_GPU_RULES,
        "scholete-website": _SCHOLETE_WEBSITE_RULES,
        "AgenticWhales": _AGENTIC_WHALES_RULES,
        "agenticwhales": _AGENTIC_WHALES_RULES,
    }.get(repo)


_PULSE_RULES = """
## Pulse (DocAI) Review Guidelines
- **Language:** Python / FastAPI backend, React frontend.
- **Critical areas:** Document extraction accuracy, OCR pipeline correctness, data privacy/PHI handling, audit logging.
- **Database:** Supabase Postgres. Watch for missing indexes on query-heavy paths, N+1 queries in the extraction service.
- **Error handling:** All API endpoints should return structured JSON errors (not bare 500s). Graceful degradation on OCR/LLM failures.
- **Testing:** Every extraction endpoint needs test coverage. New LLM prompts need evaluation tests.
- **Conventions:** FastAPI Pydantic models for request/response validation. Type hints required on all new functions.
"""

_STRIDE_RULES = """
## Stride Review Guidelines
- **Language:** Node.js/TypeScript backend (Express), React/TypeScript frontend.
- **Critical areas:** Student data privacy, session/auth security, real-time tutoring correctness, payment integration.
- **Database:** Supabase Postgres. Watch for N+1 in tutor-aggregation queries, missing RLS policies.
- **Frontend:** React 18/19 patterns. Avoid `useCallback` overuse — prefer plain functions with explicit params.
- **Gamification:** XP/level values are in `backend/config.js`. Don't hardcode them.
- **API:** All API routes use Express Router patterns. Auth middleware on all protected routes.
- **Testing:** Jest for backend, React Testing Library for frontend.
"""

_STRIDE_GPU_RULES = """
## Stride GPU Review Guidelines
- **Language:** Python, MLX framework for Apple Silicon GPU workloads.
- **Critical areas:** Model inference correctness, GPU memory management, request queuing, timeout handling.
- **Architecture:** All GPU changes go through repo (branch → PR → merge → GH Actions). Never run bootstrap.sh manually.
- **Conventions:** Caddy reverse proxy with rate limiting. No secrets in code — use env vars.
- **Error handling:** GPU OOM errors must be caught gracefully and return a 503 with retry hint.
"""

_SCHOLETE_WEBSITE_RULES = """
## Scholete Website Review Guidelines
- **Language:** React/TypeScript, possibly Next.js.
- **Critical areas:** SEO metadata, page performance (LCP/CLS), responsive design, accessibility.
- **Content:** Marketing copy should be reviewed for accuracy about product capabilities.
- **Analytics:** Check that new pages include analytics tracking hooks.
"""

_AGENTIC_WHALES_RULES = """
## AgenticWhales Review Guidelines
- **Language:** Python.
- **Critical areas:** Agent orchestration logic, tool-calling safety, state management.
- **Conventions:** Type hints on all functions. Make async where IO-bound.
- **Testing:** Every new tool needs unit tests. Integration tests for agent flows.
"""
