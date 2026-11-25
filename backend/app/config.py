"""Warden configuration."""

# Product name (confirmed 2026-11-24): WARDEN. A short, punchy, techy
# brand (Grok / LangGraph / n8n style, NOT Greek).
PRODUCT_NAME = "Warden"
import os
from pathlib import Path

# Load backend/.env (if present) before reading any setting below.
# Values already in the process environment win, so tests and Docker
# overrides behave as expected.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except Exception:  # python-dotenv missing or unreadable file: keep going
    pass

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = Path(__file__).resolve().parent

# SQLite databases (separate files: app data vs LangGraph checkpoints)
DATA_DB = os.environ.get("WARDEN_DATA_DB", str(BACKEND_DIR / "warden.db"))
CHECKPOINT_DB = os.environ.get(
    "WARDEN_CHECKPOINT_DB", str(BACKEND_DIR / "checkpoints.db")
)

# --- Model ---------------------------------------------------------------
# "auto" picks the best configured backend: OPENAI_API_KEY -> openai,
# ANTHROPIC_API_KEY -> anthropic, a reachable Ollama -> ollama, else the
# offline deterministic model. Force one with WARDEN_LLM=openai|anthropic|
# ollama|deterministic. A configured provider is never silently swapped
# for the fallback: if it fails, the run fails and says why.
LLM_PROVIDER = os.environ.get("WARDEN_LLM", "auto").strip().lower()
LLM_MODEL = os.environ.get("WARDEN_LLM_MODEL", "").strip()
LLM_TEMPERATURE = float(os.environ.get("WARDEN_LLM_TEMPERATURE", "0"))
LLM_TIMEOUT_S = float(os.environ.get("WARDEN_LLM_TIMEOUT", "90"))
LLM_MAX_RETRIES = int(os.environ.get("WARDEN_LLM_RETRIES", "2"))
# Any OpenAI-compatible gateway works here (Ollama, vLLM, Groq, OpenRouter).
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "").strip() or None
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")

# --- Tools ---------------------------------------------------------------
# "auto": real network tools with a labelled mock fallback.
# "real": real tools, failures surface as tool errors.
# "mock": fully offline synthetic data (deterministic in tests/CI).
TOOL_MODE = os.environ.get("WARDEN_TOOLS", "auto").strip().lower()
WEB_TIMEOUT_S = float(os.environ.get("WARDEN_WEB_TIMEOUT", "8"))
WEB_MAX_BYTES = int(os.environ.get("WARDEN_WEB_MAX_BYTES", "1000000"))
WEB_MAX_REDIRECTS = int(os.environ.get("WARDEN_WEB_MAX_REDIRECTS", "3"))

# --- Guardrail / spend limits (USD, estimated with reference rates) ------
MAX_COST_USD_PER_RUN = float(os.environ.get("WARDEN_MAX_COST_USD", "0.50"))
MAX_TOKENS_PER_RUN = int(os.environ.get("WARDEN_MAX_TOKENS", "20000"))
MAX_ITERATIONS = int(os.environ.get("WARDEN_MAX_ITERATIONS", "12"))

# Cost model (documented estimate): reference frontier-model rates.
COST_INPUT_PER_MTOK = 3.0    # $3 per 1M input tokens
COST_OUTPUT_PER_MTOK = 15.0  # $15 per 1M output tokens

# --- Execution -----------------------------------------------------------
# Runs execute in a bounded worker pool, never on the request thread.
WORKER_THREADS = int(os.environ.get("WARDEN_WORKERS", "4"))
# How often the SSE stream checks for new trace steps (seconds).
STREAM_POLL_S = float(os.environ.get("WARDEN_STREAM_POLL", "0.2"))

# --- Eval ----------------------------------------------------------------
EVAL_REGRESSION_THRESHOLD = 0.10  # block deploy if success rate drops >10pts vs baseline

# Tools that require a human approval before they run.
TOOLS_NEEDING_APPROVAL = {"crm_update", "send_message", "delete_file"}

# Demo output sandbox (file_writer writes here only).
OUTPUT_DIR = BACKEND_DIR / "output"

# CORS: comma-separated origins, or "*" for local development.
CORS_ORIGINS = [
    o.strip() for o in os.environ.get("WARDEN_CORS_ORIGINS", "*").split(",") if o.strip()
]
