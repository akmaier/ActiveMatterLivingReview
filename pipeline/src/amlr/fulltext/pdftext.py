"""Full-text layer of a PDF (PyMuPDF, falling back to pypdf if it is installed)."""

from __future__ import annotations

from pathlib import Path


def extract_text(pdf_path: Path) -> str:
    """Extract the full text layer from a PDF (PyMuPDF, falls back to pypdf)."""
    try:
        import fitz

        with fitz.open(str(pdf_path)) as doc:
            return "\n".join(page.get_text("text") for page in doc)
    except Exception:
        try:
            import pypdf

            reader = pypdf.PdfReader(str(pdf_path))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
            return ""
