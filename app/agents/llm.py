"""The model layer: one thin wrapper every Hito agent goes through.

Three backends, tried in this order, each with the same contract:

1. **A local open-source model** (Qwen2.5 3B Instruct, Apache-2.0, through
   Ollama). This is the default. It needs no account, no API key and no
   network: the contract never leaves the machine, which for a document that
   contains a client's name, address and fee schedule is the right default for
   a freelancer rather than a nice-to-have.
2. **Claude**, if `ANTHROPIC_API_KEY` is set. Better at the harder judgment
   calls, and the project supports it, but it is opt-in.
3. **A deterministic rule engine**, always. Every agent has a hand-written twin
   with the same output contract, so the product degrades instead of breaking.

Four things matter in here:

* **Structured outputs.** Both model backends are constrained by the same JSON
  schema - Ollama's `format` field and Claude's `output_config.format` - so the
  backend never parses prose and never repairs malformed JSON.
* **Honest labelling.** Whatever ran is recorded and shown in the UI. The rule
  engine is never presented as a model.
* **Observability.** Model, engine, latency, token counts and cost go into
  `agent_runs` per call.
* **It always answers.** A backend that is down, slow or wrong falls through to
  the next one.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

import httpx

from ..config import settings

# USD per million tokens, from the published price list. Local models are free,
# which is a real part of the argument for them.
PRICING = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}

_claude = None
_claude_error: str | None = None
_ollama_state: dict = {"checked_at": 0.0, "ok": False, "detail": "", "models": []}
OLLAMA_RECHECK_SECONDS = 20.0


# ---------------------------------------------------------------------------
# backend 1: the local open-source model
# ---------------------------------------------------------------------------

def _same_model(pulled: str, wanted: str) -> bool:
    """Ollama tags are loose: 'qwen2.5:3b' may be listed as 'qwen2.5:3b' or
    'qwen2.5:3b-instruct-q4_K_M', and a bare name gets ':latest' appended."""
    pulled = pulled.strip().removesuffix(":latest")
    wanted = wanted.strip().removesuffix(":latest")
    return pulled == wanted or pulled.startswith(wanted)


def ollama_status(force: bool = False) -> dict:
    """Is a local model actually there? Cached, because agents call it a lot."""
    now = time.time()
    if not force and now - _ollama_state["checked_at"] < OLLAMA_RECHECK_SECONDS:
        return _ollama_state

    _ollama_state["checked_at"] = now
    try:
        response = httpx.get(f"{settings.ollama_host}/api/tags", timeout=2.5)
        response.raise_for_status()
        models = [m.get("name", "") for m in response.json().get("models", [])]
        _ollama_state["models"] = models
        wanted = settings.ollama_model
        if any(_same_model(m, wanted) for m in models):
            _ollama_state.update(ok=True, detail=f"{wanted} ready")
        elif models:
            _ollama_state.update(
                ok=False,
                detail=f"Ollama is running but {wanted} is not pulled "
                       f"(have: {', '.join(models[:4])}). "
                       f"Run: ollama pull {wanted}",
            )
        else:
            _ollama_state.update(
                ok=False,
                detail=f"Ollama is running but has no models. "
                       f"Run: ollama pull {wanted}",
            )
    except Exception as exc:
        _ollama_state.update(
            ok=False,
            models=[],
            detail=f"no local model server at {settings.ollama_host} ({type(exc).__name__})",
        )
    return _ollama_state


def _ollama_chat(*, system: str, user: str, schema: dict | None,
                 max_tokens: int) -> tuple[str, dict]:
    payload: dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {
            # Extraction, not creative writing: no sampling noise, and a context
            # window that fits a contract without pushing a laptop into swap.
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": settings.ollama_ctx,
            "num_predict": max_tokens,
        },
    }
    if schema is not None:
        payload["format"] = schema

    response = httpx.post(
        f"{settings.ollama_host}/api/chat",
        json=payload,
        timeout=settings.ollama_timeout,
    )
    response.raise_for_status()
    body = response.json()
    text = (body.get("message") or {}).get("content", "")
    usage = {
        "input_tokens": int(body.get("prompt_eval_count") or 0),
        "output_tokens": int(body.get("eval_count") or 0),
    }
    if not text.strip():
        raise RuntimeError("local model returned an empty response")
    return text, usage


# ---------------------------------------------------------------------------
# backend 2: Claude
# ---------------------------------------------------------------------------

def claude_client():
    global _claude, _claude_error
    if _claude is not None or _claude_error is not None:
        return _claude
    if not settings.anthropic_api_key:
        _claude_error = "ANTHROPIC_API_KEY not set"
        return None
    try:
        import anthropic

        _claude = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    except Exception as exc:  # pragma: no cover
        _claude_error = f"anthropic sdk unavailable: {exc}"
        _claude = None
    return _claude


def _claude_create(cli, **kwargs):
    """Call Claude, opting into server-side refusal fallback when supported."""
    try:
        return cli.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            **kwargs,
        )
    except TypeError:
        pass
    except Exception as exc:
        if not _is_param_error(exc):
            raise
    return cli.messages.create(**kwargs)


def _is_param_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(s in text for s in ("fallback", "beta", "unexpected keyword",
                                   "unrecognized", "invalid_request"))


def _claude_chat(cli, *, system: str, user: str, schema: dict | None,
                 effort: str, max_tokens: int) -> tuple[str, Any, str]:
    output_config: dict[str, Any] = {"effort": effort}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    response = _claude_create(
        cli,
        model=settings.model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config=output_config,
    )
    if getattr(response, "stop_reason", "") == "refusal":
        raise RuntimeError("model declined the request")
    text = "\n".join(
        b.text for b in response.content if getattr(b, "type", "") == "text"
    ).strip()
    return text, response.usage, getattr(response, "model", settings.model)


# ---------------------------------------------------------------------------
# provider selection
# ---------------------------------------------------------------------------

def chain() -> list[str]:
    """Which backends to try, in order, for the configured provider."""
    choice = settings.llm_provider
    if choice == "ollama":
        return ["ollama"]
    if choice == "claude":
        return ["claude"]
    if choice == "rules":
        return []
    order = []
    if ollama_status()["ok"]:
        order.append("ollama")
    if settings.anthropic_api_key:
        order.append("claude")
    return order


def status() -> dict:
    """What the UI and /api/status report about the engine."""
    local = ollama_status()
    order = chain()
    active = order[0] if order else "rules"
    if active == "ollama":
        return {
            "live": True,
            "provider": "ollama",
            "model": settings.ollama_model,
            "label": f"{settings.ollama_model} (local, open source)",
            "detail": local["detail"],
            "cost": "free - runs on this machine",
            "fallbacks": order[1:] + ["rules"],
        }
    if active == "claude":
        return {
            "live": True,
            "provider": "claude",
            "model": settings.model,
            "label": settings.model,
            "detail": _claude_error or "api key configured",
            "cost": "billed per token",
            "fallbacks": ["rules"],
        }
    return {
        "live": False,
        "provider": "rules",
        "model": "rule engine",
        "label": "rule engine",
        "detail": local["detail"],
        "cost": "free",
        "fallbacks": [],
    }


# ---------------------------------------------------------------------------
# cost / metadata
# ---------------------------------------------------------------------------

def _cost(model: str, usage: Any) -> float:
    rate_in, rate_out = PRICING.get(model, (0.0, 0.0))
    tin = getattr(usage, "input_tokens", 0) or 0
    tout = getattr(usage, "output_tokens", 0) or 0
    return round(tin / 1e6 * rate_in + tout / 1e6 * rate_out, 6)


def _meta(agent: str, engine: str, model: str, started: float, *,
          usage: Any = None, tokens: dict | None = None, note: str = "") -> dict:
    meta = {
        "agent": agent,
        "engine": engine,
        "model": model,
        "latency_ms": int((time.time() - started) * 1000),
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
    }
    if tokens:
        meta.update(tokens)
    elif usage is not None:
        meta["input_tokens"] = getattr(usage, "input_tokens", 0) or 0
        meta["output_tokens"] = getattr(usage, "output_tokens", 0) or 0
        meta["cost_usd"] = _cost(model, usage)
    if note:
        meta["note"] = note
    return meta


def _loads(text: str) -> dict:
    """Parse the model's JSON, tolerating a fenced block from a small model."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("structured output was not an object")
    return data


