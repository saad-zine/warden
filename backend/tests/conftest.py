"""Test setup: point the app at throwaway SQLite files.

The env vars are set here, before any app module is imported, so
config.py picks up the temp paths. All tests in a session share one
temp DB; runs use unique ids, so tests stay independent.
"""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="warden_test_")
os.environ["WARDEN_DATA_DB"] = os.path.join(_tmp, "warden.db")
os.environ["WARDEN_CHECKPOINT_DB"] = os.path.join(_tmp, "checkpoints.db")
# Tests never touch the network or a paid model: the deterministic model and
# mock tools are the offline contract. Real-provider code paths are unit
# tested directly (tests/test_llm_provider.py, tests/test_web_tools.py).
os.environ["WARDEN_LLM"] = "deterministic"
os.environ["WARDEN_TOOLS"] = "mock"
for _key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TAVILY_API_KEY", "BRAVE_API_KEY"):
    os.environ.pop(_key, None)

from app import db  # noqa: E402

db.init_db()
db.seed_quests()
