"""GitHub integration for the Review Council.

Fetches PR diffs, posts review comments, sets commit statuses,
and handles incoming webhooks.
"""

import re
import hmac
import json
from hashlib import sha256
from typing import Optional, Dict, Any, List

import httpx

from .config import GITHUB_TOKEN, MONITORED_REPOS


# ── Helpers ─────────────────────────────────────────────────────────

def _headers() -> dict:
    if not GITHUB_TOKEN:
        raise RuntimeError(
            "GITHUB_TOKEN is not set. Add it to your .env file."
        )
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.diff",
        "User-Agent": "review-council/1.0",
    }


def _api_headers() -> dict:
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not set.")
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "review-council/1.0",
    }


# ── Parse a GitHub-style repo identifier ──────────────────────────

# Acceptable formats:
#   "https://github.com/scholete/pulse/pull/42"
#   "scholete/pulse#42"
#   "pulse#42"  (assumes scholete/ prefix when MONITORED_REPOS matches)
_PR_PATTERN = re.compile(
    r"(?:https?://github\.com/)?"
    r"(?P<owner>[\w.-]+)/"
    r"(?P<repo>[\w.-]+)"
    r"(?:/pull/|#)(?P<number>\d+)"
)


def parse_pr_url(url: str) -> Optional[tuple]:
    """Parse a PR URL into ``(owner, repo, pr_number)`` or ``None``.

    Accepts full URLs (``https://github.com/owner/repo/pull/42``) and
    shorthand (``owner/repo#42``).
    """
    m = _PR_PATTERN.search(url)
    if m:
        return m.group("owner"), m.group("repo"), int(m.group("number"))
    return None


# ── Fetch a PR diff ────────────────────────────────────────────────

async def fetch_pr_diff(
    owner: str,
    repo: str,
    pr_number: int,
) -> Optional[Dict[str, Any]]:
    """Fetch the unified diff for a pull request.

    Returns:
        Dict with ``diff_text``, ``title``, ``description``, ``sha``,
        ``author``, or ``None`` on error.
    """
    async with httpx.AsyncClient() as client:
        # Get PR metadata
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=_api_headers(),
        )
        if resp.status_code != 200:
            print(f"[github] Failed to fetch PR metadata: {resp.status_code}")
            print(f"[github] Response: {resp.text[:500]}")
            return None

        pr_data = resp.json()

        # Get the diff text
        diff_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=_headers(),
        )
        if diff_resp.status_code != 200:
            print(f"[github] Failed to fetch PR diff: {diff_resp.status_code}")
            return None

        return {
            "diff_text": diff_resp.text,
            "title": pr_data.get("title", ""),
            "description": pr_data.get("body", "") or "",
            "sha": pr_data.get("head", {}).get("sha", ""),
            "author": pr_data.get("user", {}).get("login", "unknown"),
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
        }


# ── Post a review to a PR ──────────────────────────────────────────

async def post_pr_review(
    owner: str,
    repo: str,
    pr_number: int,
    review_body: str,
    commit_sha: Optional[str] = None,
    event: str = "COMMENT",
) -> bool:
    """Post a PR review comment on GitHub.

    Args:
        owner:      Repository owner.
        repo:       Repository name.
        pr_number:  Pull request number.
        review_body: Markdown body of the review.
        commit_sha: Head commit SHA (optional, for line-specific reviews).
        event:      ``APPROVE``, ``COMMENT``, or ``REQUEST_CHANGES``.

    Returns:
        ``True`` on success.
    """
    payload: Dict[str, Any] = {
        "body": review_body,
        "event": event,
    }
    if commit_sha:
        payload["commit_id"] = commit_sha

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers=_api_headers(),
            json=payload,
        )
        if resp.status_code not in (200, 201):
            print(f"[github] Failed to post review: {resp.status_code} {resp.text[:300]}")
            return False
        return True


# ── Set commit status ──────────────────────────────────────────────

async def set_commit_status(
    owner: str,
    repo: str,
    sha: str,
    state: str,
    description: str,
    target_url: str = "",
) -> bool:
    """Set a commit status check (success/failure/pending).

    Args:
        owner:       Repository owner.
        repo:        Repository name.
        sha:         Commit SHA.
        state:       One of ``error``, ``failure``, ``pending``, ``success``.
        description: Short description for the status.
        target_url:  Optional link to the review.

    Returns:
        ``True`` on success.
    """
    payload: Dict[str, Any] = {
        "state": state,
        "description": description[:140],
        "context": "Review Council",
    }
    if target_url:
        payload["target_url"] = target_url

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/statuses/{sha}",
            headers=_api_headers(),
            json=payload,
        )
        if resp.status_code not in (200, 201):
            print(f"[github] Failed to set status: {resp.status_code} {resp.text[:300]}")
            return False
        return True


# ── Webhook payload parsing ────────────────────────────────────────

def parse_webhook_payload(
    body: bytes,
    signature_header: str = "",
    secret: str = "",
) -> Optional[Dict[str, Any]]:
    """Validate and parse a GitHub webhook payload.

    Args:
        body:            Raw request body.
        signature_header: Value of ``X-Hub-Signature-256`` header.
        secret:          Webhook secret (from config or env).

    Returns:
        Parsed JSON payload, or ``None`` if signature validation fails.
    """
    if secret and signature_header:
        expected = "sha256=" + hmac.new(
            secret.encode(),
            body,
            sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature_header):
            print("[github] Webhook signature mismatch")
            return None

    return json.loads(body)


def extract_pr_info_from_webhook(payload: dict) -> Optional[Dict[str, Any]]:
    """Extract PR info from a ``pull_request`` webhook event.

    Returns:
        Dict suitable for ``fetch_pr_diff()``, or ``None`` if the
        payload doesn't contain a PR we care about.
    """
    action = payload.get("action")
    if action not in ("opened", "synchronize", "reopened", "ready_for_review"):
        return None

    pr = payload.get("pull_request")
    if not pr:
        return None

    repo_full = payload.get("repository", {}).get("full_name", "")
    owner, repo_name = repo_full.split("/") if "/" in repo_full else ("", "")

    # Only review monitored repos
    if MONITORED_REPOS and repo_name not in MONITORED_REPOS:
        return None

    return {
        "owner": owner,
        "repo": repo_name,
        "pr_number": pr["number"],
    }


# ── List open PRs for monitored repos ──────────────────────────────

async def list_open_prs() -> List[Dict[str, Any]]:
    """List open PRs across all monitored repos.

    Returns:
        List of ``{"owner", "repo", "number", "title", "author"}``.
    """
    prs = []
    async with httpx.AsyncClient() as client:
        for repo_name in MONITORED_REPOS:
            # For each monitored repo, assume owner is "scholete"
            # (override if needed via config)
            resp = await client.get(
                f"https://api.github.com/repos/scholete/{repo_name}/pulls?state=open",
                headers=_api_headers(),
            )
            if resp.status_code != 200:
                continue
            for pr in resp.json():
                prs.append({
                    "owner": "scholete",
                    "repo": repo_name,
                    "number": pr["number"],
                    "title": pr["title"],
                    "author": pr["user"]["login"],
                })
    return prs
