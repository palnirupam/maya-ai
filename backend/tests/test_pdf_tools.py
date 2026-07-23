"""Regression tests for background PDF report generation."""

import re
from pathlib import Path

from pypdf import PdfReader

from backend.tools.documents import create_pdf


def _created_path(result: str) -> Path:
    assert result.startswith("SUCCESS: PDF created at "), result
    return Path(result.removeprefix("SUCCESS: PDF created at "))


def test_create_pdf_writes_extractable_report_in_test_output_directory():
    result = create_pdf(
        "West Bengal News",
        "Headline one\nhttps://example.com/one\n\nHeadline two and its summary.",
        "West Bengal News.pdf",
    )

    path = _created_path(result)
    assert path.parent.name == "output"
    assert path.name.startswith("West Bengal News")
    assert path.suffix == ".pdf"
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    assert "West Bengal News" in text
    assert "Headline one" in text
    assert "example.com/one" in text


def test_create_pdf_sanitizes_filename_and_never_overwrites():
    first = _created_path(create_pdf("Daily Report", "First version", "../bad:name.pdf"))
    second = _created_path(create_pdf("Daily Report", "Second version", "../bad:name.pdf"))

    assert re.fullmatch(r"bad_name(?: \(\d+\))?\.pdf", first.name)
    assert second != first
    assert first.exists()
    assert second.exists()


def test_create_pdf_rejects_empty_content():
    assert create_pdf("News", "   ").startswith("ERROR:")
