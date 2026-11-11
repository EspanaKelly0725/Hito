"""The Claude layer: one thin wrapper every Hito agent goes through.

Three things matter here.

1. **Structured outputs.** Every agent that returns data to the product uses
   `output_config.format` with a JSON schema, so the backend never parses prose
   and never has to repair malformed JSON.
2. **Observability.** Each call records model, engine, latency, token counts and
   cost into `agent_runs`, which the dashboard shows. If a judge asks "is this
   really calling a model?", the answer is a table with token counts.
3. **A real fallback.** With no ANTHROPIC_API_KEY, every agent falls back to a
   deterministic rule engine and the UI says so. The demo never dead-ends on a
   missing key, and we never pretend rules are a model.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from ..config import settings

# USD per million tokens, from the published price list.
PRICING = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}

_client = None
_client_error: str | None = None


def client():
    """Lazily build the Anthropic client; None when unavailable."""
    global _client, _client_error
    if _client is not None or _client_error is not None:
        return _client
    if not settings.anthropic_api_key:
        _client_error = "ANTHROPIC_API_KEY not set"
        return None
    try:
        import anthropic

        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    except Exception as exc:  # pragma: no cover
        _client_error = f"anthropic sdk unavailable: {exc}"
        _client = None
    return _client


def _cost(model: str, usage: Any) -> float:
    rate_in, rate_out = PRICING.get(model, (4.00, 20.00))
    tin = getattr(usage, "input_tokens", 0) or 0
    tout = getattr(usage, "output_tokens", 0) or 0
    return round(tin / 1e6 * rate_in + tout / 1e6 * rate_out, 6)


def _meta(agent: str, engine: str, model: str, started: float,
          usage: Any = None, note: str = "") -> dict:
    meta = {
        "agent": agent,
        "engine": engine,
        "model": model,
        "latency_ms": int((time.time() - started) * 1000),
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cost_usd": _cost(model, usage) if usage is not None else 0.0,
    }
    if note:
        meta["note"] = note
    return meta


def _create(cli, **kwargs):
    """Call Claude, opting into server-side refusal fallback when supported.

    A refused request would otherwise just stop; on an SDK or platform that does
    not know the parameter we retry the plain call rather than fail the feature.
    """
    try:
        return cli.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            **kwargs,
        )
    except TypeError:
        pass
    except Exception as exc:  # unsupported beta / platform -> plain call
        if not _is_param_error(exc):
            raise
    return cli.messages.create(**kwargs)


def _is_param_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(s in text for s in ("fallback", "beta", "unexpected keyword",
                                   "unrecognized", "invalid_request"))


def call_json(agent: str, *, system: str, user: str, schema: dict,
              fallback: Callable[[], dict], model: str | None = None,
              effort: str = "medium", max_tokens: int = 8000) -> dict:
    """Run one agent. Returns its JSON payload plus a `_meta` block.

    `fallback` is the deterministic implementation of the same contract; it runs
    when there is no API key, when the SDK is missing, or when the call fails.
    """
    started = time.time()
    model = model or settings.model
    cli = client()
    if cli is None:
        data = fallback()
        data["_meta"] = _meta(agent, "rules", "rule-engine", started,
                              note=_client_error or "no api key")
        return data

    try:
        response = _create(
            cli,
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        )
        if getattr(response, "stop_reason", "") == "refusal":
            raise RuntimeError("model declined the request")
        text = next(
            (b.text for b in response.content if getattr(b, "type", "") == "text"), ""
        )
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("structured output was not an object")
        data["_meta"] = _meta(agent, "claude", getattr(response, "model", model),
                              started, response.usage)
        return data
    except Exception as exc:
        data = fallback()
        data["_meta"] = _meta(agent, "rules", "rule-engine", started,
                              note=f"claude call failed: {exc}")
        return data


def call_text(agent: str, *, system: str, user: str,
              fallback: Callable[[], str], model: str | None = None,
              effort: str = "medium", max_tokens: int = 2000) -> dict:
    """Same as call_json but for free-form copy (collection emails)."""
    started = time.time()
    model = model or settings.model
    cli = client()
    if cli is None:
        return {"text": fallback(),
                "_meta": _meta(agent, "rules", "rule-engine", started,
                               note=_client_error or "no api key")}
    try:
        response = _create(
            cli,
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort},
        )
        if getattr(response, "stop_reason", "") == "refusal":
            raise RuntimeError("model declined the request")
        text = "\n".join(
            b.text for b in response.content if getattr(b, "type", "") == "text"
        ).strip()
        return {"text": text or fallback(),
                "_meta": _meta(agent, "claude", getattr(response, "model", model),
                               started, response.usage)}
    except Exception as exc:
        return {"text": fallback(),
                "_meta": _meta(agent, "rules", "rule-engine", started,
                               note=f"claude call failed: {exc}")}


def status() -> dict:
    cli = client()
    return {
        "live": cli is not None,
        "model": settings.model if cli is not None else "rule-engine",
        "reason": _client_error,
    }


def money(value: float) -> str:
    return f"{float(value):,.2f}"


def first_number(text: str, default: float = 0.0) -> float:
    match = re.search(r"[\d][\d,]*\.?\d*", text or "")
    if not match:
        return default
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return default
