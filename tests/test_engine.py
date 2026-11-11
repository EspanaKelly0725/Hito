"""The engine layer: which backend runs, and what happens when it cannot.

These matter because the whole product is built on the promise that Hito keeps
working when the model does not - and that it never claims a model ran when one
did not.
"""
from __future__ import annotations

import pytest

from app.agents import llm
from app.config import settings

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


@pytest.fixture
def provider():
    """Set HITO_LLM_PROVIDER for one test and put it back."""
    original = settings.llm_provider

    def _set(value: str) -> None:
        settings.llm_provider = value

    yield _set
    settings.llm_provider = original


def test_rules_provider_skips_every_model(provider):
    provider("rules")
    assert llm.chain() == []
    status = llm.status()
    assert status["live"] is False
    assert status["provider"] == "rules"
    assert status["model"] == "rule engine"


def test_pinning_a_provider_uses_only_that_one(provider):
    provider("ollama")
    assert llm.chain() == ["ollama"]
    provider("claude")
    assert llm.chain() == ["claude"]


def test_auto_falls_back_to_rules_when_nothing_is_configured(provider):
    provider("auto")
    # the test environment has no API key and, usually, no local model
    if not llm.ollama_status()["ok"] and not settings.anthropic_api_key:
        assert llm.chain() == []


def test_a_failed_backend_falls_through_to_the_deterministic_twin(provider):
    provider("ollama")  # pinned, and the test host has no model server
    result = llm.call_json(
        "test_agent",
        system="irrelevant",
        user="irrelevant",
        schema=SCHEMA,
        fallback=lambda: {"answer": "from the rule engine"},
    )
    assert result["answer"] == "from the rule engine"
    meta = result["_meta"]
    assert meta["engine"] == "rules", "a fallback must never be labelled as a model"
    assert meta["model"] == "rule engine"
    assert meta["cost_usd"] == 0.0
    assert meta["note"], "it has to say why the model did not run"


def test_text_calls_fall_back_the_same_way(provider):
    provider("ollama")
    result = llm.call_text(
        "test_agent", system="x", user="y", fallback=lambda: "templated copy"
    )
    assert result["text"] == "templated copy"
    assert result["_meta"]["engine"] == "rules"


def test_every_run_is_timed_even_when_it_falls_back(provider):
    provider("rules")
    result = llm.call_json("test_agent", system="x", user="y", schema=SCHEMA,
                           fallback=lambda: {"answer": "ok"})
    assert "latency_ms" in result["_meta"]
    assert result["_meta"]["agent"] == "test_agent"


# --- parsing what a small model actually returns ---------------------------

def test_json_parsing_tolerates_a_fenced_block():
    assert llm._loads('```json\n{"answer": "hi"}\n```') == {"answer": "hi"}
    assert llm._loads('```\n{"answer": "hi"}\n```') == {"answer": "hi"}


def test_json_parsing_finds_the_object_in_chatty_output():
    assert llm._loads('Sure! {"answer": "hi"} Hope that helps.') == {"answer": "hi"}


def test_json_parsing_rejects_a_non_object():
    with pytest.raises((ValueError, Exception)):
        llm._loads("[1, 2, 3]")


# --- model tag matching ----------------------------------------------------

@pytest.mark.parametrize("pulled,wanted,expected", [
    ("qwen2.5:3b", "qwen2.5:3b", True),
    ("qwen2.5:3b-instruct-q4_K_M", "qwen2.5:3b", True),
    ("qwen2.5:3b:latest", "qwen2.5:3b", True),
    ("qwen2.5:7b", "qwen2.5:3b", False),
    ("llama3.2:3b", "qwen2.5:3b", False),
])
def test_model_tag_matching(pulled, wanted, expected):
    assert llm._same_model(pulled, wanted) is expected


def test_status_names_the_cost_of_whatever_is_running(provider):
    provider("rules")
    assert "free" in llm.status()["cost"]


# --- fitting a contract into the engine's context window -------------------

def test_a_short_contract_is_passed_through_untouched():
    text = "Milestone 1 - Logo: US$3,000."
    assert llm.trim_to_budget(text, budget=1000) == text


def test_a_long_contract_keeps_its_head_and_its_tail():
    head = "Milestone 1 - Logo: US$3,000 due October 10, 2026."
    tail = "Signed for the Client: Dana Whitfield."
    text = head + ("x" * 50000) + tail
    trimmed = llm.trim_to_budget(text, budget=2000)

    assert len(trimmed) < len(text)
    # the fee schedule lives at the top and the signatures at the bottom;
    # losing either is the failure this function exists to prevent
    assert trimmed.startswith(head)
    assert trimmed.endswith(tail)
    assert "omitted to fit" in trimmed


def test_the_budget_follows_the_active_engine(provider):
    provider("claude")
    assert llm.context_budget_chars() == 50000
    provider("ollama")
    local = llm.context_budget_chars()
    assert 1000 < local < 50000, "a local 8K window is much smaller than Claude's"
