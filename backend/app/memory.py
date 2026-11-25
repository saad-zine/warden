"""Persistent cross-session memory with BM25 retrieval.

Memories are stored in SQLite and retrieved with BM25 (rank_bm25) — a
lexical retrieval method. The agent injects the top-k retrieved memories
into its context at the start of a run, so it remembers facts and
preferences across sessions.

Note on BM25Plus: classic BM25 IDF is log((N - df + 0.5)/(df + 0.5)),
which is *negative* for terms that appear in most documents. With a small
corpus (fewer than ~3 memories) that makes every score non-positive and
retrieval silently returns nothing. BM25Plus uses log((N + 1)/df), which
is always positive, so memory works from the very first row.
"""
import re

from rank_bm25 import BM25Plus

from . import db


def _tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


class MemoryStore:
    def __init__(self):
        self._docs = []
        self._bm25 = None
        self.refresh()

    def refresh(self):
        try:
            self._docs = db.list_memories()
        except Exception:
            # The DB/tables may not exist yet (import time, before init_db).
            self._docs = []
        corpus = [_tokens(m["content"]) for m in self._docs]
        self._bm25 = BM25Plus(corpus) if corpus else None

    def add(self, agent_id, content, category="fact"):
        mid = db.add_memory(agent_id, content, category)
        self.refresh()
        return mid

    def list(self, agent_id=None):
        return db.list_memories(agent_id)

    def update(self, mid, content=None, category=None):
        db.update_memory(mid, content, category)
        self.refresh()

    def delete(self, mid):
        db.delete_memory(mid)
        self.refresh()

    def retrieve(self, query, agent_id=None, k=3):
        """Return the top-k memories relevant to `query` (BM25 scores)."""
        if not self._docs:
            self.refresh()
        docs = self._docs
        if agent_id:
            docs = [d for d in docs if d["agent_id"] == agent_id]
        if not docs:
            return []
        # Rebuild the index on the filtered set (cheap: memory is small).
        corpus = [_tokens(d["content"]) for d in docs]
        bm25 = BM25Plus(corpus)
        scores = bm25.get_scores(_tokens(query))
        ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
        out = []
        for doc, score in ranked[:k]:
            if score > 0:
                d = dict(doc)
                d["score"] = round(float(score), 3)
                out.append(d)
        return out
