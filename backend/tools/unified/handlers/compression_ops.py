"""File compression and extraction operations - zero external API cost."""
import os
import zipfile
import tarfile
import shutil
from pathlib import Path


def handle_compression(action: str, src: str = "", dst: str = "", name: str = "") -> str:
    """Handle file compression and extraction operations.
    
    Actions:
        compress - Create archive from folder/file (auto-detects format from dst extension)
        extract - Extract archive to destination folder
        list - List contents of archive
        compress_files - Compress multiple specific files (name = comma-separated paths)
    
    Args:
        action: Operation to perform
        src: Source file/folder path
        dst: Destination path (for compress: archive path, for extract: output folder)
        name: Additional parameter (comma-separated file paths for compress_files)
    
    Returns:
        Status message with operation result
    """
    try:
        if action == "compress":
            return _compress_folder(src, dst)
        
        elif action == "extract":
            return _extract_archive(src, dst)
        
        elif action == "list":
            return _list_archive_contents(src)
        
        elif action == "compress_files":
            file_paths = [p.strip() for p in (name or "").split(",") if p.strip()]
            return _compress_specific_files(file_paths, dst)
        
        return f"ERR: Unknown compression action '{action}'"
    
    except Exception as e:
        return f"ERR: {e}"


def _compress_folder(src: str, dst: str) -> str:
    """Compress a folder or file into an archive."""
    if not src or not os.path.exists(src):
        return f"ERR: Source path not found: {src}"
    
    if not dst:
        # Auto-generate destination filename
        dst = f"{src}.zip" if os.path.isdir(src) else f"{src}.zip"
    
    # Detect archive format from extension
    dst_lower = dst.lower()
    
    try:
        if dst_lower.endswith('.zip'):
            return _create_zip(src, dst)
        elif dst_lower.endswith(('.tar.gz', '.tgz')):
            return _create_tar(src, dst, 'gz')
        elif dst_lower.endswith(('.tar.bz2', '.tbz2')):
            return _create_tar(src, dst, 'bz2')
        elif dst_lower.endswith('.tar'):
            return _create_tar(src, dst, None)
        else:
            # Default to zip if no recognized extension
            dst = f"{dst}.zip"
            return _create_zip(src, dst)
    
    except Exception as e:
        return f"ERR: Compression failed: {e}"


def _create_zip(src: str, dst: str) -> str:
    """Create a ZIP archive."""
    src_path = Path(src)
    file_count = 0
    total_size = 0
    
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zipf:
        if src_path.is_file():
            # Single file
            zipf.write(src, src_path.name)
            file_count = 1
            total_size = src_path.stat().st_size
        else:
            # Directory - recursively add all files
            for root, dirs, files in os.walk(src):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Calculate relative path for archive
                    arcname = os.path.relpath(file_path, os.path.dirname(src))
                    zipf.write(file_path, arcname)
                    file_count += 1
                    total_size += os.path.getsize(file_path)
    
    compressed_size = os.path.getsize(dst)
    compression_ratio = 100 * (1 - compressed_size / total_size) if total_size > 0 else 0
    
    return (f"OK: Compressed {file_count} file(s) to {dst}\n"
            f"Original: {total_size / (1024*1024):.2f} MB → "
            f"Compressed: {compressed_size / (1024*1024):.2f} MB "
            f"({compression_ratio:.1f}% reduction)")


def _create_tar(src: str, dst: str, compression: str | None) -> str:
    """Create a TAR archive with optional compression."""
    mode_map = {None: 'w', 'gz': 'w:gz', 'bz2': 'w:bz2'}
    mode = mode_map.get(compression, 'w')
    
    src_path = Path(src)
    file_count = 0
    total_size = 0
    
    with tarfile.open(dst, mode) as tar:
        if src_path.is_file():
            tar.add(src, arcname=src_path.name)
            file_count = 1
            total_size = src_path.stat().st_size
        else:
            for root, dirs, files in os.walk(src):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, os.path.dirname(src))
                    tar.add(file_path, arcname=arcname)
                    file_count += 1
                    total_size += os.path.getsize(file_path)
    
    compressed_size = os.path.getsize(dst)
    return (f"OK: Created TAR archive with {file_count} file(s) at {dst}\n"
            f"Archive size: {compressed_size / (1024*1024):.2f} MB")


