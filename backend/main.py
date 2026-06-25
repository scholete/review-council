"""FastAPI backend for the Review Council.

Endpoints for submitting diffs, reviewing GitHub PRs, receiving
webhooks, and browsing past reviews.
"""

import uuid
import json
import asyncio
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import storage
from .council import (
    run_full_review,
    generate_review_title,
    stage1_collect_reviews,
    stage2_collect_rankings,
    stage3_synthesize_final,
    calculate_aggregate_rankings,
)
from .github_integration import (
    parse_pr_url,
    fetch_pr_diff,
    post_pr_review,
    set_commit_status,
    parse_webhook_payload,
    extract_pr_info_from_webhook,
    list_open_prs,
)
from .diff_analyzer import diff_summary

app = FastAPI(title="Review Council API")

# CORS for local frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ──────────────────────────────────────────────────────────

class SubmitDiffRequest(BaseModel):
    diff_text: str
    repo: str = ""
    pr_title: str = ""
    pr_description: str = ""


class SubmitPRRequest(BaseModel):
    pr_url: str


class ReviewMetadata(BaseModel):
    id: str
    created_at: str
    title: str
    status: str
    repo: str = ""
    pr_number: Optional[int] = None
    pr_title: str = ""
    message_count: int


class ReviewDetail(BaseModel):
    id: str
    created_at: str
    title: str
    status: str
    pr: Dict[str, Any]
    diff_text: str
    messages: List[Dict[str, Any]]


# ── Endpoints ───────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "service": "Review Council API"}


# ── List / Create / Get / Delete reviews ───────────────────────────

@app.get("/api/reviews", response_model=List[ReviewMetadata])
async def list_reviews():
    return storage.list_reviews()


@app.get("/api/reviews/{review_id}", response_model=ReviewDetail)
async def get_review(review_id: str):
    review = storage.get_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@app.delete("/api/reviews/{review_id}")
async def delete_review(review_id: str):
    if not storage.delete_review(review_id):
        raise HTTPException(status_code=404, detail="Review not found")
    return {"status": "deleted"}


# ── Submit a raw diff for review ────────────────────────────────────

@app.post("/api/review")
async def submit_diff(request: SubmitDiffRequest):
    """Submit a raw diff for council review."""
    review_id = str(uuid.uuid4())
    review = storage.create_review(review_id, pr_info={
        "repo": request.repo,
        "title": request.pr_title or diff_summary(request.diff_text),
        "diff_summary": diff_summary(request.diff_text),
    })

    if request.repo:
        title = await generate_review_title(
            request.pr_title or diff_summary(request.diff_text),
            repo=request.repo,
        )
        storage.update_review(review_id, title=title)

    storage.add_user_message(review_id, f"Review diff for {request.repo or 'unknown'}")

    stage1, stage2, stage3, metadata = await run_full_review(
        request.diff_text,
        repo=request.repo,
        pr_title=request.pr_title,
        pr_description=request.pr_description,
    )

    storage.add_review_result(review_id, request.diff_text, stage1, stage2, stage3)

    return {
        "review_id": review_id,
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
        "metadata": metadata,
    }


# ── Submit a GitHub PR for review ──────────────────────────────────

@app.post("/api/review/pr")
async def submit_pr(request: SubmitPRRequest):
    """Fetch a GitHub PR diff and submit for council review."""
    parsed = parse_pr_url(request.pr_url)
    if parsed is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid PR URL. Use format: https://github.com/owner/repo/pull/42 or owner/repo#42",
        )

    owner, repo_name, pr_number = parsed

    pr_data = await fetch_pr_diff(owner, repo_name, pr_number)
    if pr_data is None:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch PR from GitHub. Check that the repo and PR exist, and GITHUB_TOKEN is set.",
        )

    review_id = str(uuid.uuid4())
    storage.create_review(review_id, pr_info={
        "owner": owner,
        "repo": repo_name,
        "pr_number": pr_number,
        "title": pr_data["title"],
        "sha": pr_data["sha"],
        "author": pr_data["author"],
    })

    # Set commit status to pending
    if pr_data["sha"]:
        await set_commit_status(
            owner, repo_name, pr_data["sha"],
            state="pending",
            description="Review Council is analysing this PR...",
        )

    # Run the review
    storage.add_user_message(review_id, f"Review PR #{pr_number} in {owner}/{repo_name}")

    stage1, stage2, stage3, metadata = await run_full_review(
        pr_data["diff_text"],
        repo=repo_name,
        pr_title=pr_data["title"],
        pr_description=pr_data["description"],
    )

    storage.add_review_result(review_id, pr_data["diff_text"], stage1, stage2, stage3)
    if pr_data["title"]:
        storage.update_review(review_id, title=f"PR #{pr_number}: {pr_data['title'][:50]}")

    # Post review back to GitHub
    verdict = "✅ Approved"
    if stage3["response"] and "deny" in stage3["response"].lower():
        verdict = "❌ Changes Requested"
    elif stage3["response"] and "changes requested" in stage3["response"].lower():
        verdict = "⚠️ Changes Requested"

    review_body = f"""# Review Council — PR #{pr_number}

{verdict}

---

{stage3['response']}
"""
    await post_pr_review(owner, repo_name, pr_number, review_body)

    # Update commit status
    if pr_data["sha"]:
        if stage3["response"] and "deny" in stage3["response"].split("\n")[0].lower():
            await set_commit_status(
                owner, repo_name, pr_data["sha"],
                state="failure",
                description="Review Council: changes requested",
            )
        else:
            await set_commit_status(
                owner, repo_name, pr_data["sha"],
                state="success",
                description="Review Council: review complete",
            )

    return {
        "review_id": review_id,
        "pr": {
            "owner": owner,
            "repo": repo_name,
            "number": pr_number,
            "title": pr_data["title"],
        },
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
        "metadata": metadata,
    }


