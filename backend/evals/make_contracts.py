"""Render the 8 synthetic eval contracts to PDF and write their gold JSON.

Each spec is the ground truth; the clause sentences are written into the PDF verbatim and the gold
citations point at the page they landed on. Run: python -m evals.make_contracts
"""

import io
import json
import re
from pathlib import Path
from typing import Any

import pymupdf

from app.ingest.pdf import page_texts

HERE = Path(__file__).parent
FILLER = (
    "Each party shall keep confidential all non-public information disclosed by the other party "
    "and use it only to perform this Agreement. Neither party may assign this Agreement without "
    "prior written consent. Notices must be in writing and are effective on receipt. This "
    "Agreement is the entire agreement between the parties and supersedes all prior proposals. "
)

SPECS: list[dict[str, Any]] = [
    {
        "slug": "01_northwind_web",
        "title": "Website Redesign Services Agreement",
        "currency": "USD",
        "total": "10000.00",
        "net": 15,
        "deposit": None,
        "auto": None,
        "agency": ("Pixel & Pine Studio", "billing@pixelpine.example"),
        "client": ("Northwind Retail", "ap@northwind.example"),
        "subs": [
            ("Ana Lima", "ana@lima.example", "15"),
            ("Ben Okafor", "ben@okafor.example", "10"),
        ],
        "milestones": [
            (
                "Discovery and design system",
                "Figma design system and page wireframes",
                "4000.00",
                "2026-11-06",
                ["Figma file shared with client", "Covers home, product and checkout pages"],
            ),
            (
                "Storefront build",
                "Responsive storefront deployed to staging",
                "3500.00",
                "2026-11-27",
                ["Staging URL live", "Lighthouse performance score of at least 85"],
            ),
            (
                "Launch and QA",
                "Production launch with QA report",
                "2500.00",
                "2026-12-18",
                ["Site live on production domain", "QA report with zero open critical bugs"],
            ),
        ],
        "late": {"type": "pct_monthly", "value": "1.5", "grace": 5, "cap": "500.00"},
        "dispute": True,
    },
    {
        "slug": "02_eur_fixed_fee",
        "title": "Brand Identity Agreement",
        "currency": "EUR",
        "total": "6000.00",
        "net": 30,
        "deposit": None,
        "auto": None,
        "agency": ("Studio Kanal", "rechnung@kanal.example"),
        "client": ("Baumhaus GmbH", "finance@baumhaus.example"),
        "subs": [],
        "milestones": [
            (
                "Logo concepts",
                "Three logo concepts",
                "2500.00",
                "2026-11-15",
                ["Three distinct concepts delivered as PDF"],
            ),
            (
                "Brand guidelines",
                "Final logo and brand guideline PDF",
                "3500.00",
                "2026-12-15",
                ["Vector logo files", "Guideline PDF of at least 20 pages"],
            ),
        ],
        "late": {"type": "fixed", "value": "50.00", "grace": 10, "cap": None},
        "dispute": False,
    },
    {
        "slug": "03_gbp_flat_pct",
        "title": "Mobile App Development Agreement",
        "currency": "GBP",
        "total": "20000.00",
        "net": 14,
        "deposit": None,
        "auto": None,
        "agency": ("Hedgerow Apps Ltd", "accounts@hedgerow.example"),
        "client": ("Thames Fitness", "payables@thamesfit.example"),
        "subs": [("Priya Shah", "priya@shah.example", "25")],
        "milestones": [
            (
                "Prototype",
                "Clickable prototype",
                "4000.00",
                "2026-11-10",
                ["Prototype link shared"],
            ),
            (
                "Alpha",
                "Alpha build on TestFlight",
                "6000.00",
                "2026-12-10",
                ["TestFlight build available"],
            ),
            (
                "Beta",
                "Beta with payments",
                "5000.00",
                "2027-01-15",
                ["In-app payments working in test mode"],
            ),
            (
                "Release",
                "App store release",
                "5000.00",
                "2027-02-15",
                ["App approved on both stores"],
            ),
        ],
        "late": {"type": "pct_flat", "value": "5", "grace": 0, "cap": None},
        "dispute": True,
    },
    {
        "slug": "04_deemed_acceptance",
        "title": "Data Pipeline Consulting Agreement",
        "currency": "USD",
        "total": "15000.00",
        "net": 30,
        "deposit": None,
        "auto": 7,
        "agency": ("Riverbend Data", "ar@riverbend.example"),
        "client": ("Cobalt Logistics", "ap@cobalt.example"),
        "subs": [],
        "milestones": [
            ("Audit", "Current-state audit", "2000.00", "2026-11-01", ["Audit report delivered"]),
            (
                "Design",
                "Target architecture",
                "3000.00",
                "2026-11-20",
                ["Architecture document approved"],
            ),
            ("Ingest", "Ingestion jobs", "4000.00", "2026-12-10", ["Jobs running daily"]),
            ("Dashboards", "Ops dashboards", "3000.00", "2027-01-10", ["Five dashboards live"]),
            (
                "Handover",
                "Docs and training",
                "3000.00",
                "2027-01-31",
                ["Two training sessions held"],
            ),
        ],
        "late": {"type": "none", "value": "0", "grace": 0, "cap": None},
        "dispute": False,
    },
    {
        "slug": "05_eur_deposit",
        "title": "E-commerce Migration Agreement",
        "currency": "EUR",
        "total": "12000.00",
        "net": 21,
        "deposit": "2000.00",
        "auto": None,
        "agency": ("Nordlicht Digital", "billing@nordlicht.example"),
        "client": ("Alpenmode AG", "kreditoren@alpenmode.example"),
        "subs": [("Lukas Brandt", "lukas@brandt.example", "20")],
        "milestones": [
            (
                "Catalog migration",
                "All products migrated",
                "3000.00",
                "2026-11-20",
                ["All SKUs imported"],
            ),
            ("Checkout", "Checkout and payments", "3500.00", "2026-12-20", ["Test orders succeed"]),
            (
                "Go-live",
                "Production cutover",
                "3500.00",
                "2027-01-20",
                ["DNS switched", "No P1 incidents for 7 days"],
            ),
        ],
        "late": {"type": "pct_monthly", "value": "1", "grace": 7, "cap": "300.00"},
        "dispute": True,
    },
    {
        "slug": "06_inconsistent_total",
        "title": "Marketing Site Agreement",
        "currency": "USD",
        "total": "10000.00",
        "net": 15,
        "deposit": None,
        "auto": None,
        "agency": ("Lantern Creative", "money@lantern.example"),
        "client": ("Sable Coffee", "ap@sable.example"),
        "subs": [],
        "milestones": [
            ("Copy and design", "Homepage design", "3000.00", "2026-11-05", ["Design approved"]),
            ("Build", "Site build", "3000.00", "2026-11-25", ["Staging live"]),
            ("Launch", "Launch", "3000.00", "2026-12-10", ["Production live"]),
        ],
        "late": {"type": "fixed", "value": "75.00", "grace": 3, "cap": None},
        "dispute": False,
    },
    {
        "slug": "07_gbp_monthly_nocap",
        "title": "Video Production Agreement",
        "currency": "GBP",
        "total": "8000.00",
        "net": 10,
        "deposit": None,
        "auto": None,
        "agency": ("Kestrel Films", "accounts@kestrel.example"),
        "client": ("Moorland Outdoor", "finance@moorland.example"),
        "subs": [("Tom Reyes", "tom@reyes.example", "30")],
        "milestones": [
            ("Shoot", "Two shoot days", "5000.00", "2026-11-12", ["Raw footage delivered"]),
            (
                "Edit",
                "Final 90s edit",
                "3000.00",
                "2026-12-01",
                ["Final cut approved", "Captions included"],
            ),
        ],
        "late": {"type": "pct_monthly", "value": "2", "grace": 0, "cap": None},
        "dispute": True,
    },
    {
        "slug": "08_usd_two_subs_auto",
        "title": "SaaS Onboarding Agreement",
        "currency": "USD",
        "total": "9000.00",
        "net": 20,
        "deposit": None,
        "auto": 10,
        "agency": ("Copperleaf Labs", "ar@copperleaf.example"),
        "client": ("Juniper Health", "vendors@juniper.example"),
        "subs": [
            ("Mia Chen", "mia@chen.example", "12.5"),
            ("Raj Patel", "raj@patel.example", "7.5"),
        ],
        "milestones": [
            ("Setup", "Tenant setup", "2000.00", "2026-11-03", ["Tenant provisioned"]),
            ("Integrations", "EHR integration", "4000.00", "2026-12-01", ["HL7 feed live"]),
            ("Training", "Staff training", "3000.00", "2026-12-15", ["Three sessions delivered"]),
        ],
        "late": {"type": "fixed", "value": "100.00", "grace": 5, "cap": None},
        "dispute": False,
    },
]


