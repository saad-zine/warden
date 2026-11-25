"""Warden configuration."""

# Product name (confirmed 2026-11-24): WARDEN. A short, punchy, techy
# brand (Grok / LangGraph / n8n style, NOT Greek).
PRODUCT_NAME = "Warden"
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = Path(__file__).resolve().parent

# SQLite databases (separate files: app data vs LangGraph checkpoints)
DATA_DB = os.environ.get("WARDEN_DATA_DB", str(BACKEND_DIR / "warden.db"))
CHECKPOINT_DB = os.environ.get(
    "WARDEN_CHECKPOINT_DB", str(BACKEND_DIR / "checkpoints.db")
)

# Guardrail / spend limits (USD, estimated with reference rates; see docs)
MAX_COST_USD_PER_RUN = float(os.environ.get("WARDEN_MAX_COST_USD", "0.50"))
MAX_TOKENS_PER_RUN = int(os.environ.get("WARDEN_MAX_TOKENS", "20000"))
MAX_ITERATIONS = int(os.environ.get("WARDEN_MAX_ITERATIONS", "12"))

# Cost model (documented estimate): reference frontier-model rates.
# Tokens are counted by a word-count proxy (see agents/model.py) — the
# number is an estimate, not a metered bill.
COST_INPUT_PER_MTOK = 3.0   # $3 per 1M input tokens
COST_OUTPUT_PER_MTOK = 15.0  # $15 per 1M output tokens

# Eval
EVAL_REGRESSION_THRESHOLD = 0.10  # block deploy if success rate drops >10pts vs baseline

# Tools that require a human approval before they run.
TOOLS_NEEDING_APPROVAL = {"crm_update", "send_message", "delete_file"}

# Demo output sandbox (file_writer writes here only).
OUTPUT_DIR = BACKEND_DIR / "output"
