"""Test configuration: force mock mode and an isolated database."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Must be set before app.config is imported.
os.environ["HITO_FORCE_MOCK"] = "1"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.setdefault(
    "HITO_DB", str(Path(tempfile.gettempdir()) / "hito_test.db")
)

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    db.connect()
    db.reset()
    yield
    db.reset()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def contract_pdf() -> bytes:
    path = settings.data_dir / "contract_laura_bluebonnet.pdf"
    if not path.exists():
        import subprocess

        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "make_demo_pdf.py")], check=True
        )
    return path.read_bytes()
