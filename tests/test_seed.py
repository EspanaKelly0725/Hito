"""Seeding client history must never destroy live work."""
from __future__ import annotations


def test_seed_is_safe_to_run_after_a_project_exists(client, contract_pdf):
    from tests.test_flow import approve_sample_plan

    milestones = approve_sample_plan(client, contract_pdf)
    assert len(milestones) == 3

    client.post("/api/demo/seed", json={"client_email": "buyer@example.com"})

    survivors = [
        m for m in client.get("/api/dashboard").json()["milestones"]
        if not m["historical"]
    ]
    assert len(survivors) == 3, "seeding wiped the approved project"


def test_seeding_twice_does_not_stack_history(client):
    first = client.post("/api/demo/seed",
                        json={"client_email": "buyer@example.com"}).json()
    second = client.post("/api/demo/seed",
                         json={"client_email": "buyer@example.com"}).json()
    assert first["history"] == second["history"]
    assert second["history"]["invoices_settled"] == 3


def test_history_is_looked_up_by_client_email(client):
    client.post("/api/demo/seed", json={"client_email": "someone@example.com"})
    from app.main import client_history

    assert client_history("someone@example.com")["invoices_settled"] == 3
    # a client Hito has never billed has no history, and says so
    assert client_history("stranger@example.com") == {
        "invoices_settled": 0, "late_ratio": 0.0, "avg_days_late": 0.0
    }


def test_seed_defaults_to_the_sample_contract_client(client):
    result = client.post("/api/demo/seed", json={}).json()
    assert result["client_email"] == "ap@bluebonnetroasters.example"
    assert result["history"]["invoices_settled"] == 3
    assert result["history"]["late_ratio"] == round(1 / 3, 4)