def _money(cur: str, v: str) -> str:
    return f"{cur} {float(v):,.2f}"


def clauses(s: dict[str, Any]) -> dict[str, str]:
    """Keyed sentences that go verbatim into the PDF (keys used to build gold cites)."""
    cur = s["currency"]
    c = {
        "agency": f'{s["agency"][0]} (the "Agency", {s["agency"][1]}) will provide the services.',
        "client": f'{s["client"][0]} (the "Client", {s["client"][1]}) engages the Agency.',
        "total": f"The total fee for the services is {_money(cur, s['total'])}.",
        "net": f"Each invoice is payable within {s['net']} days of the invoice date.",
    }
    for i, (title, deliv, amt, due, crit) in enumerate(s["milestones"], 1):
        c[f"m{i}"] = (
            f"Milestone {i} - {title}: {deliv}, fee {_money(cur, amt)}, due {due}. "
            f"Acceptance criteria: {'; '.join(crit)}."
        )
    for i, (name, email, pct) in enumerate(s["subs"], 1):
        c[f"s{i}"] = (
            f"Subcontractor {name} ({email}) shall receive {pct}% of each milestone payment "
            "received by the Agency."
        )
    lt = s["late"]
    if lt["type"] == "pct_monthly":
        c["late"] = (
            f"Overdue amounts accrue a late fee of {lt['value']}% per month after a grace period of "
            f"{lt['grace']} days"
            + (f", capped at {_money(cur, lt['cap'])} per invoice." if lt["cap"] else ".")
        )
    elif lt["type"] == "pct_flat":
        c["late"] = (
            f"Invoices not paid within {lt['grace']} days after the due date incur a one-time late fee of {lt['value']}% of the invoice amount."
        )
    elif lt["type"] == "fixed":
        c["late"] = (
            f"A fixed late fee of {_money(cur, lt['value'])} applies to any invoice unpaid {lt['grace']} days after its due date."
        )
    if s["deposit"]:
        c["deposit"] = (
            f"A non-refundable deposit of {_money(cur, s['deposit'])} is due on signature."
        )
    if s["auto"]:
        c["auto"] = (
            f"A milestone is deemed accepted if the Client raises no written objection within {s['auto']} days of delivery."
        )
    if s["dispute"]:
        c["dispute"] = (
            "Any billing dispute must be raised in writing within 10 days of the invoice date, citing the milestone concerned."
        )
    return c


