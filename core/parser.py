"""
Parser avanzado de archivos .rpy de Ren'Py.
Extrae TODOS los tipos de texto traducible:
  - Diálogos:         e "Hola"
  - Narración:        "Texto narrado"
  - Menús:            "Opción":
  - Texto UI:         text/textbutton/label/placeholder "..."
  - Bloques translate: translate spanish label_id:
  - NVL:              nvl "texto"
  - Strings con id:   old "..." / new "..."
"""

import re
import os
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


# ─────────────────────────────────────────────────────────────────────────────
# Modelo de datos
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Segment:
    text: str
    file: str
    line: int
    seg_type: str       # dialogue | narration | menu | ui | translate_block | nvl
    indent: str = ""
    context: Optional[str] = None
    char_id: Optional[str] = None
    translate_lang: Optional[str] = None
    translate_label: Optional[str] = None
    raw_line: str = ""
    quote_char: str = '"'
    orig_comment_line: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text, "file": self.file, "line": self.line,
            "type": self.seg_type, "indent": self.indent,
            "context": self.context, "char_id": self.char_id,
            "translate_lang": self.translate_lang,
            "translate_label": self.translate_label,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Expresiones regulares
# ─────────────────────────────────────────────────────────────────────────────

# Cadena entre comillas (simple o doble), acepta escapes
_QSTR = r'(?P<q>["\'])(?P<text>(?:[^"\'\\]|\\.)*)(?P=q)'

# Diálogo:  e "Hello"  /  mcth "..."  (con o sin paréntesis extra)
RE_DIALOGUE = re.compile(
    r'^(?P<indent>\s*)(?P<char>[a-zA-Z_]\w*)\s+' + _QSTR + r'\s*$'
)

# Narración pura: solo una cadena en la línea
RE_NARRATION = re.compile(
    r'^(?P<indent>\s*)' + _QSTR + r'\s*$'
)

# Opción de menú: "texto":
RE_MENU_CHOICE = re.compile(
    r'^(?P<indent>\s*)' + _QSTR + r'\s*:\s*$'
)

# Elementos UI
RE_UI = re.compile(
    r'^(?P<indent>\s*)(?P<kw>text|textbutton|label|placeholder|input_prompt|'
    r'imagebutton|hotspot)\s+' + _QSTR + r'(?P<rest>.*)$'
)

# Cabecera de bloque translate
RE_TRANSLATE_HDR = re.compile(
    r'^(?P<indent>\s*)translate\s+(?P<lang>\w+)\s+(?P<label>\S+)\s*:\s*$'
)

# Comentario original dentro de translate block: # e "texto"  o  # "texto"
RE_TRANSLATE_CMT = re.compile(
    r'^(?P<indent>\s*)#\s*(?:(?P<char>[a-zA-Z_]\w*)\s+)?' + _QSTR + r'\s*$'
)

# Línea activa dentro de translate block
RE_TRANSLATE_ACTIVE = re.compile(
    r'^(?P<indent>\s*)(?:(?P<char>[a-zA-Z_]\w*)\s+)?' + _QSTR + r'\s*$'
)

# NVL
RE_NVL = re.compile(
    r'^(?P<indent>\s*)(?P<char>[a-zA-Z_]\w*)\s+nvl\s+' + _QSTR + r'\s*$'
    r'|^(?P<indent2>\s*)nvl\s+' + _QSTR + r'\s*$'
)

# String viejo/nuevo en bloques translate string
RE_OLD_NEW = re.compile(
    r'^(?P<indent>\s*)(?P<kw>old|new)\s+' + _QSTR + r'\s*$'
)

# Palabras clave de Ren'Py que NO son IDs de personaje
_KW = {
    "menu", "label", "screen", "init", "python", "if", "elif", "else",
    "with", "show", "hide", "play", "stop", "queue", "return", "jump",
    "call", "pass", "while", "for", "define", "default", "image",
    "transform", "style", "translate", "voice", "window", "nvl",
    "scene", "pause", "renpy", "config", "persistent", "True", "False",
    "None", "not", "and", "or", "in", "is", "text", "textbutton",
    "vbox", "hbox", "frame", "add", "null", "bar", "key", "timer",
    "viewport", "side", "grid", "fixed", "button", "imagebutton",
    "hotspot", "input", "use", "at", "as", "onlayer", "zorder",
    "old", "new", "strings", "python", "early",
}

def _valid_char(name: str) -> bool:
    return (name not in _KW and
            name.lower() not in _KW and
            bool(re.match(r'^[a-zA-Z_]\w*$', name)))


# ─────────────────────────────────────────────────────────────────────────────
# Parser principal
# ─────────────────────────────────────────────────────────────────────────────

