from pydantic import BaseModel

from app.llm.provider import structured

PROMPT = """You review a freelancer's delivery against the contract's acceptance criteria for one
milestone. Judge each criterion only from the evidence given (notes, links, PR text). A criterion
with no evidence is a gap. Do not assume work exists that the evidence does not mention.
`summary_for_client` is 2-4 polite sentences the client can read: what was delivered and how it
maps to each criterion."""


class AcceptanceResult(BaseModel):
    meets_criteria: bool
    gaps: list[str]
    summary_for_client: str


def review(title: str, criteria: list[str], notes: str, links: list[str]) -> AcceptanceResult:
    crit = "\n".join(f"- {c}" for c in criteria) or "- (none listed)"
    link_txt = "\n".join(f"- {u}" for u in links) or "- (none)"
    prompt = (
        f"Milestone: {title}\nAcceptance criteria:\n{crit}\n\n"
        f"Delivery notes:\n{notes or '(none)'}\n\nLinks:\n{link_txt}"
    )
    return structured(prompt, AcceptanceResult, system=PROMPT)
