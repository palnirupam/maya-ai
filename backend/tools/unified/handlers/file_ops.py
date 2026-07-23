"""All file operation implementations — no LLM token cost here."""
import errno
import os
import shutil
import uuid
from ..core.policy import is_safe_path
from ..core.path import dedupe_path, ensure_parent, find_items

_PDF_EXTS = {".pdf"}
_DOCX_EXTS = {".docx"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff"}


class PartialFileOperationError(RuntimeError):
    """An operation changed state but could not reach its full end state."""


def _is_link_like(path: str) -> bool:
    """Detect symlinks and Windows junction/reparse-point directories."""
    try:
        return os.path.islink(path) or (
            hasattr(os.path, "isjunction") and os.path.isjunction(path)
        )
    except OSError:
        return True


def _tree_contains_link(path: str) -> bool:
    if _is_link_like(path):
        return True
    if not os.path.isdir(path):
        return False
    try:
        for root, dirs, files in os.walk(path, followlinks=False):
            for entry in dirs + files:
                if _is_link_like(os.path.join(root, entry)):
                    return True
    except OSError:
        return True
    return False


def _remove_path(path: str) -> None:
    if _is_link_like(path) or not os.path.isdir(path):
        os.unlink(path)
    elif not os.listdir(path):
        os.rmdir(path)
    else:
        shutil.rmtree(path)


def _temporary_sibling(path: str, label: str) -> str:
    parent = os.path.dirname(os.path.abspath(path))
    name = os.path.basename(path)
    return os.path.join(parent, f".{name}.maya-{label}-{uuid.uuid4().hex}")


def _destination(src: str, dst: str) -> str:
    dest = os.path.join(dst, os.path.basename(src)) if os.path.isdir(dst) else dst
    return dedupe_path(dest)


def _is_within(path: str, parent: str) -> bool:
    try:
        return os.path.commonpath(
            (os.path.realpath(os.path.abspath(path)), os.path.realpath(os.path.abspath(parent)))
        ) == os.path.realpath(os.path.abspath(parent))
    except (OSError, ValueError):
        return False


def _verify_staged_copy(src: str, stage: str) -> None:
    """Verify tree shape and file sizes before publishing a staged copy."""
    if os.path.isdir(src):
        source_entries = {}
        staged_entries = {}
        for root, dirs, files in os.walk(src, followlinks=False):
            rel_root = os.path.relpath(root, src)
            for directory in dirs:
                rel = os.path.normcase(os.path.normpath(os.path.join(rel_root, directory)))
                source_entries[("dir", rel)] = None
            for filename in files:
                path = os.path.join(root, filename)
                rel = os.path.normcase(os.path.normpath(os.path.join(rel_root, filename)))
                source_entries[("file", rel)] = os.path.getsize(path)
        for root, dirs, files in os.walk(stage, followlinks=False):
            rel_root = os.path.relpath(root, stage)
            for directory in dirs:
                rel = os.path.normcase(os.path.normpath(os.path.join(rel_root, directory)))
                staged_entries[("dir", rel)] = None
            for filename in files:
                path = os.path.join(root, filename)
                rel = os.path.normcase(os.path.normpath(os.path.join(rel_root, filename)))
                staged_entries[("file", rel)] = os.path.getsize(path)
        if source_entries != staged_entries:
            raise OSError("staged directory copy verification failed")
    elif not os.path.isfile(stage) or os.path.getsize(src) != os.path.getsize(stage):
        raise OSError("staged file copy verification failed")


def _copy_staged(src: str, dest: str) -> str:
    """Copy to a hidden sibling and expose the final path only when complete."""
    if os.path.isdir(src) and _is_within(dest, src):
        raise ValueError("destination cannot be inside the source directory")
    ensure_parent(dest)
    stage = _temporary_sibling(dest, "copy")
    try:
        if os.path.isdir(src):
            shutil.copytree(src, stage)
        else:
            shutil.copy2(src, stage)
        _verify_staged_copy(src, stage)
        # On Windows, rename is atomic and fails if another process created the
        # destination after dedupe_path() selected it. Never overwrite that file.
        os.rename(stage, dest)
    except Exception as exc:
        try:
            if os.path.lexists(stage):
                _remove_path(stage)
        except Exception as cleanup_exc:
            raise PartialFileOperationError(
                f"copy failed and incomplete staging remains at {stage}: {cleanup_exc}"
            ) from exc
        raise
    return dest


def _read_pdf(src):
    try:
        from pypdf import PdfReader
    except ImportError:
        return "ERR: pypdf not installed"
    try:
        reader = PdfReader(src)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text or "ERR: PDF has no extractable text (likely a scanned/image-only PDF)"
    except Exception as e:
        return f"ERR: failed to read PDF ({e})"


def _read_docx(src):
    try:
        import docx
    except ImportError:
        return "ERR: python-docx not installed"
    try:
        doc = docx.Document(src)
        text = "\n".join(p.text for p in doc.paragraphs)
        return text or "ERR: DOCX contains no text"
    except Exception as e:
        return f"ERR: failed to read DOCX ({e})"


def _read_image(src):
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return "ERR: pytesseract/Pillow not installed"
    try:
        with Image.open(src) as img:
            text = pytesseract.image_to_string(img)
        return text or "ERR: OCR found no text in image"
    except pytesseract.TesseractNotFoundError:
        return "ERR: Tesseract-OCR binary not found on this machine (install it separately and add it to PATH)"
    except Exception as e:
        return f"ERR: OCR failed ({e})"


def _move(src, dst):
    dest = _destination(src, dst)
    if os.path.isdir(src) and _is_within(dest, src):
        raise ValueError("destination cannot be inside the source directory")
    ensure_parent(dest)
    try:
        os.rename(src, dest)
        return dest
    except OSError as exc:
        if exc.errno != errno.EXDEV and getattr(exc, "winerror", None) != 17:
            raise

    _copy_staged(src, dest)
    recovery = _temporary_sibling(src, "move-recovery")
    try:
        os.rename(src, recovery)
    except Exception as exc:
        raise PartialFileOperationError(
            f"destination created at {dest}, but source remains at {src}: {exc}"
        ) from exc

    try:
        _remove_path(recovery)
    except Exception as exc:
        raise PartialFileOperationError(
            f"destination created at {dest}; source cleanup remains at {recovery}: {exc}"
        ) from exc
    return dest


def _copy(src, dst):
    return _copy_staged(src, _destination(src, dst))


def handle_file(action, src="", dst="", name="", n=5, path=""):
    """Route file actions to implementations."""
    if action == "copy":
        if not os.path.exists(src):
            return f"ERR: missing {src}"
        if not is_safe_path(src) or (dst and not is_safe_path(dst)):
            return "ERR: protected path"
        if _tree_contains_link(src):
            return "ERR: copy source contains a symlink or reparse point"
        try:
            return f"OK: {_copy(src, dst)}"
        except PartialFileOperationError as e:
            return f"PARTIAL: {e}"
        except Exception as e:
            return f"ERR: {e}"

    if action == "move":
        if not os.path.exists(src):
            return f"ERR: missing {src}"
        if not is_safe_path(src) or (dst and not is_safe_path(dst)):
            return "ERR: protected path"
        if _tree_contains_link(src):
            return "ERR: move source contains a symlink or reparse point"
        try:
            return f"OK: {_move(src, dst)}"
        except PartialFileOperationError as e:
            return f"PARTIAL: {e}"
        except Exception as e:
            return f"ERR: {e}"

    if action == "rename":
        if not os.path.exists(src):
            return f"ERR: missing {src}"
        # Security: deny rename on protected paths (would let AI shadow .env files, etc.)
        parent = os.path.dirname(os.path.abspath(src)) or "."
        if not dst or os.path.isabs(dst) or os.path.basename(dst) != dst:
            return "ERR: rename destination must be a file name in the same directory"
        dest = os.path.join(parent, dst)
        if not is_safe_path(src) or not is_safe_path(dest):
            return "ERR: protected path"
        dest = dedupe_path(dest)
        try:
            os.rename(src, dest)
            return f"OK: {dest}"
        except Exception as e:
            return f"ERR: {e}"

    if action == "delete":
        if not os.path.lexists(src):
            return f"ERR: missing {src}"
        if not is_safe_path(src):
            return "ERR: protected path"
        try:
            _remove_path(src)
            if os.path.lexists(src):
                return f"ERR: delete could not be verified for {src}"
            return f"OK: removed {src}"
        except Exception as e:
            return f"ERR: {e}"

    if action == "mkdir":
        try:
            if not is_safe_path(path):
                return "ERR: protected path"
            os.makedirs(path, exist_ok=False)
            return f"OK: {path}"
        except FileExistsError:
            return f"ERR: exists {path}"
        except Exception as e:
            return f"ERR: {e}"

    if action == "read":
        if not os.path.isfile(src):
            return f"ERR: not a file {src}"
        # Security: block reads of protected paths (e.g. .env, crypto key files)
        if not is_safe_path(src):
            return "ERR: protected path"
        ext = os.path.splitext(src)[1].lower()
        try:
            if ext in _PDF_EXTS:
                return _read_pdf(src)
            if ext in _DOCX_EXTS:
                return _read_docx(src)
            if ext in _IMAGE_EXTS:
                return _read_image(src)
            with open(src, encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"ERR: {e}"

    if action == "write":
        try:
            # Security: block writes to protected paths (e.g. project source, .env)
            if not is_safe_path(src):
                return "ERR: protected path"
            dest = dedupe_path(src)
            ensure_parent(dest)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(dst)
            return f"OK: {dest}"
        except Exception as e:
            return f"ERR: {e}"

    if action == "ls":
        try:
            target = path or src or "."
            if not os.path.isdir(target):
                return f"ERR: not a dir {target}"
            if not is_safe_path(target):
                return "ERR: protected path"
            items = os.listdir(target)
            return f"{target}:\n" + "\n".join(items)
        except Exception as e:
            return f"ERR: {e}"

    if action == "search":
        try:
            query = name or src
            results = find_items(query, n)
            if not results:
                return f"Not found: '{query}'"
            return f"Found {len(results)}:\n" + "\n".join(f"  - {p}" for p in results)
        except Exception as e:
            return f"ERR: {e}"

    if action == "delete_by_name":
        try:
            items = find_items(name, n)
            if not items:
                return f"Not found: '{name}'"
            deleted, errors = [], []
            for p in items:
                if not is_safe_path(p):
                    errors.append(f"{os.path.basename(p)}: protected")
                    continue
                try:
                    _remove_path(p)
                    if os.path.lexists(p):
                        errors.append(f"{os.path.basename(p)}: deletion could not be verified")
                    else:
                        deleted.append(p)
                except Exception as e:
                    errors.append(f"{os.path.basename(p)}: {e}")
            parts = []
            if deleted:
                parts.append(f"Deleted {len(deleted)}:")
                for d in deleted:
                    parts.append(f"  - {d}")
            if errors:
                parts.append(f"Errors: {'; '.join(errors[:3])}")
            return "\n".join(parts) if parts else f"Not found: '{name}'"
        except Exception as e:
            return f"ERR: {e}"

    if action == "organize":
        try:
            from ...desktop.advanced.file_system_tools import organize_folder, _resolve_folder
            folder = path or "downloads"
            if not is_safe_path(_resolve_folder(folder)):
                return "ERR: protected path"
            return organize_folder(folder)
        except Exception as e:
            return f"ERR: {e}"

    return f"ERR: unknown file action '{action}'"
