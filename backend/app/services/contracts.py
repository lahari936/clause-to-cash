import hashlib
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents import checker, extractor
from app.agents.validators import validate
from app.config import get_settings
from app.db.models import (
    Clause,
    Contract,
    ExtractionField,
    Mandate,
    Milestone,
    Party,
    PaymentTerms,
)
from app.ingest.pdf import page_texts
from app.schemas.extraction import Cited, ContractExtraction

MIN_CONFIDENCE = 0.7


class ReviewError(Exception):
    pass


def upload(db: Session, title: str, pdf: bytes) -> Contract:
    pages = page_texts(pdf)
    if not any(p.strip() for p in pages):
        raise ReviewError("PDF has no extractable text (scanned PDFs are not supported)")
    sha = hashlib.sha256(pdf).hexdigest()
    c = Contract(title=title, file_key=f"db:{sha}", sha256=sha, pdf=pdf, pages_json=pages)
    db.add(c)
    db.flush()
    return c


def store_extraction(
    db: Session,
    c: Contract,
    x: ContractExtraction,
    flags: dict[str, str],
    verdicts: dict[str, checker.CheckResult],
) -> None:
    db.execute(delete(ExtractionField).where(ExtractionField.contract_id == c.id))
    data = x.model_dump(mode="json")
    seen = set()
    for it in extractor.field_items(x):
        seen.add(it.path)
        v = verdicts.get(it.path)
        verdict = v.verdict if v else ("ok" if it.value is None else "unsupported")
        reason = v.reason if v else ("nothing claimed" if it.value is None else "no citation")
        if it.path in flags:
            verdict, reason = "wrong", f"validator: {flags[it.path]}; checker: {reason}"
        db.add(
            ExtractionField(
                contract_id=c.id,
                path=it.path,
                value_json=it.value,
                confidence=it.cite.confidence if it.cite else 1.0,
                checker_verdict=verdict,
                checker_reason=reason,
            )
        )
    for path, problem in flags.items():  # validator flags on paths that aren't single fields
        if path not in seen:
            db.add(
                ExtractionField(
                    contract_id=c.id,
                    path=path,
                    value_json=data.get(path),
                    confidence=1.0,
                    checker_verdict="wrong",
                    checker_reason=f"validator: {problem}",
                )
            )
    c.extraction_json = data
    c.currency = x.currency
    c.total_amount = x.total_amount
    c.status = "review"


def run_extraction(db: Session, c: Contract) -> None:
    pages = c.pages_json
    x = extractor.extract(pages)
    flags = validate(x, pages)
    verdicts = checker.check(extractor.field_items(x), pages)
    store_extraction(db, c, x, flags, verdicts)


def is_flagged(f: ExtractionField) -> bool:
    return f.user_override_json is None and (
        f.checker_verdict != "ok" or f.confidence < MIN_CONFIDENCE
    )


def fields(db: Session, contract_id: int) -> list[ExtractionField]:
    return list(
        db.scalars(
            select(ExtractionField)
            .where(ExtractionField.contract_id == contract_id)
            .order_by(ExtractionField.id)
        )
    )


def override(db: Session, c: Contract, path: str, value: Any) -> ExtractionField:
    """Human review: set (or confirm) a field's value. Confirming clears its flag."""
    f = db.scalar(
        select(ExtractionField).where(
            ExtractionField.contract_id == c.id, ExtractionField.path == path
        )
    )
    if f is None:
        raise ReviewError(f"unknown field {path}")
    if c.status == "approved":
        raise ReviewError("contract already approved; mandate is frozen")
    f.user_override_json = {"value": value}
    return f


def final_extraction(c: Contract, fs: list[ExtractionField]) -> ContractExtraction:
    data: dict[str, Any] = dict(c.extraction_json or {})
    for f in fs:
        if f.user_override_json is not None:
            extractor.apply_override(data, f.path, f.user_override_json["value"])
    return ContractExtraction.model_validate(data)


def _paypal_emails(x: ContractExtraction) -> list[str | None]:
    s = get_settings()
    subs = iter([s.sub_a_email, s.sub_b_email])
    out: list[str | None] = []
    for p in x.parties:
        sandbox = {"agency": s.agency_email, "client": s.client_email}.get(p.role)
        if p.role == "subcontractor":
            sandbox = next(subs, None)
        out.append(sandbox or p.email)
    return out


def approve(
    db: Session,
    c: Contract,
    approved_by: str,
    threshold: Decimal | None = None,
    paypal_emails: dict[int, str] | None = None,
) -> Mandate:
    """Freeze the reviewed terms into the Mandate and materialise parties/milestones/terms."""
    if c.status == "approved":
        raise ReviewError("already approved")
    fs = fields(db, c.id)
    open_flags = [f.path for f in fs if is_flagged(f)]
    if not fs or open_flags:
        raise ReviewError(f"unresolved review flags: {', '.join(open_flags) or 'not extracted'}")
    x = final_extraction(c, fs)
    overridden = {f.path for f in fs if f.user_override_json is not None}
    if still := {k: v for k, v in validate(x, c.pages_json).items() if k not in overridden}:
        raise ReviewError(f"validators still failing: {still}")

    def clause(kind: str, cite: Cited | None) -> Clause | None:
        if cite is None:
            return None
        cl = Clause(contract_id=c.id, kind=kind, page=cite.page, quote=cite.quote[:300])
        db.add(cl)
        return cl

    emails = _paypal_emails(x)
    for i, e in (paypal_emails or {}).items():
        emails[i] = e
    parties = []
    for p, email in zip(x.parties, emails, strict=True):
        clause("party", p.cite)
        parties.append(
            Party(
                contract_id=c.id,
                role=p.role,
                name=p.name,
                email=p.email,
                paypal_email=email,
                share_pct=p.share_pct if p.role == "subcontractor" else None,
            )
        )
    db.add_all(parties)
    for m in x.milestones:
        cl = clause("milestone", m.cite)
        db.flush()
        db.add(
            Milestone(
                contract_id=c.id,
                seq=m.seq,
                title=m.title,
                deliverable=m.deliverable,
                acceptance_criteria=m.acceptance_criteria,
                amount=m.amount,
                due_date=m.due_date,
                clause_id=cl.id if cl else None,
            )
        )
    terms_clauses = [clause("payment_terms", x.net_days_cite), clause("late_fee", x.late_fee.cite)]
    clause("total", x.total_cite)
    clause("auto_accept", x.auto_accept_cite)
    clause("dispute", x.dispute_clause)
    db.flush()
    db.add(
        PaymentTerms(
            contract_id=c.id,
            net_days=x.net_days,
            late_fee_type=x.late_fee.type,
            late_fee_value=x.late_fee.value,
            grace_days=x.late_fee.grace_days,
            late_fee_cap=x.late_fee.cap,
            deposit_amount=x.deposit_amount,
            clause_ids=[cl.id for cl in terms_clauses if cl],
        )
    )
    client = next(p for p in parties if p.role == "client")
    rules = x.model_dump(mode="json") | {
        "client_paypal_email": client.paypal_email,
        "paypal_emails": {p.name: p.paypal_email for p in parties},
    }
    mandate = Mandate(
        contract_id=c.id,
        approved_by=approved_by,
        rules_json=rules,
        approval_threshold=threshold
        if threshold is not None
        else get_settings().approval_threshold,
    )
    db.add(mandate)
    c.status = "approved"
    c.currency = x.currency
    c.total_amount = x.total_amount
    db.flush()
    return mandate
