import re
from dataclasses import dataclass

# "3.", "3.2", "Section 4", "ARTICLE 5" at line start, followed by a heading/clause text.
HEADING = re.compile(r"^\s*(?:(?:section|article|clause)\s+)?(\d+(?:\.\d+)*)[.)]?\s+\S", re.I)


@dataclass
class Section:
    page: int  # 1-based page where the section starts
    ref: str  # "3.2", or "" for preamble
    text: str


def split_sections(pages: list[str]) -> list[Section]:
    out: list[Section] = []
    cur = Section(page=1, ref="", text="")
    for pno, text in enumerate(pages, start=1):
        if cur.text.strip() and cur.page != pno:  # section continues on a new page
            out.append(cur)
            cur = Section(page=pno, ref=cur.ref, text="")
        for line in text.splitlines():
            m = HEADING.match(line)
            if m:
                if cur.text.strip():
                    out.append(cur)
                cur = Section(page=pno, ref=m.group(1), text="")
            cur.text += line + "\n"
    if cur.text.strip():
        out.append(cur)
    return out


def render_for_llm(sections: list[Section]) -> str:
    return "\n".join(f"[page {s.page}] [§{s.ref or '-'}]\n{s.text.strip()}\n" for s in sections)
