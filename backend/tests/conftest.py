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

from app import db  # noqa: E402

db.init_db()
db.seed_quests()