def build_html(s: dict[str, Any], c: dict[str, str]) -> str:
    def p(*keys: str) -> str:
        return "".join(f"<p>{c[k]}</p>" for k in keys if k in c)

    subs = [k for k in c if re.fullmatch(r"s\d+", k)]
    ms = [k for k in c if re.fullmatch(r"m\d+", k)]
    return (
        f"<h1>{s['title']}</h1><p>1. Parties</p>{p('agency', 'client')}"
        f"<p>2. General Terms</p>"
        + "".join(f"<p>2.{i} {FILLER}</p>" for i in range(1, 9))
        + f"<p>3. Fees</p>{p('total', 'deposit')}"
        + f"<p>4. Milestones</p>{p(*ms)}{p('auto')}"
        + f"<p>5. Payment Terms</p>{p('net', 'late')}"
        + (f"<p>6. Subcontractors</p>{p(*subs)}" if subs else "")
        + (f"<p>7. Disputes</p>{p('dispute')}" if "dispute" in c else "")
        + "<p>8. Signatures</p><p>Signed by both parties on 2026-10-01.</p>"
    )


def render_pdf(html: str) -> bytes:
    story = pymupdf.Story(
        html=html, user_css="body{font-family:sans-serif;font-size:11pt} h1{font-size:16pt}"
    )
    rect = pymupdf.paper_rect("letter")
    where = rect + (54, 54, -54, -54)
    out = io.BytesIO()
    writer = pymupdf.DocumentWriter(out)
    more = True
    while more:
        dev = writer.begin_page(rect)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return out.getvalue()


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def cite(pages: list[str], quote: str) -> dict[str, Any]:
    q = _norm(quote)[:300]
    for i, t in enumerate(pages, 1):
        if q[:60] in _norm(t):
            return {"page": i, "quote": q, "confidence": 1.0}
    raise ValueError(f"quote not found: {q[:60]}")


