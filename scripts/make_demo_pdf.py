"""Build data/contract_laura_bluebonnet.pdf - the sample contract for the demo.

Writes a real, multi-page PDF with a text layer (base-14 Helvetica, no external
library) so that `pypdf` extracts it the same way it would extract a contract a
freelancer actually received by email.

The contract is deliberately imperfect: the late-payment clause is vague, the
acceptance window is only defined for one deliverable, and revisions are
unbounded. Those are the things the contract-reading agent is supposed to flag
as warnings rather than silently accept.
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "contract_laura_bluebonnet.pdf"

TITLE = "BRAND IDENTITY SERVICES AGREEMENT"

BODY = """
This Agreement is made on September 22, 2026 between:

Client: Bluebonnet Coffee Roasters LLC
Address: 1104 E 6th Street, Austin, Texas 78702, United States
Billing contact: Dana Whitfield, ap@bluebonnetroasters.example

Designer: Laura Restrepo, independent brand designer
Address: Carrera 43A # 18-20, El Poblado, Medellin, Colombia
Contact: laura@hito.studio

1. SCOPE OF WORK

The Designer will develop a complete brand identity for the Client's retail
coffee business, consisting of three deliverables set out in Section 2. The
Designer may engage subcontractors to complete portions of the work and remains
the Client's single point of contact.

2. DELIVERABLES AND FEES

The total fee for the engagement is US$9,000 (nine thousand United States
dollars), invoiced in three parts against delivery of each milestone:

Milestone 1 - Logo and primary marks: US$3,000, due on October 10, 2026.
Includes the primary logotype, one secondary mark, and the colour palette,
delivered as vector files.

Milestone 2 - Website design and build: US$3,000, due on October 28, 2026.
Includes a five-page responsive marketing site and handover of the source files.

Milestone 3 - Brand manual: US$3,000, due on November 25, 2026. Includes a
written manual covering logo usage, typography, colour and photography
direction. The Client shall review the manual and confirm acceptance within ten
(10) business days of delivery; payment for this milestone falls due on that
confirmation.

Each invoice is issued through PayPal upon delivery of the corresponding
milestone and is payable within fifteen (15) days of issue.

3. REVISIONS

The Client may request revisions to each deliverable. The Designer will
accommodate reasonable revision requests.

4. LATE PAYMENT

Invoices not settled by their due date may be subject to a late charge, and the
Designer may suspend work on remaining milestones until outstanding amounts are
settled.

5. COLLABORATORS AND REVENUE SHARE

The Designer works with the following collaborators on this engagement, who are
paid out of each milestone payment as it is received:

Andres Villa - developer - andres.villa@example.dev - 30% of each payment
Mariana Soto - illustrator - mariana.soto@example.art - 20% of each payment

The Designer is solely responsible for paying these collaborators and the Client
has no direct obligation to them.

6. INTELLECTUAL PROPERTY

Upon delivery of each milestone, the Client receives a licence to use the
delivered materials. Full assignment of rights in all deliverables transfers to
the Client on delivery of Milestone 3.

7. GOVERNING LAW

This Agreement is governed by the laws of the State of Texas. The parties will
attempt to resolve any dispute in good faith before pursuing other remedies.

8. SIGNATURES

Signed for the Client: Dana Whitfield, Operations Director
Signed by the Designer: Laura Restrepo

Date: September 22, 2026
"""

PAGE_WIDTH, PAGE_HEIGHT = 612, 792
MARGIN_X, TOP_Y = 64, 740
LEADING = 14.2
LINES_PER_PAGE = int((TOP_Y - 60) / LEADING)
MAX_CHARS = 88


def wrap(text: str, width: int = MAX_CHARS) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            lines.append("")
            continue
        current = ""
        for word in stripped.split():
            candidate = f"{current} {word}".strip()
            if len(candidate) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def escape(text: str) -> str:
    return (text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            .encode("latin-1", "replace").decode("latin-1"))


def content_stream(lines: list[str], *, heading: str | None = None) -> bytes:
    parts = ["BT", f"1 0 0 1 {MARGIN_X} {TOP_Y} Tm", f"{LEADING} TL"]
    if heading:
        parts += ["/F2 14 Tf", f"({escape(heading)}) Tj", "T*", "T*", "/F1 9.5 Tf"]
    else:
        parts.append("/F1 9.5 Tf")
    for line in lines:
        bold = line[:2].isdigit() and line[1:2] == "." or (
            line.isupper() and len(line) > 4 and not line.startswith("US$")
        )
        if line.startswith("Milestone") or bold:
            parts += ["/F2 9.5 Tf", f"({escape(line)}) Tj", "T*", "/F1 9.5 Tf"]
        else:
            parts += [f"({escape(line)}) Tj", "T*"]
    parts.append("ET")
    return "\n".join(parts).encode("latin-1")


def build_pdf(pages: list[bytes]) -> bytes:
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font_regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                       b"/Encoding /WinAnsiEncoding >>")
    font_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                    b"/Encoding /WinAnsiEncoding >>")
    pages_ref = add(b"")  # placeholder, filled once page ids are known

    page_ids = []
    for stream in pages:
        content_id = add(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
            + stream + b"\nendstream"
        )
        page_id = add(
            f"<< /Type /Page /Parent {pages_ref} 0 R "
            f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> >> "
            f"/Contents {content_id} 0 R >>".encode()
        )
        page_ids.append(page_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_ref - 1] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
    )
    catalog_id = add(f"<< /Type /Catalog /Pages {pages_ref} 0 R >>".encode())
    info_id = add(
        b"<< /Title (Brand Identity Services Agreement) "
        b"/Author (Bluebonnet Coffee Roasters LLC) /Producer (Hito demo generator) >>"
    )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R "
        f"/Info {info_id} 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def main() -> None:
    lines = wrap(BODY)
    pages, first = [], True
    while lines:
        budget = LINES_PER_PAGE - (3 if first else 0)
        chunk, lines = lines[:budget], lines[budget:]
        pages.append(content_stream(chunk, heading=TITLE if first else None))
        first = False

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build_pdf(pages))
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes, {len(pages)} pages)")


if __name__ == "__main__":
    main()
