"""JSON-based storage for reviews and PR metadata."""

import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path
from .config import DATA_DIR


def ensure_data_dir():
    """Ensure the data directory exists."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def _path(review_id: str) -> str:
    return os.path.join(DATA_DIR, f"{review_id}.json")


# ── CRUD ────────────────────────────────────────────────────────────

def create_review(review_id: str, pr_info: Optional[Dict] = None) -> Dict[str, Any]:
    """Create a new review record.

    Args:
        review_id: Unique identifier.
        pr_info:   Optional dict with ``owner``, ``repo``, ``pr_number``,
                   ``title``, ``sha``, ``author``.

    Returns:
        The new review dict.
    """
    ensure_data_dir()
    review = {
        "id": review_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": "Code Review",
        "status": "pending",  # pending | in_progress | completed | failed
        "pr": pr_info or {},
        "diff_text": "",
        "messages": [],
    }
    _save(review)
    return review


def get_review(review_id: str) -> Optional[Dict[str, Any]]:
    """Load a review from storage."""
    path = _path(review_id)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _save(review: Dict[str, Any]):
    path = _path(review["id"])
    with open(path, "w") as f:
        json.dump(review, f, indent=2)


def list_reviews() -> List[Dict[str, Any]]:
    """List all reviews (metadata only), newest first."""
    ensure_data_dir()
    reviews = []
    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".json"):
            continue
        with open(os.path.join(DATA_DIR, filename)) as f:
            data = json.load(f)
        pr = data.get("pr", {})
        reviews.append({
            "id": data["id"],
            "created_at": data["created_at"],
            "title": data.get("title", "Code Review"),
            "status": data.get("status", "unknown"),
            "repo": pr.get("repo", ""),
            "pr_number": pr.get("pr_number"),
            "pr_title": pr.get("title", ""),
            "message_count": len(data.get("messages", [])),
        })
    reviews.sort(key=lambda x: x["created_at"], reverse=True)
    return reviews


def delete_review(review_id: str) -> bool:
    """Delete a review record."""
    path = _path(review_id)
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True


# ── Mutations ───────────────────────────────────────────────────────

def update_review(
    review_id: str,
    **kwargs,
):
    """Update one or more fields on a review record.

    Accepts: ``title``, ``status``, ``diff_text``, ``pr``.
    """
    review = get_review(review_id)
    if review is None:
        raise ValueError(f"Review {review_id} not found")
    review.update(kwargs)
    _save(review)


def add_user_message(review_id: str, content: str):
    """Append a user message."""
    review = get_review(review_id)
    if review is None:
        raise ValueError(f"Review {review_id} not found")
    review["messages"].append({
        "role": "user",
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save(review)


def add_review_result(
    review_id: str,
    diff_text: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any],
):
    """Append a review result (replaces the old assistant message approach).

    Stores the full 3-stage output plus the original diff so each
    review record is self-contained.
    """
    review = get_review(review_id)
    if review is None:
        raise ValueError(f"Review {review_id} not found")
    review["diff_text"] = diff_text
    review["status"] = "completed" if stage3.get("response") else "failed"
    review["messages"].append({
        "role": "assistant",
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save(review)
