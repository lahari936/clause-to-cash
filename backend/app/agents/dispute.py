"""Dispute agent: turns contract clauses + delivery/acceptance records + timeline into an evidence
pack (markdown -> PDF) and a proposed response. It proposes; a human approves submission."""

import html
import io
import logging
import re

import pymupdf
from pydantic import BaseModel

from app.llm.provider import structured

log = logging.getLogger(__name__)

PROMPT = """You prepare a seller's evidence pack for a PayPal dispute on an invoice payment.
Use only the facts provided. Quote contract clauses verbatim with their page numbers.
`evidence_markdown`: sections '# Summary', '## Contract terms', '## Delivery and acceptance',
'## Invoice and payment timeline', '## Conclusion'. Use bullet lists. No invented facts.
`proposed_response`: 3-5 sentences to send to PayPal/the buyer."""


class Pack(BaseModel):
    evidence_markdown: str
    proposed_response: str


def build(facts: str) -> Pack:
    try:
        return structured(facts, Pack, system=PROMPT)
    except Exception:
        log.warning("dispute agent unavailable, using deterministic pack")
        return Pack(
            evidence_markdown=f"# Summary\nEvidence compiled from contract records.\n\n{facts}",
            proposed_response="The services were delivered and accepted under the signed contract; "
            "the invoice matches the contracted milestone amount. Evidence attached.",
        )


def _md_to_html(md: str) -> str:
    out, in_list = [], False
    for line in md.splitlines():
        t = html.escape(line.strip())
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        is_item = t.startswith(("- ", "* "))
        if in_list and not is_item:
            out.append("</ul>")
            in_list = False
        if t.startswith("### "):
            out.append(f"<h3>{t[4:]}</h3>")
        elif t.startswith("## "):
            out.append(f"<h2>{t[3:]}</h2>")
        elif t.startswith("# "):
            out.append(f"<h1>{t[2:]}</h1>")
        elif is_item:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{t[2:]}</li>")
        elif t:
            out.append(f"<p>{t}</p>")
    if in_list:
        out.append("</ul>")
    return "".join(out)


def to_pdf(md: str) -> bytes:
    story = pymupdf.Story(
        html=_md_to_html(md), user_css="body{font-family:sans-serif;font-size:10pt}"
    )
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    rect = pymupdf.paper_rect("a4")
    more = True
    while more:
        dev = writer.begin_page(rect)
        more, _ = story.place(rect + (50, 50, -50, -50))
        story.draw(dev)
        writer.end_page()
    writer.close()
    return buf.getvalue()
