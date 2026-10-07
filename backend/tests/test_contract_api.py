from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PDFS, gold, ok_verdicts

api = TestClient(app)


def _upload(slug: str) -> int:
    with open(PDFS / f"{slug}.pdf", "rb") as f:
        r = api.post("/contracts", files={"file": (f"{slug}.pdf", f, "application/pdf")})
    assert r.status_code == 201, r.text
    assert r.json()["pages"] == 2 and "pdf" not in r.json()
    return int(r.json()["id"])


def test_full_review_flow(db, llm) -> None:  # type: ignore[no-untyped-def]
    llm.on("ContractExtraction", gold("06_inconsistent_total"))
    llm.on("CheckBatch", ok_verdicts)
    cid = _upload("06_inconsistent_total")

    r = api.post(f"/contracts/{cid}/extract")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "review" and body["open_flags"] == 1
    assert {f["path"] for f in body["fields"] if f["flagged"]} == {"total_amount"}

    assert api.post(f"/contracts/{cid}/approve", json={"approved_by": "me"}).status_code == 409

    r = api.patch(f"/contracts/{cid}/fields/total_amount", json={"value": "9000.00"})
    assert r.status_code == 200 and r.json()["flagged"] is False

    r = api.post(f"/contracts/{cid}/approve", json={"approved_by": "me"})
    assert r.status_code == 200, r.text
    detail = api.get(f"/contracts/{cid}").json()
    assert detail["status"] == "approved" and detail["mandate"]["approved_by"] == "me"
    assert [m["amount"] for m in detail["milestones"]] == ["3000.00"] * 3
    assert detail["parties"][1]["paypal_email"] == "client@test.example"

    # frozen after approval
    assert api.patch(f"/contracts/{cid}/fields/net_days", json={"value": 99}).status_code == 409
    assert api.get(f"/contracts/{cid}/pdf").content.startswith(b"%PDF")
    assert "Marketing Site Agreement" in api.get(f"/contracts/{cid}/pages/1").json()["text"]


def test_rejects_non_pdf(db) -> None:  # type: ignore[no-untyped-def]
    r = api.post("/contracts", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert r.status_code == 415


def test_unknown_contract_404(db) -> None:  # type: ignore[no-untyped-def]
    assert api.get("/contracts/999").status_code == 404
