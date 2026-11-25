"""Memory: CRUD + BM25 retrieval."""
from app.memory import MemoryStore


def test_memory_crud_and_retrieval():
    store = MemoryStore()
    mid = store.add("scout", "Acme Corp prefers annual billing, not monthly.", "preference")
    store.add("scout", "Globex Ltd has 120 seats on the Enterprise plan.", "fact")
    store.add("scout", "The office coffee machine is broken.", "fact")

    # Retrieval finds the relevant memory for a billing question.
    found = store.retrieve("does Acme prefer annual or monthly billing?", agent_id="scout")
    assert found
    assert "Acme" in found[0]["content"]
    assert "annual billing" in found[0]["content"]

    # Update + delete.
    store.update(mid, "Acme Corp prefers annual billing and a $200 setup fee.", "preference")
    found = store.retrieve("Acme setup fee", agent_id="scout")
    assert any("setup fee" in m["content"] for m in found)
    store.delete(mid)
    assert not any(m["id"] == mid for m in store.list("scout"))


def test_memory_is_scoped_per_agent():
    store = MemoryStore()
    store.add("scout", "Scout-only fact: the vendor is Acme Corp.", "fact")
    store.add("planner", "Planner-only fact: the deadline is Friday.", "fact")
    scout = store.retrieve("vendor Acme", agent_id="scout")
    assert all(m["agent_id"] == "scout" for m in scout)
    planner = store.retrieve("deadline Friday", agent_id="planner")
    assert all(m["agent_id"] == "planner" for m in planner)
