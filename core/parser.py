"""
Parser avanzado de archivos .rpy de Ren'Py — v3.0
Captura TODOS los textos traducibles incluyendo:
  - Diálogos:            e "Hola"
  - Narración:           "Texto"
  - Menús:               "Opción":
  - UI:                  text/textbutton/label "..."
  - Bloques translate:   translate spanish label:
  - Strings translate:   translate spanish strings: / old "x" / new "y"
  - Tags {i}{b}{size}:   preservados, no bloquean extracción
  - Líneas con extend:   extend "continuación"
  - say con atributos:   e happy "Hola"
"""

import re
import os
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


# ─────────────────────────────────────────────────────────────────────────────
# Modelo
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Segment:
    text: str
    file: str
    line: int
    seg_type: str       # dialogue | narration | menu | ui | translate_block
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
# Utilidades regex
# ─────────────────────────────────────────────────────────────────────────────

def _extract_string(line: str):
    """
    Extrae la primera cadena entre comillas de una línea.
    Soporta comillas dobles y simples, con escapes.
    Retorna (texto, quote_char, start, end) o None.
    """
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if c in ('"', "'"):
            q = c
            i += 1
            buf = []
            while i < n:
                ch = line[i]
                if ch == '\\' and i + 1 < n:
                    buf.append(ch)
                    buf.append(line[i+1])
                    i += 2
                    continue
                if ch == q:
                    return (''.join(buf), q, i - len(buf) - 1, i + 1)
                buf.append(ch)
                i += 1
            return None  # cadena sin cerrar
        i += 1
    return None


# Palabras clave que NO son personajes
_KW = {
    "if", "elif", "else", "while", "for", "pass", "return",
    "menu", "label", "screen", "init", "python", "define", "default",
    "image", "transform", "style", "translate", "voice",
    "show", "hide", "scene", "with", "play", "stop", "queue",
    "call", "jump", "window", "nvl", "pause", "renpy",
    "config", "persistent", "True", "False", "None",
    "not", "and", "or", "in", "is",
    "text", "textbutton", "label", "vbox", "hbox", "frame",
    "add", "null", "bar", "key", "timer", "viewport", "side",
    "grid", "fixed", "button", "imagebutton", "hotspot", "input",
    "use", "at", "as", "onlayer", "zorder", "old", "new",
    "strings", "early", "extend",
}

def _is_char(token: str) -> bool:
    """¿Puede ser un ID de personaje Ren'Py?"""
    return (token not in _KW and
            token.lower() not in _KW and
            bool(re.match(r'^[a-zA-Z_]\w*$', token)))
    # NOTA: NO filtramos mayúsculas — muchos juegos usan MC, V, A, B, etc.


# ─────────────────────────────────────────────────────────────────────────────
# Parser principal
# ─────────────────────────────────────────────────────────────────────────────

# Patrones clave
RE_TRANSLATE_HDR = re.compile(
    r'^(?P<indent>\s*)translate\s+(?P<lang>\w+)\s+(?P<label>\S+)\s*:\s*$'
)
RE_UI_KW = re.compile(
    r'^\s*(text|textbutton|label|placeholder|input_prompt)\s+'
)
RE_MENU = re.compile(r'^\s*menu\s*(\w+\s*)?:')
RE_COMMENT_STR = re.compile(r'^\s*#')
RE_OLD = re.compile(r'^\s*old\s+')
RE_NEW = re.compile(r'^\s*new\s+')
RE_EXTEND = re.compile(r'^\s*extend\s+')


