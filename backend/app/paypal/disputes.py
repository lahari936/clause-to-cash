from app.paypal.client import JSON, PayPalClient


def get(pp: PayPalClient, dispute_id: str) -> JSON:
    return pp.get(f"/v1/customer/disputes/{dispute_id}")


def provide_evidence(
    pp: PayPalClient, request_id: str, dispute_id: str, pdf: bytes, notes: str
) -> JSON:
    import json

    meta = {"evidences": [{"evidence_type": "PROOF_OF_FULFILLMENT", "notes": notes[:2000]}]}
    return pp.post_multipart(
        f"/v1/customer/disputes/{dispute_id}/provide-evidence",
        request_id,
        {
            "input": ("input.json", json.dumps(meta).encode(), "application/json"),
            "file1": ("evidence.pdf", pdf, "application/pdf"),
        },
    )
