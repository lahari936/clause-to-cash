from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import Contract
from app.db.session import get_db
from app.services import copilot

router = APIRouter(prefix="/copilot", tags=["copilot"])


class Ask(BaseModel):
    contract_id: int
    message: str = Field(max_length=4000)


@router.post("")
def ask(body: Ask, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(Contract, body.contract_id)
    if c is None or c.status != "approved":
        raise HTTPException(409, "copilot needs an approved contract")
    try:
        out = copilot.chat(db, c, body.message)
    except Exception as e:
        db.rollback()  # never keep a half-done money action
        raise HTTPException(502, f"copilot failed: {e}") from e
    db.commit()
    return out
