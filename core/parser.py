"""
Advanced Ren'Py .rpy file parser.
Extracts dialogue, narration, menu choices, UI text, and translate blocks.
"""

import re
import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Segment:
    """A single translatable text segment."""
    text: str
    file: str
    line: int
    seg_type: str  # dialogue | narration | menu | ui | translate_block
    indent: str = ""
    context: Optional[str] = None
    char_id: Optional[str] = None          # character id for dialogue
    translate_lang: Optional[str] = None   # language for translate blocks
    translate_label: Optional[str] = None  # label for translate blocks
    raw_line: str = ""                     # original raw line for rewrite
    quote_char: str = '"'                  # " or '
    # For translate blocks: the index of the original comment line
    orig_comment_line: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "file": self.file,
            "line": self.line,
            "type": self.seg_type,
            "indent": self.indent,
            "context": self.context,
            "char_id": self.char_id,
            "translate_lang": self.translate_lang,
            "translate_label": self.translate_label,
        }


# ── regex patterns ──────────────────────────────────────────────────────────

# Dialogue: optional char_id then a quoted string
#   e "Hello world"
#   mcth "Thinking..."
#   $ variable = "not this"  -- we ignore $ lines
RE_DIALOGUE = re.compile(
    r'^(?P<indent>\s*)'
    r'(?P<char>\w+)\s+'
    r'(?P<q>["\'])(?P<text>(?:[^"\'\\]|\\.)*)(?P=q)'
    r'\s*$'
)

# Pure narration: line is ONLY a quoted string (no char_id)
RE_NARRATION = re.compile(
    r'^(?P<indent>\s*)'
    r'(?P<q>["\'])(?P<text>(?:[^"\'\\]|\\.)+)(?P=q)'
    r'\s*$'
)

# Menu choice: "Choice text":
RE_MENU_CHOICE = re.compile(
    r'^(?P<indent>\s*)'
    r'(?P<q>["\'])(?P<text>(?:[^"\'\\]|\\.)*)(?P=q)'
    r'\s*:\s*$'
)

# UI text statements
RE_UI_TEXT = re.compile(
    r'^(?P<indent>\s*)'
    r'(?P<kw>text|textbutton|label|placeholder|input_prompt)\s+'
    r'(?P<q>["\'])(?P<text>(?:[^"\'\\]|\\.)*)(?P=q)'
    r'(?P<rest>.*)$'
)

# translate block header: translate <lang> <label>:
RE_TRANSLATE_HEADER = re.compile(
    r'^(?P<indent>\s*)translate\s+(?P<lang>\w+)\s+(?P<label>\S+)\s*:\s*$'
)

# Comment original inside translate block: # char "text"  or  # "text"
RE_TRANSLATE_COMMENT = re.compile(
    r'^(?P<indent>\s*)#\s*'
    r'(?:(?P<char>\w+)\s+)?'
    r'(?P<q>["\'])(?P<text>(?:[^"\'\\]|\\.)*)(?P=q)'
    r'\s*$'
)

# Active translation line inside block (same as dialogue/narration but inside block)
RE_TRANSLATE_ACTIVE = re.compile(
    r'^(?P<indent>\s*)'
    r'(?:(?P<char>\w+)\s+)?'
    r'(?P<q>["\'])(?P<text>(?:[^"\'\\]|\\.)*)(?P=q)'
    r'\s*$'
)

# Keywords that are NOT character identifiers
_KEYWORDS = {
    "menu", "label", "screen", "init", "python", "if", "elif", "else",
    "with", "show", "hide", "play", "stop", "queue", "return", "jump",
    "call", "pass", "while", "for", "define", "default", "image",
    "transform", "style", "translate", "voice", "window", "nvl",
    "scene", "pause", "renpy", "config", "persistent", "True", "False",
    "None", "not", "and", "or", "in", "is", "text", "textbutton",
    "vbox", "hbox", "frame", "add", "null", "bar", "key", "timer",
    "viewport", "side", "grid", "fixed", "button", "imagebutton",
    "hotspot", "input", "use", "at", "as", "onlayer", "zorder",
}

# Characters that indicate it's probably not a char_id
_SKIP_LINE_PREFIXES = ('$', '#', '//')


def _is_valid_char_id(name: str) -> bool:
    """Check if a token could be a Ren'Py character id (not a keyword)."""
    if name.lower() in _KEYWORDS:
        return False
    if not re.match(r'^[a-zA-Z_]\w*$', name):
        return False
    return True