def gold(s: dict[str, Any], c: dict[str, str], pages: list[str]) -> dict[str, Any]:
    parties = [
        {
            "role": "agency",
            "name": s["agency"][0],
            "email": s["agency"][1],
            "share_pct": None,
            "cite": cite(pages, c["agency"]),
        },
        {
            "role": "client",
            "name": s["client"][0],
            "email": s["client"][1],
            "share_pct": None,
            "cite": cite(pages, c["client"]),
        },
    ] + [
        {
            "role": "subcontractor",
            "name": n,
            "email": e,
            "share_pct": pct,
            "cite": cite(pages, c[f"s{i}"]),
        }
        for i, (n, e, pct) in enumerate(s["subs"], 1)
    ]
    lt = s["late"]
    return {
        "title": s["title"],
        "currency": s["currency"],
        "total_amount": s["total"],
        "total_cite": cite(pages, c["total"]),
        "parties": parties,
        "milestones": [
            {
                "seq": i,
                "title": t,
                "deliverable": d,
                "acceptance_criteria": cr,
                "amount": a,
                "due_date": due,
                "cite": cite(pages, c[f"m{i}"]),
            }
            for i, (t, d, a, due, cr) in enumerate(s["milestones"], 1)
        ],
        "net_days": s["net"],
        "net_days_cite": cite(pages, c["net"]),
        "late_fee": {
            "type": lt["type"],
            "value": lt["value"],
            "grace_days": lt["grace"],
            "cap": lt["cap"],
            "cite": cite(pages, c["late"]) if "late" in c else None,
        },
        "deposit_amount": s["deposit"],
        "auto_accept_days": s["auto"],
        "auto_accept_cite": cite(pages, c["auto"]) if "auto" in c else None,
        "dispute_clause": cite(pages, c["dispute"]) if "dispute" in c else None,
    }


def main() -> None:
    (HERE / "contracts").mkdir(exist_ok=True)
    (HERE / "gold").mkdir(exist_ok=True)
    for s in SPECS:
        c = clauses(s)
        pdf = render_pdf(build_html(s, c))
        (HERE / "contracts" / f"{s['slug']}.pdf").write_bytes(pdf)
        g = gold(s, c, page_texts(pdf))
        (HERE / "gold" / f"{s['slug']}.json").write_text(json.dumps(g, indent=2))
        print(s["slug"], "pages:", len(page_texts(pdf)))


if __name__ == "__main__":
    main()
