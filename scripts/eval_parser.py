"""Measure the contract reader, per engine.

A contract reader that is wrong about an amount is worse than no reader at all,
so this is not a vibe check: it runs the parser against contracts whose correct
answer is known and scores field by field.

    python scripts/eval_parser.py                 # whichever engine is active
    python scripts/eval_parser.py --provider ollama --runs 3
    python scripts/eval_parser.py --provider rules

Cases cover what actually varies between the contracts a freelancer receives:
notation (US$3,000 / US$3.000 / 3000 USD), language, date format, and whether
the fee schedule is a list or a paragraph.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.agents import contract_parser, llm  # noqa: E402
from app.config import settings  # noqa: E402

SAMPLE_PDF = ROOT / "data" / "contract_laura_bluebonnet.pdf"

SPANISH = """
CONTRATO DE PRESTACION DE SERVICIOS DE DISENO

Celebrado el 3 de septiembre de 2026 entre:

Cliente: Panaderia La Esquina S.A.S.
Contacto de pagos: Camila Ortiz, pagos@laesquina.example
Direccion: Calle 70 # 52-20, Barranquilla, Colombia

Disenadora: Laura Restrepo, Medellin, Colombia

2. ENTREGABLES Y HONORARIOS

El valor total del contrato es de US$7.500 (siete mil quinientos dolares),
facturados contra la entrega de cada hito:

Entrega 1 - Identidad visual: US$2.500, con fecha 20 de septiembre de 2026.
Entrega 2 - Empaques para linea de panaderia: US$3.000, con fecha 18 de
octubre de 2026.
Entrega 3 - Manual de marca y senaletica: US$2.000, con fecha 15 de noviembre
de 2026.

Cada factura se emite por PayPal y es pagadera dentro de los quince (15) dias
siguientes a su emision.

5. COLABORADORES

Sofia Henao - ilustradora - sofia.henao@example.art - 25% de cada pago
Julian Mejia - fotografo - julian.mejia@example.photo - 15% de cada pago
"""

PROSE = """
LETTER OF ENGAGEMENT

Dated 1 October 2026.

This letter confirms that Northwind Analytics Ltd (billing: finance@northwind.example,
registered in Leeds, United Kingdom) has engaged Laura Restrepo to deliver a
rebrand for a total fee of 6,000 USD.

The fee is payable in two equal instalments of 3000 USD. The first falls due on
delivery of the logo suite, which we have agreed for 20 October 2026. The second
falls due on delivery of the full design system, agreed for 24 November 2026.

Laura will be assisted by Tomas Pardo (motion designer, tomas.pardo@example.studio),
who receives 20% of each instalment.

Either party may terminate on fourteen days notice.
"""

CASES = [
    {
        "name": "sample contract (PDF, list format, US$3,000)",
        "source": "pdf",
        "expect": {
            "total": 9000.0,
            "amounts": [3000.0, 3000.0, 3000.0],
            "dates": ["2026-10-10", "2026-10-28", "2026-11-25"],
            "client_email": "ap@bluebonnetroasters.example",
            "shares": {30.0, 20.0},
            "currency": "USD",
        },
    },
    {
        "name": "spanish contract (US$3.000 notation, dates in words)",
        "source": SPANISH,
        "expect": {
            "total": 7500.0,
            "amounts": [2500.0, 3000.0, 2000.0],
            "dates": ["2026-09-20", "2026-10-18", "2026-11-15"],
            "client_email": "pagos@laesquina.example",
            "shares": {25.0, 15.0},
            "currency": "USD",
        },
    },
    {
        "name": "prose contract (no list, amounts in a sentence)",
        "source": PROSE,
        "expect": {
            "total": 6000.0,
            "amounts": [3000.0, 3000.0],
            "dates": ["2026-10-20", "2026-11-24"],
            "client_email": "finance@northwind.example",
            "shares": {20.0},
            "currency": "USD",
        },
    },
]


def load(case: dict) -> tuple[str, str]:
    if case["source"] == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(SAMPLE_PDF)
        return "\n".join(p.extract_text() or "" for p in reader.pages), SAMPLE_PDF.name
    return case["source"], "contract.txt"


def score(plan: dict, expect: dict) -> dict:
    amounts = [m["amount"] for m in plan["milestones"]]
    dates = [m["due_date"] for m in plan["milestones"]]
    shares = {c["pct"] for c in plan["collaborators"]}
    quoted = sum(1 for m in plan["milestones"] if m.get("contract_quote"))
    return {
        "milestone count": len(amounts) == len(expect["amounts"]),
        "amounts": sorted(amounts) == sorted(expect["amounts"]),
        "total": abs(plan["total_amount"] - expect["total"]) < 0.01,
        "due dates": sorted(d for d in dates) == sorted(expect["dates"]),
        "client email": plan["client_email"].lower() == expect["client_email"],
        "collaborator shares": shares == expect["shares"],
        "currency": plan["currency"] == expect["currency"],
        "quotes every milestone": quoted == len(amounts) and quoted > 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["auto", "ollama", "claude", "rules"],
                        default="auto")
    parser.add_argument("--runs", type=int, default=1,
                        help="repeat each case, to see how stable the model is")
    args = parser.parse_args()

    settings.llm_provider = args.provider
    engine = llm.status()
    print(f"engine: {engine['label']}  ({engine['provider']})")
    if engine["detail"]:
        print(f"        {engine['detail']}")
    print()

    totals = {"checks": 0, "passed": 0}
    latencies: list[float] = []

    for case in CASES:
        text, filename = load(case)
        print(f"- {case['name']}")
        case_results: list[dict] = []
        for run in range(args.runs):
            started = time.time()
            plan = contract_parser.parse(text, filename=filename)
            latencies.append(time.time() - started)
            meta = plan.get("_meta", {})
            results = score(plan, case["expect"])
            case_results.append(results)
            passed = sum(results.values())
            totals["checks"] += len(results)
            totals["passed"] += passed
            run_label = f" run {run + 1}" if args.runs > 1 else ""
            print(f"    {passed}/{len(results)} checks{run_label} "
                  f"| {meta.get('engine')}  |  {meta.get('latency_ms')} ms "
                  f"| {meta.get('output_tokens')} out")
            for check, ok in results.items():
                if not ok:
                    print(f"      MISS  {check}")
        if args.runs > 1:
            unstable = [
                check for check in case_results[0]
                if len({r[check] for r in case_results}) > 1
            ]
            if unstable:
                print(f"      unstable across runs: {', '.join(unstable)}")
        print()

    pct = 100 * totals["passed"] / max(totals["checks"], 1)
    print(f"score: {totals['passed']}/{totals['checks']} checks ({pct:.0f}%)")
    if latencies:
        print(f"latency: median {statistics.median(latencies):.1f}s "
              f"| slowest {max(latencies):.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
