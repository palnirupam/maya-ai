"""Create readable PDF reports without opening a desktop application."""

from __future__ import annotations

import html
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from backend.tools.unified.core.path import dedupe_path
from backend.tools.unified.core.policy import assert_safe_path


logger = logging.getLogger(__name__)

_MAX_TITLE_CHARS = 300
_MAX_CONTENT_CHARS = 200_000
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def _safe_filename(filename: str, title: str) -> str:
    raw = Path(filename or "").name.strip()
    if not raw:
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_-")
        raw = stem or f"maya_report_{datetime.now():%Y%m%d_%H%M%S}"

    raw = _INVALID_FILENAME.sub("_", raw).strip(" .")
    if not raw:
        raw = f"maya_report_{datetime.now():%Y%m%d_%H%M%S}"

    path = Path(raw)
    stem = path.stem[:120].rstrip(" .") or "maya_report"
    if stem.lower() in _WINDOWS_RESERVED:
        stem = f"maya_{stem}"
    return f"{stem}.pdf"


def _output_directory() -> Path:
    configured = os.getenv("MAYA_OUTPUT_DIR", "").strip()
    if configured:
        output_dir = Path(configured).expanduser().resolve()
    else:
        documents = Path.home() / "Documents"
        base = documents if documents.is_dir() else Path.home()
        output_dir = (base / "Maya AI Reports").resolve()

    assert_safe_path(str(output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir

_FONT_NAME = "MayaPdfUnicode"
_BOLD_FONT_NAME = "MayaPdfUnicode-Bold"

# Bengali Unicode block, used for glyph-coverage verification.
_BENGALI_BLOCK = range(0x0980, 0x0A00)
# A handful of high-frequency Bengali codepoints (consonants, matras,
# virama, digits) that MUST be present for the font to be usable. Checking
# a sample is faster than checking the whole block and catches "font claims
# Bengali support but is missing key glyphs" cases too.
_BENGALI_PROBE = [0x0995, 0x09BE, 0x09CD, 0x09BF, 0x09C7, 0x09A6, 0x09E6]


def _bundled_font_dir() -> Path:
    """Directory next to this file where verified fonts are shipped."""
    return Path(__file__).resolve().parent / "fonts"


def _has_bengali_coverage(font_path: Path) -> bool:
    """Actually check the font's cmap for Bengali glyphs instead of just
    trusting that the file exists. This is the check that was missing
    before, and is why fonts like DejaVuSans/Arial were silently accepted.
    """
    try:
        from fontTools.ttLib import TTFont as FTFont
    except ImportError:
        # fontTools not installed - fall back to a conservative name-based
        # guess rather than blocking font registration entirely.
        name = font_path.name.lower()
        return any(tag in name for tag in ("bengali", "beng", "nirmala", "vrinda", "noto"))

    try:
        f = FTFont(str(font_path), fontNumber=0, lazy=True)
        cmap = f.getBestCmap() or {}
        return all(cp in cmap for cp in _BENGALI_PROBE)
    except Exception:
        logger.debug("Could not inspect font %s for Bengali coverage", font_path, exc_info=True)
        return False


def _fontconfig_match(pattern: str) -> Path | None:
    """Ask the system's fontconfig for a font matching `pattern` (e.g.
    ':lang=bn' for "any font that declares Bengali support"). This finds
    fonts installed at non-standard paths that our hardcoded list would
    otherwise miss - much more robust than guessing file locations.
    """
    try:
        result = subprocess.run(
            ["fc-match", "--format=%{file}", pattern],
            capture_output=True, text=True, timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    path_str = result.stdout.strip()
    if result.returncode == 0 and path_str:
        candidate = Path(path_str)
        if candidate.is_file():
            return candidate
    return None


def _register_unicode_font() -> str:
    """Register a Unicode font that supports Bangla and return its name.
    Verifies actual Bengali glyph coverage for every candidate - a file
    merely existing is not sufficient, which was the cause of the
    "boxes appear" bug even after a font was "found".
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if _FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return _FONT_NAME

    configured = os.getenv("MAYA_PDF_FONT", "").strip()
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    bundled = _bundled_font_dir()

    candidates = [
        Path(configured).expanduser() if configured else None,
        # Bundled, verified font - ships with this module, always present.
        bundled / "NotoSansBengali-Regular.ttf",
        # fontconfig: ask the OS for its own best Bengali font match.
        _fontconfig_match(":lang=bn"),
        # Common Linux package locations.
        Path("/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansBengali-Regular.otf"),
        Path("/usr/share/fonts/truetype/lohit-bengali/Lohit-Bengali.ttf"),
        # Windows - Nirmala UI ships with Bengali coverage since Win8.
        windir / "Fonts" / "Nirmala.ttf",
        windir / "Fonts" / "NirmalaB.ttf",
        windir / "Fonts" / "vrinda.ttf",
        # macOS
        Path("/Library/Fonts/NotoSansBengali-Regular.ttf"),
        Path("/System/Library/Fonts/Supplemental/NotoSansBengali-Regular.ttf"),
    ]

    for candidate in candidates:
        if not candidate or not candidate.is_file():
            continue
        if not _has_bengali_coverage(candidate):
            # This is the guard that was missing before: a file existing
            # (e.g. DejaVuSans.ttf, arial.ttf) is not proof it can render
            # Bengali. Skip it and keep looking instead of registering it
            # and silently producing boxes.
            logger.debug("Skipping %s: no Bengali glyph coverage", candidate)
            continue
        try:
            pdfmetrics.registerFont(TTFont(_FONT_NAME, str(candidate)))
            _register_bold_variant(candidate, bundled)
            return _FONT_NAME
        except Exception:
            logger.warning("Failed to register font %s", candidate, exc_info=True)
            continue

    raise RuntimeError(
        "No font with verified Bengali glyph coverage was found. The "
        "bundled font in ./fonts/NotoSansBengali-Regular.ttf appears to be "
        "missing - reinstall the package, or set MAYA_PDF_FONT to a "
        ".ttf/.otf file that actually contains Bengali glyphs."
    )


def _register_bold_variant(regular_path: Path, bundled: Path) -> None:
    """Register a bold companion so <b> markup keeps Bengali coverage
    instead of reverting to a non-Bengali Helvetica-Bold.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if _BOLD_FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return

    bold_candidates = [
        bundled / "NotoSansBengali-Bold.ttf",
        _fontconfig_match(":lang=bn:weight=bold"),
        regular_path.with_name(regular_path.name.replace("Regular", "Bold")),
    ]
    for candidate in bold_candidates:
        if candidate and candidate.is_file() and _has_bengali_coverage(candidate):
            try:
                pdfmetrics.registerFont(TTFont(_BOLD_FONT_NAME, str(candidate)))
                return
            except Exception:
                continue

    # No verified bold file - reuse the regular font under the bold alias
    # rather than letting ReportLab fall back to Helvetica-Bold for <b>.
    try:
        pdfmetrics.registerFont(TTFont(_BOLD_FONT_NAME, str(regular_path)))
    except Exception:
        pass


def create_pdf(title: str, content: str, filename: str = "") -> str:
    """Create a polished PDF report fully in the background.

    Args:
        title: Report title displayed on the first page.
        content: Plain-text report body, including source URLs when available.
        filename: Optional output filename. The file is saved under the user's
            Documents/Maya AI Reports folder and never overwrites an old file.
    """
    if not isinstance(title, str) or not title.strip():
        return "ERROR: PDF title is required."
    if not isinstance(content, str) or not content.strip():
        return "ERROR: PDF content is required."
    if len(title) > _MAX_TITLE_CHARS:
        return f"ERROR: PDF title is too long (max {_MAX_TITLE_CHARS} characters)."
    if len(content) > _MAX_CONTENT_CHARS:
        return f"ERROR: PDF content is too large (max {_MAX_CONTENT_CHARS} characters)."

    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        output_dir = _output_directory()
        safe_name = _safe_filename(filename, title)
        output_path = Path(dedupe_path(str(output_dir / safe_name))).resolve()
        assert_safe_path(str(output_path))

        font_name = _register_unicode_font()
        bold_font_name = (
            _BOLD_FONT_NAME
            if _BOLD_FONT_NAME in pdfmetrics.getRegisteredFontNames()
            else font_name
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "MayaTitle",
            parent=styles["Title"],
            fontName=bold_font_name,
            fontSize=20,
            leading=27,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#172033"),
            spaceAfter=12,
        )
        body_style = ParagraphStyle(
            "MayaBody",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=10.5,
            leading=17,  # extra leading: Bengali conjuncts/matras need more
                          # vertical room than plain Latin text.
            alignment=TA_LEFT,
            textColor=colors.HexColor("#202938"),
            # NOTE: "CJK" wordWrap breaks between every character - correct
            # for Chinese/Japanese/Korean but WRONG for Bengali, which wraps
            # at spaces like Latin text. Left as default (None) intentionally.
            wordWrap=None,
            spaceAfter=7,
        )
        meta_style = ParagraphStyle(
            "MayaMeta",
            parent=body_style,
            fontName=font_name,
            fontSize=8.5,
            textColor=colors.HexColor("#667085"),
            alignment=TA_CENTER,
            spaceAfter=14,
        )

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=18 * mm,
            leftMargin=18 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=title.strip(),
            author="Maya AI",
        )

        story = [
            Paragraph(html.escape(title.strip()), title_style),
            Paragraph(
                f"Created by Maya AI on {datetime.now():%d %B %Y, %I:%M %p}",
                meta_style,
            ),
        ]
        for block in re.split(r"\n\s*\n", content.replace("\x00", "").strip()):
            lines = [html.escape(line.strip()) for line in block.splitlines() if line.strip()]
            if not lines:
                continue
            story.append(Paragraph("<br/>".join(lines), body_style))
            story.append(Spacer(1, 2 * mm))

        def add_page_number(canvas, document):
            canvas.saveState()
            canvas.setFont(font_name, 8)
            canvas.setFillColor(colors.HexColor("#667085"))
            canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {document.page}")
            canvas.restoreState()

        doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
        return f"SUCCESS: PDF created at {output_path}"
    except ImportError:
        return "ERROR: PDF support is not installed. Install the reportlab package."
    except RuntimeError as exc:
        logger.error("PDF creation failed: missing Unicode font (%s).", exc)
        return (
            "ERROR: PDF creation failed - no font with verified Bengali "
            "coverage available. Reinstall the package (fonts/ folder must "
            "ship alongside this module) or set MAYA_PDF_FONT."
        )
    except Exception as exc:
        logger.error("Background PDF creation failed (%s).", type(exc).__name__)
        return "ERROR: PDF creation failed."