class RenpyParser:
    """Parse .rpy files and return a list of Segment objects."""

    def __init__(self, log_callback=None):
        self.log = log_callback or (lambda msg: None)

    # ── public API ──────────────────────────────────────────────────────────

    def parse_file(self, filepath: str) -> List[Segment]:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except Exception as e:
            self.log(f"[Parser] Cannot read {filepath}: {e}")
            return []

        return self._parse_lines(lines, filepath)

    def parse_project(self, project_dir: str) -> List[Segment]:
        segments = []
        for root, dirs, files in os.walk(project_dir):
            # Skip hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fname in files:
                if fname.endswith('.rpy'):
                    fpath = os.path.join(root, fname)
                    segs = self.parse_file(fpath)
                    self.log(f"[Parser] {fpath}: {len(segs)} segments")
                    segments.extend(segs)
        return segments

    # ── internal ────────────────────────────────────────────────────────────

    def _parse_lines(self, lines: List[str], filepath: str) -> List[Segment]:
        segments: List[Segment] = []
        in_translate_block = False
        translate_lang = None
        translate_label = None
        translate_indent = ""
        last_comment_text = None
        last_comment_line = None
        in_menu = False
        menu_indent = ""

        i = 0
        while i < len(lines):
            raw = lines[i]
            stripped = raw.rstrip('\n')
            line_no = i + 1  # 1-based
            content = stripped.lstrip()

            # ── Skip blank lines & pure comments (outside translate blocks) ──
            if not content:
                i += 1
                continue

            # ── Translate block header ───────────────────────────────────────
            m = RE_TRANSLATE_HEADER.match(stripped)
            if m:
                in_translate_block = True
                translate_lang = m.group('lang')
                translate_label = m.group('label')
                translate_indent = m.group('indent')
                last_comment_text = None
                last_comment_line = None
                i += 1
                continue

            # ── Inside translate block ───────────────────────────────────────
            if in_translate_block:
                # Check if we've left the block (dedent back to header level or less)
                cur_indent = len(stripped) - len(stripped.lstrip())
                header_indent = len(translate_indent)

                if content and cur_indent <= header_indent and not content.startswith('#'):
                    # We've dedented back out — block is over
                    in_translate_block = False
                    last_comment_text = None
                    # Don't continue — fall through so the line gets processed normally
                    # (handles translate→translate transitions and new labels)

            if in_translate_block:
                # Comment line = original (do not translate)
                mc = RE_TRANSLATE_COMMENT.match(stripped)
                if mc:
                    last_comment_text = mc.group('text')
                    last_comment_line = line_no
                    i += 1
                    continue

                # Active translated line
                ma = RE_TRANSLATE_ACTIVE.match(stripped)
                if ma and ma.group('text') and not content.startswith('#'):
                    text = ma.group('text')
                    char_id = ma.group('char') if ma.group('char') and _is_valid_char_id(ma.group('char')) else None
                    seg = Segment(
                        text=text,
                        file=filepath,
                        line=line_no,
                        seg_type='translate_block',
                        indent=ma.group('indent'),
                        char_id=char_id,
                        translate_lang=translate_lang,
                        translate_label=translate_label,
                        raw_line=stripped,
                        quote_char=ma.group('q'),
                        orig_comment_line=last_comment_line,
                        context=last_comment_text,
                    )
                    segments.append(seg)
                    last_comment_text = None
                    last_comment_line = None
                i += 1
                continue

            # ── Skip dollar lines, pure comments ────────────────────────────
            if content.startswith(('$', '#', '//')):
                i += 1
                continue

            # ── Menu detection ───────────────────────────────────────────────
            if re.match(r'^\s*menu\s*:', stripped) or re.match(r'^\s*menu\s+\w+\s*:', stripped):
                in_menu = True
                menu_indent = re.match(r'^(\s*)', stripped).group(1)
                i += 1
                continue

            # Exit menu if we're back at or before menu indent
            if in_menu:
                cur_indent = len(stripped) - len(stripped.lstrip())
                menu_base = len(menu_indent)
                if content and cur_indent <= menu_base:
                    in_menu = False
                    # fall through

            if in_menu:
                # Menu choice line: "Choice":
                mc = RE_MENU_CHOICE.match(stripped)
                if mc and mc.group('text').strip():
                    seg = Segment(
                        text=mc.group('text'),
                        file=filepath,
                        line=line_no,
                        seg_type='menu',
                        indent=mc.group('indent'),
                        raw_line=stripped,
                        quote_char=mc.group('q'),
                    )
                    segments.append(seg)
                i += 1
                continue

            # ── Screen / UI text ─────────────────────────────────────────────
            mu = RE_UI_TEXT.match(stripped)
            if mu and mu.group('text').strip():
                seg = Segment(
                    text=mu.group('text'),
                    file=filepath,
                    line=line_no,
                    seg_type='ui',
                    indent=mu.group('indent'),
                    raw_line=stripped,
                    quote_char=mu.group('q'),
                    context=mu.group('kw'),
                )
                segments.append(seg)
                i += 1
                continue

            # ── Dialogue ─────────────────────────────────────────────────────
            md = RE_DIALOGUE.match(stripped)
            if md and _is_valid_char_id(md.group('char')) and md.group('text').strip():
                seg = Segment(
                    text=md.group('text'),
                    file=filepath,
                    line=line_no,
                    seg_type='dialogue',
                    indent=md.group('indent'),
                    char_id=md.group('char'),
                    raw_line=stripped,
                    quote_char=md.group('q'),
                )
                segments.append(seg)
                i += 1
                continue

            # ── Narration ────────────────────────────────────────────────────
            mn = RE_NARRATION.match(stripped)
            if mn and mn.group('text').strip():
                seg = Segment(
                    text=mn.group('text'),
                    file=filepath,
                    line=line_no,
                    seg_type='narration',
                    indent=mn.group('indent'),
                    raw_line=stripped,
                    quote_char=mn.group('q'),
                )
                segments.append(seg)
                i += 1
                continue

            i += 1

        return segments