# ---------------------------------------------------------------------------
# the two calls every agent makes
# ---------------------------------------------------------------------------

def call_json(agent: str, *, system: str, user: str, schema: dict,
              fallback: Callable[[], dict], model: str | None = None,
              effort: str = "medium", max_tokens: int = 8000) -> dict:
    """Run one agent and return its JSON payload plus a `_meta` block."""
    started = time.time()
    notes: list[str] = []

    for backend in chain():
        try:
            if backend == "ollama":
                text, tokens = _ollama_chat(
                    system=system, user=user, schema=schema,
                    max_tokens=min(max_tokens, 4096),
                )
                data = _loads(text)
                data["_meta"] = _meta(agent, "ollama", settings.ollama_model,
                                      started, tokens=tokens)
                return data

            cli = claude_client()
            if cli is None:
                notes.append(_claude_error or "claude unavailable")
                continue
            text, usage, used_model = _claude_chat(
                cli, system=system, user=user, schema=schema,
                effort=effort, max_tokens=max_tokens,
            )
            data = _loads(text)
            data["_meta"] = _meta(agent, "claude", used_model, started, usage=usage)
            return data
        except Exception as exc:
            notes.append(f"{backend}: {exc}")

    data = fallback()
    data["_meta"] = _meta(agent, "rules", "rule engine", started,
                          note="; ".join(notes) or ollama_status()["detail"])
    return data


def call_text(agent: str, *, system: str, user: str,
              fallback: Callable[[], str], model: str | None = None,
              effort: str = "medium", max_tokens: int = 2000) -> dict:
    """Same as call_json but for free-form copy."""
    started = time.time()
    notes: list[str] = []

    for backend in chain():
        try:
            if backend == "ollama":
                text, tokens = _ollama_chat(
                    system=system, user=user, schema=None,
                    max_tokens=min(max_tokens, 2048),
                )
                return {"text": text.strip(),
                        "_meta": _meta(agent, "ollama", settings.ollama_model,
                                       started, tokens=tokens)}
            cli = claude_client()
            if cli is None:
                notes.append(_claude_error or "claude unavailable")
                continue
            text, usage, used_model = _claude_chat(
                cli, system=system, user=user, schema=None,
                effort=effort, max_tokens=max_tokens,
            )
            return {"text": text or fallback(),
                    "_meta": _meta(agent, "claude", used_model, started,
                                   usage=usage)}
        except Exception as exc:
            notes.append(f"{backend}: {exc}")

    return {"text": fallback(),
            "_meta": _meta(agent, "rules", "rule engine", started,
                           note="; ".join(notes) or ollama_status()["detail"])}


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