class RenpyParser:

    def __init__(self, log_callback=None):
        self.log = log_callback or (lambda m: None)

    # ── API pública ───────────────────────────────────────────────────────────

    def parse_file(self, filepath: str) -> List[Segment]:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except Exception as e:
            self.log(f"[Parser] No se puede leer {filepath}: {e}")
            return []
        return self._parse(lines, filepath)

    def parse_project(self, project_dir: str) -> List[Segment]:
        """Recorre recursivamente un directorio buscando .rpy."""
        segments = []
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fname in sorted(files):
                if fname.endswith('.rpy'):
                    fpath = os.path.join(root, fname)
                    segs = self.parse_file(fpath)
                    self.log(f"[Parser] {os.path.basename(fpath)}: {len(segs)} segmentos")
                    segments.extend(segs)
        return segments

    # ── Motor interno ─────────────────────────────────────────────────────────

    def _parse(self, lines: List[str], filepath: str) -> List[Segment]:
        segments: List[Segment] = []

        in_translate   = False
        trans_lang     = None
        trans_label    = None
        trans_indent   = ""
        last_cmt_text  = None
        last_cmt_line  = None

        in_menu        = False
        menu_indent    = ""

        in_trans_strings = False   # translate lang strings:

        i = 0
        while i < len(lines):
            raw     = lines[i]
            stripped = raw.rstrip('\n')
            line_no  = i + 1
            content  = stripped.lstrip()
            i += 1

            # ── Saltar vacías ─────────────────────────────────────────────────
            if not content:
                continue

            # ── Comentarios puros (fuera de bloque translate) ─────────────────
            if not in_translate and content.startswith('#'):
                continue

            # ── Líneas $, // ──────────────────────────────────────────────────
            if content.startswith(('$', '//')):
                continue

            # ── Cabecera de bloque translate ──────────────────────────────────
            m = RE_TRANSLATE_HDR.match(stripped)
            if m:
                in_translate   = True
                trans_lang     = m.group('lang')
                trans_label    = m.group('label')
                trans_indent   = m.group('indent')
                last_cmt_text  = None
                last_cmt_line  = None
                # "translate lang strings:" — bloque de strings
                in_trans_strings = (trans_label == 'strings')
                continue

            # ── Dentro de bloque translate ────────────────────────────────────
            if in_translate:
                cur_ind    = len(stripped) - len(stripped.lstrip())
                header_ind = len(trans_indent)

                # ¿Salimos del bloque?
                if content and cur_ind <= header_ind and not content.startswith('#'):
                    in_translate = False
                    in_trans_strings = False
                    last_cmt_text = None
                    # Caer hacia el procesamiento normal

                else:
                    # Comentario con original
                    mc = RE_TRANSLATE_CMT.match(stripped)
                    if mc:
                        last_cmt_text = mc.group('text')
                        last_cmt_line = line_no
                        continue

                    # old/new en strings block
                    mo = RE_OLD_NEW.match(stripped)
                    if mo and mo.group('kw') == 'new' and mo.group('text').strip():
                        seg = Segment(
                            text=mo.group('text'), file=filepath, line=line_no,
                            seg_type='translate_block',
                            indent=mo.group('indent'),
                            translate_lang=trans_lang,
                            translate_label=trans_label,
                            raw_line=stripped, quote_char=mo.group('q'),
                            context=last_cmt_text,
                        )
                        segments.append(seg)
                        last_cmt_text = None
                        continue

                    # Línea activa traducible
                    ma = RE_TRANSLATE_ACTIVE.match(stripped)
                    if ma and ma.group('text').strip() and not content.startswith('#'):
                        char_id = ma.group('char')
                        if char_id and not _valid_char(char_id):
                            char_id = None
                        seg = Segment(
                            text=ma.group('text'), file=filepath, line=line_no,
                            seg_type='translate_block',
                            indent=ma.group('indent'),
                            char_id=char_id,
                            translate_lang=trans_lang,
                            translate_label=trans_label,
                            raw_line=stripped, quote_char=ma.group('q'),
                            orig_comment_line=last_cmt_line,
                            context=last_cmt_text,
                        )
                        segments.append(seg)
                        last_cmt_text = None
                        last_cmt_line = None
                    continue

            # ─── Procesamiento normal (fuera de translate) ────────────────────

            # ── Detectar inicio de menú ───────────────────────────────────────
            if re.match(r'^\s*menu\b', stripped):
                in_menu    = True
                menu_indent = re.match(r'^(\s*)', stripped).group(1)
                continue

            # ── Salida de menú ────────────────────────────────────────────────
            if in_menu:
                cur_ind  = len(stripped) - len(stripped.lstrip())
                menu_ind = len(menu_indent)
                if content and cur_ind <= menu_ind:
                    in_menu = False
                    # caer hacia procesamiento normal

            if in_menu:
                mc = RE_MENU_CHOICE.match(stripped)
                if mc and mc.group('text').strip():
                    segments.append(Segment(
                        text=mc.group('text'), file=filepath, line=line_no,
                        seg_type='menu', indent=mc.group('indent'),
                        raw_line=stripped, quote_char=mc.group('q'),
                    ))
                continue

            # ── UI ────────────────────────────────────────────────────────────
            mu = RE_UI.match(stripped)
            if mu and mu.group('text').strip():
                segments.append(Segment(
                    text=mu.group('text'), file=filepath, line=line_no,
                    seg_type='ui', indent=mu.group('indent'),
                    raw_line=stripped, quote_char=mu.group('q'),
                    context=mu.group('kw'),
                ))
                continue

            # ── Diálogo ───────────────────────────────────────────────────────
            md = RE_DIALOGUE.match(stripped)
            if md and _valid_char(md.group('char')) and md.group('text').strip():
                segments.append(Segment(
                    text=md.group('text'), file=filepath, line=line_no,
                    seg_type='dialogue', indent=md.group('indent'),
                    char_id=md.group('char'),
                    raw_line=stripped, quote_char=md.group('q'),
                ))
                continue

            # ── Narración ─────────────────────────────────────────────────────
            mn = RE_NARRATION.match(stripped)
            if mn and mn.group('text').strip():
                segments.append(Segment(
                    text=mn.group('text'), file=filepath, line=line_no,
                    seg_type='narration', indent=mn.group('indent'),
                    raw_line=stripped, quote_char=mn.group('q'),
                ))
                continue

        return segments
