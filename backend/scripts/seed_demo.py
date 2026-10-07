"""Load the Northwind demo contract end to end: upload -> extract -> check -> approve.

python scripts/seed_demo.py            # live extraction via the configured LLM
python scripts/seed_demo.py --offline  # use the hand-checked gold JSON (no LLM quota needed)
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.agents import checker  # noqa: E402
from app.agents.extractor import field_items  # noqa: E402
from app.db.models import Contract  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.schemas.extraction import ContractExtraction  # noqa: E402
from app.services import contracts  # noqa: E402

SLUG = "01_northwind_web"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--reset", action="store_true", help="seed a fresh copy even if one exists")
    a = ap.parse_args()
    pdf = (ROOT / "evals" / "contracts" / f"{SLUG}.pdf").read_bytes()
    with SessionLocal() as db:
        existing = db.scalar(
            select(Contract).where(
                Contract.title == "Northwind Website Redesign", Contract.status == "approved"
            )
        )
        if existing and not a.reset:
            print(f"demo contract already seeded: id={existing.id}")
            return
        c = contracts.upload(db, "Northwind Website Redesign", pdf)
        if a.offline:
            x = ContractExtraction.model_validate(
                json.loads((ROOT / "evals" / "gold" / f"{SLUG}.json").read_text())
            )
            ok = {
                it.path: checker.CheckResult(path=it.path, verdict="ok", reason="gold")
                for it in field_items(x)
                if it.value is not None
            }
            contracts.store_extraction(db, c, x, {}, ok)
        else:
            contracts.run_extraction(db, c)
        flagged = [f.path for f in contracts.fields(db, c.id) if contracts.is_flagged(f)]
        if flagged:
            db.commit()
            print(f"contract {c.id} extracted with review flags {flagged}; resolve them in the UI")
            return
        m = contracts.approve(db, c, "seed_demo")
        db.commit()
        print(
            f"demo contract id={c.id} approved; mandate id={m.id}; "
            f"parties -> {m.rules_json['paypal_emails']}"
        )


if __name__ == "__main__":
    main()
