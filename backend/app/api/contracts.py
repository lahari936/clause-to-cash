from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

from app.api.serialize import row
from app.db.models import Clause, Contract, Mandate, Milestone, Party, PaymentTerms
from app.db.session import get_db
from app.services import contracts as svc

router = APIRouter(prefix="/contracts", tags=["contracts"])
MAX_PDF = 15 * 1024 * 1024


def get_contract(db: Session, contract_id: int) -> Contract:
    c = db.get(Contract, contract_id)
    if c is None:
        raise HTTPException(404, "contract not found")
    return c


@router.get("")
def list_contracts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [row(c) for c in db.scalars(select(Contract).order_by(Contract.id.desc()))]


@router.post("", status_code=201)
def upload(
    file: UploadFile = File(...), title: str = Form(""), db: Session = Depends(get_db)
) -> dict[str, Any]:
    data = file.file.read(MAX_PDF + 1)
    if len(data) > MAX_PDF:
        raise HTTPException(413, "PDF too large (15 MB max)")
    if not data.startswith(b"%PDF"):
        raise HTTPException(415, "upload a PDF")
    try:
        c = svc.upload(db, title or (file.filename or "Contract").removesuffix(".pdf"), data)
    except svc.ReviewError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        raise HTTPException(422, "could not read PDF") from e
    db.commit()
    return row(c, pages=len(c.pages_json))


@router.get("/{contract_id}")
def detail(contract_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = get_contract(db, contract_id)
    fs = svc.fields(db, c.id)
    mandate = db.scalar(select(Mandate).where(Mandate.contract_id == c.id))
    by = Milestone.contract_id == c.id
    return row(
        c,
        pages=len(c.pages_json),
        fields=[row(f, flagged=svc.is_flagged(f)) for f in fs],
        open_flags=sum(svc.is_flagged(f) for f in fs),
        mandate=row(mandate) if mandate else None,
        milestones=[
            row(m) for m in db.scalars(select(Milestone).where(by).order_by(Milestone.seq))
        ],
        parties=[row(p) for p in db.scalars(select(Party).where(Party.contract_id == c.id))],
        payment_terms=row(t) if (t := db.get(PaymentTerms, c.id)) else None,
        clauses=[row(cl) for cl in db.scalars(select(Clause).where(Clause.contract_id == c.id))],
    )


@router.get("/{contract_id}/pdf")
def pdf(contract_id: int, db: Session = Depends(get_db)) -> Response:
    c = db.scalar(select(Contract).where(Contract.id == contract_id).options(undefer(Contract.pdf)))
    if c is None:
        raise HTTPException(404, "contract not found")
    return Response(c.pdf, media_type="application/pdf")


@router.get("/{contract_id}/pages/{page}")
def page_text(contract_id: int, page: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = get_contract(db, contract_id)
    if not 1 <= page <= len(c.pages_json):
        raise HTTPException(404, "no such page")
    return {"page": page, "text": c.pages_json[page - 1]}


@router.post("/{contract_id}/extract")
def extract(contract_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = get_contract(db, contract_id)
    if c.status == "approved":
        raise HTTPException(409, "already approved")
    try:
        svc.run_extraction(db, c)
    except Exception as e:
        raise HTTPException(502, f"extraction failed: {e}") from e
    db.commit()
    return detail(contract_id, db)


class Override(BaseModel):
    value: Any


@router.patch("/{contract_id}/fields/{path}")
def override(
    contract_id: int, path: str, body: Override, db: Session = Depends(get_db)
) -> dict[str, Any]:
    c = get_contract(db, contract_id)
    try:
        f = svc.override(db, c, path, body.value)
    except svc.ReviewError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return row(f, flagged=svc.is_flagged(f))


class Approve(BaseModel):
    approved_by: str
    approval_threshold: Decimal | None = None
    paypal_emails: dict[int, str] | None = None  # party index -> sandbox email


@router.post("/{contract_id}/approve")
def approve(contract_id: int, body: Approve, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = get_contract(db, contract_id)
    try:
        m = svc.approve(db, c, body.approved_by, body.approval_threshold, body.paypal_emails)
    except svc.ReviewError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return row(m)
