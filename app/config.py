"""Configuration. Reads .env (no external dependency) then the environment."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    # PayPal ---------------------------------------------------------------
    paypal_client_id: str = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    paypal_client_secret: str = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    paypal_env: str = os.getenv("PAYPAL_ENV", "sandbox").strip().lower()
    paypal_webhook_id: str = os.getenv("PAYPAL_WEBHOOK_ID", "").strip()
    invoicer_email: str = os.getenv("PAYPAL_INVOICER_EMAIL", "laura@hito.studio").strip()
    invoicer_given_name: str = os.getenv("PAYPAL_INVOICER_GIVEN_NAME", "Laura").strip()
    invoicer_surname: str = os.getenv("PAYPAL_INVOICER_SURNAME", "Restrepo").strip()
    invoicer_business: str = os.getenv(
        "PAYPAL_INVOICER_BUSINESS", "Laura Restrepo Design Studio"
    ).strip()

    # AI -------------------------------------------------------------------
    # auto = prefer the local open-weights model, fall back to Claude if a key
    # is configured, fall back to the deterministic engine otherwise.
    llm_provider: str = os.getenv("HITO_LLM_PROVIDER", "auto").strip().lower()

    # Open-source model, run locally through Ollama. Apache-2.0 weights, no
    # account, no key, no data leaving the machine.
    ollama_host: str = os.getenv(
        "OLLAMA_HOST", "http://127.0.0.1:11434"
    ).strip().rstrip("/")
    ollama_model: str = os.getenv("HITO_OLLAMA_MODEL", "qwen2.5:3b").strip()
    ollama_ctx: int = int(os.getenv("HITO_OLLAMA_CTX", "8192") or 8192)
    ollama_timeout: float = float(os.getenv("HITO_OLLAMA_TIMEOUT", "180") or 180)

    # The same open-weights model, served by someone else's GPU. This is what
    # the hosted demo runs: a 2 GB model does not fit a free instance, but the
    # product should still show a model working rather than a rule engine.
    # Any OpenAI-compatible endpoint works (OpenRouter, Groq, Together, vLLM).
    remote_base_url: str = os.getenv("HITO_REMOTE_BASE_URL", "").strip().rstrip("/")
    remote_api_key: str = os.getenv("HITO_REMOTE_API_KEY", "").strip()
    remote_model: str = os.getenv("HITO_REMOTE_MODEL", "qwen/qwen3-32b").strip()
    remote_timeout: float = float(os.getenv("HITO_REMOTE_TIMEOUT", "120") or 120)

    # Claude, optional.
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
    model: str = os.getenv("HITO_MODEL", "claude-opus-5-5").strip()
    model_fast: str = os.getenv("HITO_MODEL_FAST", "claude-haiku-5-5").strip()

    # Policy ---------------------------------------------------------------
    payout_threshold: float = float(os.getenv("PAYOUT_APPROVAL_THRESHOLD_USD", "800") or 800)
    force_mock: bool = _flag("HITO_FORCE_MOCK")

    # Paths ----------------------------------------------------------------
    db_path: Path = Path(os.getenv("HITO_DB", str(ROOT / "hito.db")))
    data_dir: Path = ROOT / "data"
    static_dir: Path = ROOT / "app" / "static"

    @property
    def paypal_base_url(self) -> str:
        if self.paypal_env == "live":
            return "https://api-m.paypal.com"
        return "https://api-m.sandbox.paypal.com"

    @property
    def paypal_live(self) -> bool:
        """True when real PayPal REST calls will be made."""
        return bool(self.paypal_client_id and self.paypal_client_secret) and not self.force_mock

    @property
    def claude_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    def modes(self) -> dict:
        from .agents import llm  # local import: llm imports settings

        engine = llm.status()
        return {
            "paypal": "sandbox" if (self.paypal_live and self.paypal_env == "sandbox")
            else ("live" if self.paypal_live else "mock"),
            "paypal_live": self.paypal_live,
            "ai": engine["model"],
            "ai_provider": engine["provider"],
            "ai_live": engine["live"],
            "ai_local": engine["provider"] == "ollama",
            # Why the engine is what it is, in words a person can act on -
            # the UI shows this so a judge is told how to turn the model on
            # rather than left guessing why it says "rule engine".
            "ai_detail": engine["detail"],
            "payout_threshold": self.payout_threshold,
            "webhook_verification": bool(self.paypal_webhook_id),
        }


settings = Settings()
