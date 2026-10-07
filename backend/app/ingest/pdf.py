import pymupdf

# Expand "fi"/"fl" ligatures so quotes match what users (and LLMs) type.
FLAGS = pymupdf.TEXTFLAGS_TEXT & ~pymupdf.TEXT_PRESERVE_LIGATURES


def page_texts(pdf: bytes) -> list[str]:
    """Plain text per page; index 0 is page 1."""
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return [page.get_text(flags=FLAGS) for page in doc]