class RenpyParser:

    def __init__(self, log_callback=None):
        self.log = log_callback or (lambda m: None)

    def parse_file(self, filepath: str) -> List[Segment]:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except Exception as e:
            self.log(f"[Parser] No se puede leer {filepath}: {e}")
            return []
        return self._parse(lines, filepath)

    def parse_project(self, project_dir: str) -> List[Segment]:
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

    def _parse(self, lines: List[str], filepath: str) -> List[Segment]:
        segments: List[Segment] = []

        in_translate   = False
        trans_lang     = None
        trans_label    = None
        trans_indent_n = 0
        last_cmt_text  = None
        last_cmt_line  = None
        in_trans_strings = False

        in_menu        = False
        menu_indent_n  = 0

        i = 0
        while i < len(lines):
            raw      = lines[i]
            stripped = raw.rstrip('\n')
            line_no  = i + 1
            content  = stripped.lstrip()
            indent_n = len(stripped) - len(content)
            i += 1

            if not content:
                continue

            # ── Cabecera translate ────────────────────────────────────────────
            m = RE_TRANSLATE_HDR.match(stripped)
            if m:
                in_translate      = True
                trans_lang        = m.group('lang')
                trans_label       = m.group('label')
                trans_indent_n    = indent_n
                last_cmt_text     = None
                last_cmt_line     = None
                in_trans_strings  = (trans_label == 'strings')
                in_menu           = False
                continue

            # ── Dentro de bloque translate ────────────────────────────────────
            if in_translate:
                # ¿Salimos? (dedent al nivel de la cabecera o menos, sin ser comentario)
                if content and indent_n <= trans_indent_n and not content.startswith('#'):
                    in_translate     = False
                    in_trans_strings = False
                    last_cmt_text    = None
                    # fall through
                else:
                    # Comentario con original
                    if content.startswith('#'):
                        # Extraer texto del comentario: # [char] "texto"
                        after_hash = content[1:].lstrip()
                        result = _extract_string(after_hash)
                        if result:
                            last_cmt_text = result[0]
                            last_cmt_line = line_no
                        continue

                    # old "texto" (solo registrar como contexto)
                    if RE_OLD.match(content):
                        result = _extract_string(content[content.index('"' if '"' in content else "'"):])
                        if result:
                            last_cmt_text = result[0]
                        continue

                    # new "texto"
                    if RE_NEW.match(content):
                        result = _extract_string(content[content.index('"' if '"' in content else "'"):])
                        if result and result[0].strip():
                            seg = Segment(
                                text=result[0], file=filepath, line=line_no,
                                seg_type='translate_block',
                                indent=' ' * indent_n,
                                translate_lang=trans_lang,
                                translate_label=trans_label,
                                raw_line=stripped,
                                quote_char=result[1],
                                context=last_cmt_text,
                            )
                            segments.append(seg)
                            last_cmt_text = None
                        continue

                    # Línea activa: [char [atribs]] "texto"
                    # Puede ser:  e "Hola"  /  e happy "Hola"  /  "Hola"
                    seg = self._parse_say_line(
                        stripped, filepath, line_no,
                        seg_type='translate_block',
                        translate_lang=trans_lang,
                        translate_label=trans_label,
                        context=last_cmt_text,
                        orig_comment_line=last_cmt_line,
                    )
                    if seg:
                        segments.append(seg)
                        last_cmt_text = None
                        last_cmt_line = None
                    continue

            # ─── Fuera de translate ───────────────────────────────────────────

            # Saltar comentarios y líneas $, //
            if content.startswith(('#', '$', '//')):
                continue

            # ── Inicio de menú ────────────────────────────────────────────────
            if RE_MENU.match(stripped):
                in_menu       = True
                menu_indent_n = indent_n
                continue

            # ── Salida de menú ────────────────────────────────────────────────
            if in_menu:
                if content and indent_n <= menu_indent_n:
                    in_menu = False
                    # fall through
                else:
                    # Opción de menú: "texto":
                    result = _extract_string(content)
                    if result and content.rstrip().endswith(':'):
                        # Es una opción de menú
                        text = result[0].strip()
                        if text and not text.startswith('{') :
                            seg = Segment(
                                text=text, file=filepath, line=line_no,
                                seg_type='menu',
                                indent=' ' * indent_n,
                                raw_line=stripped,
                                quote_char=result[1],
                            )
                            segments.append(seg)
                    continue

            # ── UI keywords ───────────────────────────────────────────────────
            if RE_UI_KW.match(stripped):
                result = _extract_string(content)
                if result and result[0].strip():
                    kw = content.split()[0]
                    seg = Segment(
                        text=result[0], file=filepath, line=line_no,
                        seg_type='ui',
                        indent=' ' * indent_n,
                        raw_line=stripped,
                        quote_char=result[1],
                        context=kw,
                    )
                    segments.append(seg)
                continue

            # ── extend "texto" ────────────────────────────────────────────────
            if RE_EXTEND.match(stripped):
                result = _extract_string(content[len('extend'):])
                if result and result[0].strip():
                    seg = Segment(
                        text=result[0], file=filepath, line=line_no,
                        seg_type='dialogue',
                        indent=' ' * indent_n,
                        raw_line=stripped,
                        quote_char=result[1],
                        char_id='extend',
                    )
                    segments.append(seg)
                continue

            # ── Diálogo / narración ───────────────────────────────────────────
            seg = self._parse_say_line(stripped, filepath, line_no)
            if seg:
                segments.append(seg)

        return segments

    def _parse_say_line(
        self, stripped: str, filepath: str, line_no: int,
        seg_type: str = None,
        translate_lang: str = None,
        translate_label: str = None,
        context: str = None,
        orig_comment_line: int = None,
    ) -> Optional[Segment]:
        """
        Intenta parsear una línea como diálogo o narración.
        Soporta:
          "texto"                    → narración
          e "texto"                  → diálogo
          e happy "texto"            → diálogo con atributo
          e happy worried "texto"    → diálogo con múltiples atributos
        """
        content = stripped.lstrip()
        indent_n = len(stripped) - len(content)

        # Prefijos que definitivamente NO son diálogo
        _SKIP = ('$', '//', '#',
                 'translate ', 'screen ', 'init ', 'init:', 'python:',
                 'python ', 'define ', 'default ', 'image ', 'transform ',
                 'style ', 'show ', 'hide ', 'scene ', 'play ', 'stop ',
                 'queue ', 'call ', 'jump ', 'return', 'pass',
                 'window ', 'pause', 'voice ', 'vbox:', 'hbox:', 'frame:',
                 'null', 'bar ', 'key ', 'timer ', 'viewport:',
                 'grid:', 'fixed:', 'button:', 'use ', 'onlayer', 'zorder',
                 'if (', 'elif ', 'else:', 'while ', 'for ',
                 'with dissolve', 'with fade', 'with None',
                 )
        if not content or any(content.startswith(s) for s in _SKIP):
            return None

        tokens = content.split()
        if not tokens:
            return None

        # Caso 1: empieza con comilla → narración
        if tokens[0].startswith(('"', "'")):
            result = _extract_string(content)
            if result and result[0].strip():
                return Segment(
                    text=result[0], file=filepath, line=line_no,
                    seg_type=seg_type or 'narration',
                    indent=' ' * indent_n,
                    raw_line=stripped,
                    quote_char=result[1],
                    translate_lang=translate_lang,
                    translate_label=translate_label,
                    context=context,
                    orig_comment_line=orig_comment_line,
                )
            return None

        # Caso 2: primer token es un identificador
        first = tokens[0]
        if not re.match(r'^[a-zA-Z_]\w*$', first):
            return None

        # Buscar la primera comilla en la línea
        result = _extract_string(content)
        if not result or not result[0].strip():
            return None

        # Verificar que lo que está antes de la cadena son solo identificadores/atributos
        before_quote = content[:result[2]].strip()
        parts = before_quote.split()

        if not parts:
            return None

        char_id = parts[0]

        # El primer token no debe ser una keyword
        if char_id.lower() in _KW:
            return None

        # Debe ser un identificador válido (permite mayúsculas: MC, V, A, B...)
        if not re.match(r'^[a-zA-Z_]\w*$', char_id):
            return None

        # Los tokens intermedios (atributos) deben ser palabras o @ - para expresiones
        for attr in parts[1:]:
            if not re.match(r'^[a-zA-Z_@\-]\w*$', attr):
                return None

        return Segment(
            text=result[0], file=filepath, line=line_no,
            seg_type=seg_type or 'dialogue',
            indent=' ' * indent_n,
            char_id=char_id,
            raw_line=stripped,
            quote_char=result[1],
            translate_lang=translate_lang,
            translate_label=translate_label,
            context=context,
            orig_comment_line=orig_comment_line,
        )
