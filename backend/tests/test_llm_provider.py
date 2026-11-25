"""Provider resolution, prompt assembly, and retry behaviour.

These are unit tests: no provider is contacted. Run with a real key to
exercise an actual model end to end.
"""
import pytest

from app import config, llm
from app.agents.model import DeterministicModel
from app.agents.tools import make_tools


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(config, "LLM_PROVIDER", "auto")
    llm.resolve_provider(force=True)
    yield
    monkeypatch.setattr(config, "LLM_PROVIDER", "deterministic")
    llm.resolve_provider(force=True)


def test_auto_without_keys_is_deterministic(monkeypatch):
    monkeypatch.setattr(llm, "_ollama_reachable", lambda: False)
    assert llm.resolve_provider(force=True) == "deterministic"
    assert llm.provider_info()["live"] is False


def test_auto_prefers_openai_then_anthropic(monkeypatch):
    monkeypatch.setattr(llm, "_ollama_reachable", lambda: False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert llm.resolve_provider(force=True) == "openai"

    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert llm.resolve_provider(force=True) == "anthropic"


def test_auto_falls_back_to_ollama_when_reachable(monkeypatch):
    monkeypatch.setattr(llm, "_ollama_reachable", lambda: True)
    assert llm.resolve_provider(force=True) == "ollama"


def test_explicit_provider_is_never_silently_replaced(monkeypatch):
    """A configured provider that cannot be built must raise, not downgrade."""
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    with pytest.raises(llm.ModelConfigError):
        llm.build_chat_model(make_tools(mode="mock"))


def test_unknown_provider_is_a_config_error(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "gpt-from-wish")
    with pytest.raises(llm.ModelConfigError):
        llm.resolve_provider(force=True)


def test_deterministic_model_binds_tools():
    tools = make_tools(mode="mock")
    model = llm.build_chat_model(tools, provider="deterministic")
    assert isinstance(model, DeterministicModel)
    assert "calculator" in model.available_tools


def test_system_prompt_carries_memory_and_tools():
    prompt = llm.build_system_prompt(
        "scout",
        [{"content": "Acme prefers annual billing.", "category": "preference"}],
        ["web_search", "calculator"],
    )
    assert "Acme prefers annual billing." in prompt
    assert "(preference)" in prompt
    assert "web_search, calculator" in prompt
    # The prompt must tell the model that approval gates are expected.
    assert "pauses the run" in prompt


def test_system_prompt_without_memory_is_clean():
    prompt = llm.build_system_prompt("scout", [], ["calculator"])
    assert "earlier sessions" not in prompt
    assert "calculator" in prompt


class _FlakyModel:
    def __init__(self, failures):
        self.calls = 0
        self.failures = failures

    def invoke(self, messages):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("provider unavailable")
        return "ok"


def test_retry_then_success(monkeypatch):
    monkeypatch.setattr(config, "LLM_MAX_RETRIES", 2)
    monkeypatch.setattr("time.sleep", lambda s: None)
    model = _FlakyModel(failures=2)
    assert llm.invoke_with_retry(model, []) == "ok"
    assert model.calls == 3


def test_retry_exhaustion_raises(monkeypatch):
    monkeypatch.setattr(config, "LLM_MAX_RETRIES", 1)
    monkeypatch.setattr("time.sleep", lambda s: None)
    model = _FlakyModel(failures=5)
    with pytest.raises(RuntimeError):
        llm.invoke_with_retry(model, [])
    assert model.calls == 2
