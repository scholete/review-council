"""Configuration for the Review Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Providers ──────────────────────────────────────────────────────
# Each provider has an API key and a base URL (OpenAI-compatible).

PROVIDER_CONFIGS = {
    "neuralwatt": {
        "api_key": os.getenv("NEURALWATT_API_KEY"),
        "base_url": "https://api.neuralwatt.com/v1",
    },
    "deepseek": {
        "api_key": os.getenv("DEEPSEEK_API_KEY"),
        "base_url": "https://api.deepseek.com",
    },
}

# ── Council members ────────────────────────────────────────────────
# Each entry specifies the provider and the model identifier to use.

COUNCIL_MODELS = [
    {"provider": "neuralwatt", "model": "glm-5.2"},
    {"provider": "deepseek", "model": "deepseek-v4-pro"},
]

# Chairman — synthesises the final review from stage 1 & 2 outputs.
CHAIRMAN_MODEL = {"provider": "deepseek", "model": "deepseek-v4-pro"}

# ── GitHub Integration ─────────────────────────────────────────────

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
MONITORED_REPOS = [
    repo.strip()
    for repo in os.getenv("MONITORED_REPOS", "").split(",")
    if repo.strip()
]

# ── Data Storage ───────────────────────────────────────────────────

DATA_DIR = os.getenv("DATA_DIR", "data/reviews")

# ── Title generation model (fast + cheap) ─────────────────────────

TITLE_MODEL = {"provider": "deepseek", "model": "deepseek-v4-pro"}
