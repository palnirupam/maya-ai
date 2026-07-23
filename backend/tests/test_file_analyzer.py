"""Regression tests for the "advanced" file analyzer.

Bug: the `file(action="read", ...)` tool only ever did a raw
`open(src, encoding="utf-8").read()` — any PDF/DOCX/image threw a raw
UnicodeDecodeError-style `ERR: ...`, and every large file was resent in full
on every later turn (no summarization), burning tokens. Fixed by:
  1. Extension-based extraction in file_ops.py (pypdf / python-docx /
     pytesseract) while preserving 100% of existing plain-text behavior.
  2. A threshold-triggered, cached "fast" tier LLM summarization pass layered
     on top in file_router.py (never touches file_ops.py's zero-LLM-cost
     invariant). See conversation history for the full design writeup.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import asyncio
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from backend.tools.unified.handlers import file_ops
from backend.tools.unified.dispatchers import file_router


class TestPlainTextRegression(unittest.TestCase):
    """Existing plain-text/code read behavior must be byte-identical to before."""

    def test_txt_file_read_unchanged(self):
        tmp = tempfile.mktemp(suffix=".txt")
        content = "line one\nline two\n"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            result = file_ops.handle_file("read", src=tmp)
            self.assertEqual(result, content)
        finally:
            os.remove(tmp)

    def test_missing_file_still_errors(self):
        result = file_ops.handle_file("read", src="C:\\nonexistent_maya_test_file.txt")
        self.assertTrue(result.startswith("ERR:"))


class TestPdfRead(unittest.TestCase):
    def test_pdf_text_extracted(self):
        from reportlab.pdfgen import canvas
        tmp = tempfile.mktemp(suffix=".pdf")
        c = canvas.Canvas(tmp)
        c.drawString(100, 750, "Hello from a test PDF document.")
        c.save()
        try:
            result = file_ops.handle_file("read", src=tmp)
            self.assertIn("Hello from a test PDF document.", result)
            self.assertFalse(result.startswith("ERR:"))
        finally:
            os.remove(tmp)

    def test_corrupt_pdf_gives_clear_error(self):
        tmp = tempfile.mktemp(suffix=".pdf")
        with open(tmp, "wb") as f:
            f.write(b"not a real pdf")
        try:
            result = file_ops.handle_file("read", src=tmp)
            self.assertTrue(result.startswith("ERR:"))
        finally:
            os.remove(tmp)


class TestDocxRead(unittest.TestCase):
    def test_docx_text_extracted(self):
        import docx
        tmp = tempfile.mktemp(suffix=".docx")
        d = docx.Document()
        d.add_paragraph("Hello from a test DOCX document.")
        d.save(tmp)
        try:
            result = file_ops.handle_file("read", src=tmp)
            self.assertEqual(result, "Hello from a test DOCX document.")
        finally:
            os.remove(tmp)


class TestImageReadDegradesGracefully(unittest.TestCase):
    """Tesseract is a separate system binary — its absence must not crash
    the read action, just return a clear ERR message."""

    def test_missing_tesseract_binary_is_graceful(self):
        import pytesseract
        tmp = tempfile.mktemp(suffix=".png")
        from PIL import Image
        Image.new("RGB", (10, 10)).save(tmp)
        try:
            with patch.object(
                pytesseract, "image_to_string",
                side_effect=pytesseract.TesseractNotFoundError(),
            ):
                result = file_ops.handle_file("read", src=tmp)
            self.assertTrue(result.startswith("ERR:"))
            self.assertIn("Tesseract", result)
        finally:
            os.remove(tmp)


class TestSummarizationTriggersAndCaches(unittest.TestCase):
    """Large extracted text should be summarized via a single fast-tier LLM
    call, and re-reading an unchanged file must hit the cache instead of
    calling the LLM again."""

    def test_large_file_is_summarized_and_cached(self):
        tmp = tempfile.mktemp(suffix=".txt")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("x" * 5000)

        fake_summary = "A concise summary."
        mock_generate = AsyncMock(return_value=fake_summary)
        try:
            with patch(
                "backend.brain.providers.gemini_adapter.gemini_adapter.generate_response",
                mock_generate,
            ):
                result1 = asyncio.run(file_router.file(action="read", src=tmp))
                result2 = asyncio.run(file_router.file(action="read", src=tmp))

            self.assertIn(fake_summary, result1)
            self.assertTrue(result1.startswith("[Summarized"))
            self.assertEqual(result1, result2)
            mock_generate.assert_called_once()
        finally:
            os.remove(tmp)

    def test_small_file_is_not_summarized(self):
        tmp = tempfile.mktemp(suffix=".txt")
        content = "short content"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)

        mock_generate = AsyncMock(return_value="should not be used")
        try:
            with patch(
                "backend.brain.providers.gemini_adapter.gemini_adapter.generate_response",
                mock_generate,
            ):
                result = asyncio.run(file_router.file(action="read", src=tmp))

            self.assertEqual(result, content)
            mock_generate.assert_not_called()
        finally:
            os.remove(tmp)

    def test_non_read_actions_pass_through_unaffected(self):
        tmp_dir = tempfile.mkdtemp()
        result = asyncio.run(file_router.file(action="ls", path=tmp_dir))
        self.assertIn(tmp_dir, result)


if __name__ == "__main__":
    unittest.main()
