"""3-stage Review Council orchestration for code review.

Stage 1 — Each council model independently reviews the code diff.
Stage 2 — Each model evaluates the anonymised reviews (meta-review).
Stage 3 — Chairman synthesises a final consolidated review.
"""

from typing import List, Dict, Any, Tuple
from .llm_client import query_models_parallel, query_model
from .config import COUNCIL_MODELS, CHAIRMAN_MODEL, TITLE_MODEL


# ── Helpers ─────────────────────────────────────────────────────────

def _format_diff_for_prompt(diff_text: str, repo: str = "", pr_title: str = "") -> str:
    """Wrap a raw diff into a readable block prefixed with context."""
    parts = []
    if repo:
        parts.append(f"Repository: {repo}")
    if pr_title:
        parts.append(f"PR Title: {pr_title}")
    parts.append("```diff")
    parts.append(diff_text)
    parts.append("```")
    return "\n".join(parts)


# ── Stage 1: Individual Code Reviews ────────────────────────────────

async def stage1_collect_reviews(
    diff_text: str,
    *,
    repo: str = "",
    pr_title: str = "",
    pr_description: str = "",
) -> List[Dict[str, Any]]:
    """Stage 1 — each council model independently reviews the diff.

    Args:
        diff_text:      Unified diff text.
        repo:           Repository name (e.g. "pulse").
        pr_title:       Title of the pull request.
        pr_description: Description / body of the pull request.

    Returns:
        List of ``{"model", "response", "provider"}`` dicts.
    """
    formatted_diff = _format_diff_for_prompt(diff_text, repo, pr_title)

    review_prompt = f"""You are a senior engineer performing a focused code review.

Context:
{"  Repository: " + repo if repo else ""}
{"  PR Title: " + pr_title if pr_title else ""}
{"  PR Description: " + pr_description if pr_description else ""}

Below is the code diff to review:

{formatted_diff}

Focus ONLY on the files actually changed in this diff and their direct dependencies.
Do NOT review unrelated files, speculate about code you cannot see, or flag
hypothetical scenarios. Only flag issues in the changed code.

Review these areas:

1. **Summary** — What does this change do in a sentence?
2. **Correctness** — Any bugs, logic errors, or edge cases missed in the changed code?
3. **Security** — Injection risks, data leaks, auth/authorisation issues in the changed code?
4. **Code Quality** — Readability, maintainability, follows language/framework conventions?
5. **Architecture** — Coupling, separation of concerns, API design?
6. **Performance** — N+1 queries, unnecessary allocations, caching opportunities?
7. **Testing** — Are tests included? What scenarios are missing?

Do NOT include:
- Nitpicks, minor style issues, naming, or comments
- Issues in files not touched by this diff
- Hypothetical scenarios that "could" happen but won't

Be specific and actionable with file paths and line numbers.
If the changed code is correct, say so explicitly.

End with a **verdict**: ✅ Approve | ⚠️ Changes Requested | ❌ Deny

IMPORTANT: Only use ⚠️ Changes Requested if there is at least one Critical or High Priority issue directly in the changed code that will cause incorrect behavior in production. Missing tests, style suggestions, and architecture improvements are NOT blockers — mention them but default to ✅ Approve."""

    messages = [{"role": "user", "content": review_prompt}]

    responses = await query_models_parallel(COUNCIL_MODELS, messages)

    stage1_results = []
    for cfg in COUNCIL_MODELS:
        model_name = cfg["model"]
        resp = responses.get(model_name)
        if resp is not None:
            stage1_results.append({
                "model": model_name,
                "provider": cfg["provider"],
                "response": resp.get("content", ""),
            })

    return stage1_results


# ── Stage 2: Meta-Review (Anonymised Peer Evaluation) ──────────────