def _compress_specific_files(file_paths: list[str], dst: str) -> str:
    """Compress specific files into an archive."""
    if not file_paths:
        return "ERR: No files specified"
    
    if not dst:
        return "ERR: Destination archive path required"
    
    # Ensure .zip extension
    if not dst.lower().endswith('.zip'):
        dst = f"{dst}.zip"
    
    file_count = 0
    total_size = 0
    missing_files = []
    
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in file_paths:
            if not os.path.exists(file_path):
                missing_files.append(file_path)
                continue
            
            if os.path.isfile(file_path):
                zipf.write(file_path, os.path.basename(file_path))
                file_count += 1
                total_size += os.path.getsize(file_path)
    
    if missing_files and file_count == 0:
        return f"ERR: None of the specified files exist"
    
    result = f"OK: Compressed {file_count} file(s) to {dst}"
    if missing_files:
        result += f"\nWarning: {len(missing_files)} file(s) not found"
    
    return result


def _extract_archive(src: str, dst: str) -> str:
    """Extract an archive to destination folder."""
    if not src or not os.path.exists(src):
        return f"ERR: Archive not found: {src}"
    
    if not dst:
        # Extract to same directory as archive, with archive name as folder
        dst = os.path.join(
            os.path.dirname(src),
            os.path.splitext(os.path.basename(src))[0]
        )
    
    # Create destination directory if it doesn't exist
    os.makedirs(dst, exist_ok=True)
    
    src_lower = src.lower()
    
    try:
        if src_lower.endswith('.zip'):
            return _extract_zip(src, dst)
        elif src_lower.endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2')):
            return _extract_tar(src, dst)
        else:
            return f"ERR: Unsupported archive format (supported: .zip, .tar, .tar.gz, .tar.bz2)"
    
    except Exception as e:
        return f"ERR: Extraction failed: {e}"


def _extract_zip(src: str, dst: str) -> str:
    """Extract a ZIP archive."""
    with zipfile.ZipFile(src, 'r') as zipf:
        zipf.extractall(dst)
        file_count = len(zipf.namelist())
    
    return f"OK: Extracted {file_count} file(s) to {dst}"


def _extract_tar(src: str, dst: str) -> str:
    """Extract a TAR archive."""
    with tarfile.open(src, 'r:*') as tar:
        tar.extractall(dst)
        file_count = len(tar.getnames())
    
    return f"OK: Extracted {file_count} file(s) to {dst}"


def _list_archive_contents(src: str) -> str:
    """List contents of an archive without extracting."""
    if not src or not os.path.exists(src):
        return f"ERR: Archive not found: {src}"
    
    src_lower = src.lower()
    
    try:
        if src_lower.endswith('.zip'):
            with zipfile.ZipFile(src, 'r') as zipf:
                info_list = zipf.infolist()
                lines = [f"Archive: {src} ({len(info_list)} items)\n"]
                lines.append(f"{'Size':>10}  {'Compressed':>10}  Name")
                lines.append("-" * 50)
                
                for info in info_list[:50]:  # Limit to first 50 items
                    lines.append(
                        f"{info.file_size:>10}  {info.compress_size:>10}  {info.filename}"
                    )
                
                if len(info_list) > 50:
                    lines.append(f"\n... and {len(info_list) - 50} more items")
                
                return "\n".join(lines)
        
        elif src_lower.endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2')):
            with tarfile.open(src, 'r:*') as tar:
                members = tar.getmembers()
                lines = [f"Archive: {src} ({len(members)} items)\n"]
                lines.append(f"{'Size':>10}  {'Type':>6}  Name")
                lines.append("-" * 50)
                
                for member in members[:50]:
                    file_type = "dir" if member.isdir() else "file"
                    lines.append(
                        f"{member.size:>10}  {file_type:>6}  {member.name}"
                    )
                
                if len(members) > 50:
                    lines.append(f"\n... and {len(members) - 50} more items")
                
                return "\n".join(lines)
        
        else:
            return f"ERR: Unsupported archive format"
    
    except Exception as e:
        return f"ERR: Cannot read archive: {e}"
