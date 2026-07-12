"""Pull plain text out of an uploaded resume file.

Handles PDF and Word (.docx); anything else is treated as plain text. Keeps the upload
path simple: the file becomes text, then it goes through the same screener flow as a
pasted resume.
"""

from __future__ import annotations

from io import BytesIO


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return _from_pdf(data)
    if name.endswith(".docx"):
        return _from_docx(data)
    return data.decode("utf-8", errors="ignore")


def _from_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _from_docx(data: bytes) -> str:
    import docx

    doc = docx.Document(BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs).strip()