async def stage2_collect_rankings(
    diff_text: str,
    stage1_results: List[Dict[str, Any]],
    *,
    repo: str = "",
    pr_title: str = "",
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Stage 2 — each model evaluates the anonymised reviews.

    Args:
        diff_text:      Original diff (for context).
        stage1_results: Results from Stage 1.
        repo:           Repository name.
        pr_title:       PR title.

    Returns:
        ``(stage2_results, label_to_model)`` tuple.
    """
    # Anonymise: Response A, Response B, ...
    labels = [chr(65 + i) for i in range(len(stage1_results))]
    label_to_model = {
        f"Response {label}": f"{r['provider']}/{r['model']}"
        for label, r in zip(labels, stage1_results)
    }

    formatted_diff = _format_diff_for_prompt(diff_text, repo, pr_title)

    reviews_text = "\n\n".join([
        f"Response {label}:\n{r['response']}"
        for label, r in zip(labels, stage1_results)
    ])

    meta_prompt = f"""You are evaluating code reviews (not code). Below is a code diff followed by several anonymised reviews of it.

Code Diff:
{formatted_diff}

Reviews (anonymised):
{reviews_text}

Your task:
1. Evaluate each review individually. Which one caught the most issues? Which one was most thorough? Which gave the most actionable feedback?
2. At the very end of your response provide a final ranking.

IMPORTANT format for the ranking:
- Start with the line "FINAL RANKING:" (all caps, colon).
- Then list the responses from best to worst as a numbered list.
- Each line: number, period, space, then ONLY "Response X".
- No extra text after the ranking section.

Example:
FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking."""

    messages = [{"role": "user", "content": meta_prompt}]

    responses = await query_models_parallel(COUNCIL_MODELS, messages)

    stage2_results = []
    for cfg in COUNCIL_MODELS:
        model_name = cfg["model"]
        resp = responses.get(model_name)
        if resp is not None:
            full_text = resp.get("content", "")
            parsed = parse_ranking_from_text(full_text)
            stage2_results.append({
                "model": model_name,
                "provider": cfg["provider"],
                "ranking": full_text,
                "parsed_ranking": parsed,
            })

    return stage2_results, label_to_model


# ── Stage 3: Chairman Synthesis ─────────────────────────────────────

async def stage3_synthesize_final(
    diff_text: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    *,
    repo: str = "",
    pr_title: str = "",
) -> Dict[str, Any]:
    """Stage 3 — Chairman produces a single consolidated review.

    Args:
        diff_text:      Original diff.
        stage1_results: Individual reviews.
        stage2_results: Peer evaluations.
        repo:           Repository name.
        pr_title:       PR title.

    Returns:
        ``{"model", "provider", "response"}``
    """
    formatted_diff = _format_diff_for_prompt(diff_text, repo, pr_title)

    stage1_text = "\n\n".join([
        f"Reviewer: {r['provider']}/{r['model']}\n{r['response']}"
        for r in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Evaluator: {r['provider']}/{r['model']}\n{r['ranking']}"
        for r in stage2_results
    ])

    chairman_prompt = f"""You are the Chairman of a Review Council. Multiple AI models have reviewed a code diff and then evaluated each other's reviews.

{"Repository: " + repo if repo else ""}
{"PR Title: " + pr_title if pr_title else ""}

Code Diff:
{formatted_diff}

STAGE 1 — Individual Reviews:
{stage1_text}

STAGE 2 — Peer Evaluations of Reviews:
{stage2_text}

Your task as Chairman is to synthesise all of this into a **single, consolidated, actionable code review**.

Focus ONLY on the files actually changed in this diff. Do not speculate about code not visible in the diff.

Consider:
- The issues caught by each reviewer and their severity
- The peer evaluations — which reviews were most thorough
- Areas of agreement (high-confidence issues) vs disagreement
- Anything important that ALL reviewers missed

Format your final review as:

## Summary
(one-paragraph overview)

## Critical Issues
(file:line — description)
Only REAL bugs, security vulnerabilities, or data corruption risks in the changed code.
Leave empty if none.

## High Priority
(file:line — description)
Only missing auth/ownership checks, null guards, or incorrect data flow in the changed logic.
Leave empty if none.

## Code Quality & Architecture
(readability, maintainability, coupling, API design — non-blocking observations)

## Performance
(N+1 queries, allocations, caching — non-blocking observations)

## Testing
(are tests included? what's missing? — non-blocking)

## Positive Highlights
(what the PR does well)

## Verdict
✅ Approve | ⚠️ Changes Requested | ❌ Deny

CRITICAL RULE: Default to ✅ Approve. Only use ⚠️ Changes Requested if there is at least one Critical or High Priority issue that will cause incorrect behavior in production. Do NOT request changes for:
- Style, naming, formatting, nitpicks
- Missing tests (mention in Testing section instead)
- Architecture suggestions or follow-up tickets
- Hypothetical edge cases
- Issues in files not touched by this diff"""

    messages = [{"role": "user", "content": chairman_prompt}]

    response = await query_model(CHAIRMAN_MODEL, messages)
    if response is None:
        return {
            "model": CHAIRMAN_MODEL["model"],
            "provider": CHAIRMAN_MODEL["provider"],
            "response": "Error: Unable to generate final synthesis.",
        }

    return {
        "model": CHAIRMAN_MODEL["model"],
        "provider": CHAIRMAN_MODEL["provider"],
        "response": response.get("content", ""),
    }


# ── Ranking Parser ─────────────────────────────────────────────────

def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """Extract ``["Response C", "Response A", ...]`` from a model's output."""
    import re

    if "FINAL RANKING:" in ranking_text:
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            section = parts[1]
            # Match lines like "1. Response C" and extract "Response C"
            numbered = re.findall(r"\d+\.\s*(Response [A-Z])", section)
            if numbered:
                return numbered
            # Fallback: just "Response X" patterns in order
            return re.findall(r"Response [A-Z]", section)

    return re.findall(r"Response [A-Z]", ranking_text)


# ── Aggregate Rankings ─────────────────────────────────────────────

def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Average rank position per reviewer, sorted best to worst."""
    from collections import defaultdict

    positions = defaultdict(list)

    for r in stage2_results:
        parsed = parse_ranking_from_text(r["ranking"])
        for pos, label in enumerate(parsed, start=1):
            if label in label_to_model:
                positions[label_to_model[label]].append(pos)

    aggregate = []
    for reviewer, pos_list in positions.items():
        if pos_list:
            aggregate.append({
                "reviewer": reviewer,
                "average_rank": round(sum(pos_list) / len(pos_list), 2),
                "rankings_count": len(pos_list),
            })

    aggregate.sort(key=lambda x: x["average_rank"])
    return aggregate


# ── Title Generation ───────────────────────────────────────────────

async def generate_review_title(
    pr_title: str,
    repo: str = "",
) -> str:
    """Derive a short title for a code review."""
    context = f"Repository: {repo}\n" if repo else ""
    prompt = f"""{context}Generate a very short title (3-6 words) summarising this pull request review:
PR Title: {pr_title}

Title:"""
    messages = [{"role": "user", "content": prompt}]
    response = await query_model(TITLE_MODEL, messages, timeout=30.0)
    if response is None:
        return "Code Review"
    title = response.get("content", "Code Review").strip().strip("\"'")
    return title[:50] if len(title) <= 50 else title[:47] + "..."


# ── Full Pipeline ───────────────────────────────────────────────────

async def run_full_review(
    diff_text: str,
    *,
    repo: str = "",
    pr_title: str = "",
    pr_description: str = "",
) -> Tuple[List, List, Dict, Dict]:
    """Run the complete 3-stage review council.

    Returns:
        ``(stage1_results, stage2_results, stage3_result, metadata)``
    """
    # Stage 1
    stage1_results = await stage1_collect_reviews(
        diff_text, repo=repo, pr_title=pr_title, pr_description=pr_description,
    )
    if not stage1_results:
        return [], [], {
            "model": "error",
            "response": "All models failed to respond. Check API keys and try again.",
        }, {}

    # Stage 2
    stage2_results, label_to_model = await stage2_collect_rankings(
        diff_text, stage1_results, repo=repo, pr_title=pr_title,
    )

    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

    # Stage 3
    stage3_result = await stage3_synthesize_final(
        diff_text, stage1_results, stage2_results,
        repo=repo, pr_title=pr_title,
    )

    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings,
    }

    return stage1_results, stage2_results, stage3_result, metadata
