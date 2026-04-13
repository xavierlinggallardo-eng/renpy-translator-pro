"""
Reinsertion engine: takes translated segments and writes them back
into the .rpy files while preserving all formatting and structure.
"""

import os
import re
import shutil
from typing import List, Dict, Tuple
from .parser import Segment


def _escape_for_renpy(text: str, quote_char: str) -> str:
    """Escape the quote character inside translated text."""
    other = '"' if quote_char == "'" else "'"
    # Escape only the relevant quote char; unescape the other one
    text = text.replace('\\' + quote_char, quote_char)  # un-double-escape first
    text = text.replace(quote_char, '\\' + quote_char)
    return text


def reinsert(
    segments: List[Segment],
    translations: Dict[int, str],  # line_no -> translated text
    project_dir: str,
    output_dir: str,
    log_callback=None,
) -> int:
    """
    Reinsert translations into a copy of the project.

    Returns number of lines modified.
    """
    log = log_callback or (lambda m: None)

    # Group segments by file
    by_file: Dict[str, List[Segment]] = {}
    for seg in segments:
        by_file.setdefault(seg.file, []).append(seg)

    # Copy full project to output
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    shutil.copytree(project_dir, output_dir)

    modified_count = 0

    for filepath, file_segs in by_file.items():
        # Build a map: line_number (1-based) -> new text
        line_map: Dict[int, str] = {}
        for seg in file_segs:
            key = seg.line
            if key in translations and translations[key]:
                line_map[key] = translations[key]

        if not line_map:
            continue

        # Compute relative path and output path
        rel = os.path.relpath(filepath, project_dir)
        out_path = os.path.join(output_dir, rel)

        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except Exception as e:
            log(f"[Reinsert] Cannot read {filepath}: {e}")
            continue

        # Build segment lookup by line_no for quote_char and type
        seg_by_line: Dict[int, Segment] = {s.line: s for s in file_segs}

        new_lines = list(lines)

        for line_no, new_text in line_map.items():
            idx = line_no - 1
            if idx < 0 or idx >= len(lines):
                continue

            seg = seg_by_line.get(line_no)
            if not seg:
                continue

            original = lines[idx].rstrip('\n')
            q = seg.quote_char

            try:
                escaped = _escape_for_renpy(new_text, q)
                rebuilt = _rebuild_line(original, seg, escaped)
                if rebuilt is not None:
                    new_lines[idx] = rebuilt + '\n'
                    modified_count += 1
            except Exception as e:
                log(f"[Reinsert] Line {line_no} in {filepath}: {e}")

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        try:
            with open(out_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            log(f"[Reinsert] Written: {out_path}")
        except Exception as e:
            log(f"[Reinsert] Cannot write {out_path}: {e}")

    return modified_count


def _rebuild_line(original: str, seg: Segment, new_text: str) -> str:
    """
    Reconstruct a single line replacing only the quoted string.
    Works for dialogue, narration, menu choices, UI text, and translate blocks.
    """
    q = seg.quote_char
    pattern = re.compile(
        r'(?P<q>["\'])(?P<text>(?:[^"\'\\]|\\.)*)(?P=q)'
    )

    # Find the first (or only) quoted string in the line
    match = pattern.search(original)
    if not match:
        return original  # nothing to replace

    start, end = match.start(), match.end()
    rebuilt = original[:start] + q + new_text + q + original[end:]
    return rebuilt