# ── Streamed version (supports larger diffs with progress) ─────────

@app.post("/api/review/stream")
async def submit_diff_stream(request: SubmitDiffRequest):
    """Submit a diff and stream the 3-stage review as SSE events."""

    async def event_generator():
        review_id = str(uuid.uuid4())
        storage.create_review(review_id, pr_info={
            "repo": request.repo,
            "title": request.pr_title or diff_summary(request.diff_text),
        })
        storage.add_user_message(review_id, f"Review diff for {request.repo or 'unknown'}")

        yield f"data: {json.dumps({'type': 'review_created', 'review_id': review_id})}\n\n"

        # Stage 1
        yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
        stage1 = await stage1_collect_reviews(
            request.diff_text,
            repo=request.repo,
            pr_title=request.pr_title,
            pr_description=request.pr_description,
        )
        yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1})}\n\n"

        if not stage1:
            yield f"data: {json.dumps({'type': 'error', 'message': 'All models failed'})}\n\n"
            return

        # Stage 2
        yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
        stage2, label_to_model = await stage2_collect_rankings(
            request.diff_text, stage1, repo=request.repo, pr_title=request.pr_title,
        )
        aggregate = calculate_aggregate_rankings(stage2, label_to_model)
        yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate}})}\n\n"

        # Stage 3
        yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
        stage3 = await stage3_synthesize_final(
            request.diff_text, stage1, stage2,
            repo=request.repo, pr_title=request.pr_title,
        )
        yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3})}\n\n"

        # Save
        storage.add_review_result(review_id, request.diff_text, stage1, stage2, stage3)
        yield f"data: {json.dumps({'type': 'complete', 'review_id': review_id})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ── Webhook: auto-review new PRs ────────────────────────────────────

@app.post("/webhooks/github")
async def github_webhook(request: Request):
    """Receive GitHub webhook events for automatic PR review."""
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")

    payload = parse_webhook_payload(body, sig, secret)
    if payload is None and secret:
        raise HTTPException(status_code=403, detail="Signature mismatch")

    # Skip validation if no secret configured (development mode)
    if payload is None:
        payload = json.loads(body)

    event = request.headers.get("X-GitHub-Event", "")

    if event == "ping":
        return {"status": "pong"}

    if event != "pull_request":
        return {"status": "ignored", "reason": f"unsupported event: {event}"}

    pr_info = extract_pr_info_from_webhook(payload)
    if pr_info is None:
        return {"status": "ignored", "reason": "action or repo not monitored"}

    # Fire-and-forget: trigger a review in the background
    asyncio.create_task(_auto_review(pr_info))

    return {"status": "accepted", "pr": f"{pr_info['owner']}/{pr_info['repo']}#{pr_info['pr_number']}"}


async def _auto_review(pr_info: dict):
    """Background task for auto-reviewing a PR."""
    pr_data = await fetch_pr_diff(
        pr_info["owner"], pr_info["repo"], pr_info["pr_number"],
    )
    if pr_data is None:
        return

    review_id = str(uuid.uuid4())
    storage.create_review(review_id, pr_info={
        "owner": pr_info["owner"],
        "repo": pr_info["repo"],
        "pr_number": pr_info["pr_number"],
        "title": pr_data["title"],
        "sha": pr_data["sha"],
        "author": pr_data["author"],
    })

    if pr_data["sha"]:
        await set_commit_status(
            pr_info["owner"], pr_info["repo"], pr_data["sha"],
            state="pending",
            description="Review Council is analysing this PR...",
        )

    stage1, stage2, stage3, metadata = await run_full_review(
        pr_data["diff_text"],
        repo=pr_info["repo"],
        pr_title=pr_data["title"],
        pr_description=pr_data["description"],
    )

    storage.add_review_result(review_id, pr_data["diff_text"], stage1, stage2, stage3)

    verdict = "✅ Approved"
    if stage3["response"] and "deny" in stage3["response"].lower():
        verdict = "❌ Changes Requested"
    elif stage3["response"] and "changes requested" in stage3["response"].lower():
        verdict = "⚠️ Changes Requested"

    review_body = f"# Review Council — PR #{pr_info['pr_number']}\n\n{verdict}\n\n---\n\n{stage3['response']}"
    await post_pr_review(pr_info["owner"], pr_info["repo"], pr_info["pr_number"], review_body)

    if pr_data["sha"]:
        state = "failure" if "deny" in (stage3.get("response", "") or "").lower() else "success"
        await set_commit_status(
            pr_info["owner"], pr_info["repo"], pr_data["sha"],
            state=state,
            description="Review Council: review complete",
        )


# ── List open PRs from monitored repos ─────────────────────────────

@app.get("/api/prs")
async def open_prs():
    """List open pull requests across monitored repos."""
    prs = await list_open_prs()
    return prs


# ── Entry point ─────────────────────────────────────────────────────

import os

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
