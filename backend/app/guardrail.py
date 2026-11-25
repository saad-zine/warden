"""Safety guardrail: policy + incident RAG for approval decisions.

Before a risky tool runs, the guardrail retrieves the relevant policy and
past-incident documents (BM25 over a small corpus of markdown files in
backend/policies/ and backend/incidents/) and records the retrieved
excerpts on the approval, so the human sees *why* the action needs a
decision and what happened last time. The approval requirement itself
comes from the policy table (which tools need approval); the RAG layer
provides the evidence.
"""
import re
from pathlib import Path

from rank_bm25 import BM25Plus

from . import config

POLICY_DIR = Path(__file__).resolve().parent.parent / "policies"
INCIDENT_DIR = Path(__file__).resolve().parent.parent / "incidents"


def _tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


class Guardrail:
    def __init__(self):
        self.docs = []  # {kind, name, title, text}
        for kind, folder in (("policy", POLICY_DIR), ("incident", INCIDENT_DIR)):
            if not folder.exists():
                continue
            for path in sorted(folder.glob("*.md")):
                text = path.read_text(encoding="utf-8")
                title = text.splitlines()[0].lstrip("# ").strip() if text else path.stem
                self.docs.append(
                    {"kind": kind, "name": path.name, "title": title, "text": text}
                )
        corpus = [_tokens(d["text"]) for d in self.docs]
        self._bm25 = BM25Plus(corpus) if corpus else None

    def needs_approval(self, tool_name):
        return tool_name in config.TOOLS_NEEDING_APPROVAL

    def retrieve(self, tool_name, args, k=3):
        """Retrieve the most relevant policy/incident docs for an action."""
        if self._bm25 is None:
            return []
        query = f"{tool_name} " + " ".join(str(v) for v in args.values())
        scores = self._bm25.get_scores(_tokens(query))
        ranked = sorted(zip(self.docs, scores), key=lambda x: x[1], reverse=True)
        out = []
        for doc, score in ranked[:k]:
            if score > 0:
                excerpt = " ".join(doc["text"].splitlines()[1:])[:280].strip()
                out.append(
                    {
                        "doc": doc["name"],
                        "kind": doc["kind"],
                        "title": doc["title"],
                        "excerpt": excerpt,
                        "score": round(float(score), 3),
                    }
                )
        return out

    def decide(self, tool_name, args):
        """Return {needs_approval, policy_refs} for an action."""
        refs = self.retrieve(tool_name, args, k=3)
        return {
            "needs_approval": self.needs_approval(tool_name),
            "policy_refs": refs,
        }
