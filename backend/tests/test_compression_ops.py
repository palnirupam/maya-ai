"""Tests for file compression and extraction operations."""
import os
import tempfile
import zipfile
import tarfile
from pathlib import Path
import pytest

from backend.tools.unified.handlers.compression_ops import (
    handle_compression,
    _compress_folder,
    _extract_archive,
    _list_archive_contents,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_files(temp_dir):
    """Create sample files for testing."""
    test_dir = Path(temp_dir) / "test_folder"
    test_dir.mkdir()
    
    # Create test files
    (test_dir / "file1.txt").write_text("Content of file 1")
    (test_dir / "file2.txt").write_text("Content of file 2")
    
    # Create subdirectory with file
    sub_dir = test_dir / "subdir"
    sub_dir.mkdir()
    (sub_dir / "file3.txt").write_text("Content of file 3")
    
    return test_dir


def test_compress_folder_to_zip(sample_files, temp_dir):
    """Test compressing a folder to ZIP format."""
    dst = os.path.join(temp_dir, "test_archive.zip")
    result = _compress_folder(str(sample_files), dst)
    
    assert "OK:" in result
    assert "Compressed 3 file(s)" in result
    assert os.path.exists(dst)
    
    # Verify ZIP contents
    with zipfile.ZipFile(dst, 'r') as zipf:
        names = zipf.namelist()
        assert len(names) == 3


def test_compress_folder_to_tar_gz(sample_files, temp_dir):
    """Test compressing a folder to TAR.GZ format."""
    dst = os.path.join(temp_dir, "test_archive.tar.gz")
    result = _compress_folder(str(sample_files), dst)
    
    assert "OK:" in result
    assert os.path.exists(dst)
    
    # Verify TAR contents
    with tarfile.open(dst, 'r:gz') as tar:
        names = tar.getnames()
        assert len(names) == 3


def test_compress_single_file(temp_dir):
    """Test compressing a single file."""
    # Create single file
    test_file = Path(temp_dir) / "single.txt"
    test_file.write_text("Single file content")
    
    dst = os.path.join(temp_dir, "single.zip")
    result = _compress_folder(str(test_file), dst)
    
    assert "OK:" in result
    assert "Compressed 1 file(s)" in result
    assert os.path.exists(dst)


def test_compress_nonexistent_source():
    """Test compressing a nonexistent source."""
    result = _compress_folder("/nonexistent/path", "output.zip")
    assert "ERR:" in result
    assert "not found" in result.lower()


def test_extract_zip(sample_files, temp_dir):
    """Test extracting a ZIP archive."""
    # First compress
    zip_path = os.path.join(temp_dir, "test.zip")
    _compress_folder(str(sample_files), zip_path)
    
    # Extract
    extract_dir = os.path.join(temp_dir, "extracted")
    result = _extract_archive(zip_path, extract_dir)
    
    assert "OK:" in result
    assert "Extracted 3 file(s)" in result
    assert os.path.exists(extract_dir)
    
    # Verify extracted files
    assert (Path(extract_dir) / "test_folder" / "file1.txt").exists()
    assert (Path(extract_dir) / "test_folder" / "subdir" / "file3.txt").exists()


def test_extract_tar_gz(sample_files, temp_dir):
    """Test extracting a TAR.GZ archive."""
    # First compress
    tar_path = os.path.join(temp_dir, "test.tar.gz")
    _compress_folder(str(sample_files), tar_path)
    
    # Extract
    extract_dir = os.path.join(temp_dir, "extracted")
    result = _extract_archive(tar_path, extract_dir)
    
    assert "OK:" in result
    assert os.path.exists(extract_dir)


def test_extract_nonexistent_archive():
    """Test extracting a nonexistent archive."""
    result = _extract_archive("/nonexistent/archive.zip", "/output")
    assert "ERR:" in result
    assert "not found" in result.lower()


def test_extract_unsupported_format(temp_dir):
    """Test extracting unsupported archive format."""
    # Create a fake archive file
    fake_archive = os.path.join(temp_dir, "fake.rar")
    Path(fake_archive).write_text("not a real archive")
    
    result = _extract_archive(fake_archive, temp_dir)
    assert "ERR:" in result
    assert "Unsupported" in result


def test_list_archive_contents_zip(sample_files, temp_dir):
    """Test listing ZIP archive contents."""
    # First compress
    zip_path = os.path.join(temp_dir, "test.zip")
    _compress_folder(str(sample_files), zip_path)
    
    # List contents
    result = _list_archive_contents(zip_path)
    
    assert "Archive:" in result
    assert "3 items" in result
    assert "file1.txt" in result or "test_folder" in result


def test_list_archive_contents_tar(sample_files, temp_dir):
    """Test listing TAR archive contents."""
    # First compress
    tar_path = os.path.join(temp_dir, "test.tar.gz")
    _compress_folder(str(sample_files), tar_path)
    
    # List contents
    result = _list_archive_contents(tar_path)
    
    assert "Archive:" in result
    assert "items" in result


def test_list_nonexistent_archive():
    """Test listing nonexistent archive."""
    result = _list_archive_contents("/nonexistent/archive.zip")
    assert "ERR:" in result
    assert "not found" in result.lower()


def test_compress_specific_files(temp_dir):
    """Test compressing specific files by name."""
    # Create test files
    file1 = Path(temp_dir) / "doc1.txt"
    file2 = Path(temp_dir) / "doc2.txt"
    file1.write_text("Document 1")
    file2.write_text("Document 2")
    
    # Compress specific files
    file_paths = [str(file1), str(file2)]
    dst = os.path.join(temp_dir, "specific.zip")
    
    result = handle_compression("compress_files", name=",".join(file_paths), dst=dst)
    
    assert "OK:" in result
    assert "Compressed 2 file(s)" in result
    assert os.path.exists(dst)
    
    # Verify contents
    with zipfile.ZipFile(dst, 'r') as zipf:
        names = zipf.namelist()
        assert "doc1.txt" in names
        assert "doc2.txt" in names


def test_compress_files_with_missing(temp_dir):
    """Test compressing files when some don't exist."""
    # Create one file
    file1 = Path(temp_dir) / "exists.txt"
    file1.write_text("Exists")
    
    # Reference non-existent file
    file_paths = [str(file1), "/nonexistent/file.txt"]
    dst = os.path.join(temp_dir, "partial.zip")
    
    result = handle_compression("compress_files", name=",".join(file_paths), dst=dst)
    
    assert "OK:" in result
    assert "Compressed 1 file(s)" in result
    assert "Warning:" in result
    assert os.path.exists(dst)


def test_handle_compression_router(sample_files, temp_dir):
    """Test the main handle_compression router function."""
    # Test compress
    dst = os.path.join(temp_dir, "router_test.zip")
    result = handle_compression("compress", str(sample_files), dst)
    assert "OK:" in result
    
    # Test extract
    extract_dir = os.path.join(temp_dir, "extracted_router")
    result = handle_compression("extract", dst, extract_dir)
    assert "OK:" in result
    
    # Test list
    result = handle_compression("list", dst)
    assert "Archive:" in result
    
    # Test unknown action
    result = handle_compression("unknown_action")
    assert "ERR:" in result
    assert "Unknown" in result


def test_compression_with_language_integration(sample_files, temp_dir):
    """Test compression operations with language-aware messages."""
    from backend.brain.language_style import set_latest_conversation_style
    from backend.brain.language_policy_enforcer import enforce_style
    
    # Set language to Banglish
    set_latest_conversation_style("banglish")
    
    dst = os.path.join(temp_dir, "test.zip")
    result = handle_compression("compress", str(sample_files), dst)
    
    # Result should be in English initially (handler returns English)
    assert "OK:" in result
    
    # Can be translated to Banglish if needed
    banglish_result = enforce_style(result, "banglish")
    assert isinstance(banglish_result, str)


def test_auto_format_detection(sample_files, temp_dir):
    """Test automatic format detection from file extension."""
    # No extension - should default to .zip
    result = _compress_folder(str(sample_files), os.path.join(temp_dir, "noext"))
    assert "OK:" in result
    assert os.path.exists(os.path.join(temp_dir, "noext.zip"))
    
    # TAR.BZ2 extension
    result = _compress_folder(str(sample_files), os.path.join(temp_dir, "test.tar.bz2"))
    assert "OK:" in result
    assert os.path.exists(os.path.join(temp_dir, "test.tar.bz2"))


def test_compression_ratio_reporting(sample_files, temp_dir):
    """Test that compression ratio is reported."""
    dst = os.path.join(temp_dir, "ratio_test.zip")
    result = _compress_folder(str(sample_files), dst)
    
    assert "MB" in result
    assert "%" in result  # Compression percentage
    assert "reduction" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
