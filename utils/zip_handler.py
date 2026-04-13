"""
ZIP archive support: extract to temp dir and return path.
"""

import os
import zipfile
import tempfile
import shutil


def extract_zip(zip_path: str, log=None) -> str:
    """
    Extract a .zip to a temporary directory.
    Returns the path to the extracted directory.
    The caller is responsible for cleaning up with cleanup_temp(dir).
    """
    temp_dir = tempfile.mkdtemp(prefix="renpy_trans_")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(temp_dir)
        if log:
            log(f"[ZIP] Extracted to: {temp_dir}")
        # If the zip contains a single top-level folder, use that
        entries = os.listdir(temp_dir)
        if len(entries) == 1:
            single = os.path.join(temp_dir, entries[0])
            if os.path.isdir(single):
                return single
        return temp_dir
    except Exception as e:
        if log:
            log(f"[ZIP] Error extracting: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def cleanup_temp(temp_dir: str) -> None:
    """Clean up a temp directory (best-effort)."""
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass
