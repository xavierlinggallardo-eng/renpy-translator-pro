"""
Extractor basado en el enfoque de Zenpy:
Usa el propio ejecutable de Ren'Py para generar archivos de traducción,
luego los traduce y los reinserta.

Flujo:
1. Invoca: MiJuego.exe translate <lang>
   → Genera game/tl/<lang>/*.rpy con todos los bloques translate
2. Parsea esos archivos generados (captura TODO el texto)
3. Traduce solo las líneas vacías (sin traducir aún)
4. Guarda de vuelta

Ventaja: captura el 100% del texto igual que Ren'Py sabe que es traducible,
incluyendo GUI, phone messages, screens, etc.
"""

import os
import re
import subprocess
import shutil
from typing import List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class TLSegment:
    """Segmento dentro de un archivo tl/<lang>/*.rpy generado por Ren'Py."""
    file: str           # path al archivo .rpy en tl/<lang>/
    line: int           # línea 1-based
    block_header: str   # "translate spanish label_0:"
    orig_comment: str   # "# e \"Hello\""  o  "# \"Narration\""
    active_line: str    # "e \"\""  o  "\"\""  (vacío = sin traducir)
    translated: str = ""  # texto traducido a insertar
    indent: str = "    "
    quote_char: str = '"'
    is_string_block: bool = False  # para translate strings


class RenpyTLExtractor:
    """
    Extractor que usa los archivos tl/ generados por Ren'Py.
    Este es el método más fiable — usa la propia lógica de Ren'Py.
    """

    def __init__(self, log=None):
        self.log = log or (lambda m: None)

    def generate_tl_files(self, exe_path: str, lang: str) -> Optional[str]:
        """
        Invoca el exe del juego con el comando translate para generar
        los archivos de traducción en game/tl/<lang>/.
        
        Retorna el path a la carpeta tl/<lang>/ o None si falla.
        """
        self.log(f"[TL] Generando archivos de traducción para '{lang}'...")
        self.log(f"[TL] Ejecutable: {exe_path}")

        game_dir = self._find_game_dir(exe_path)
        if not game_dir:
            self.log("[TL] No se encontró la carpeta game/")
            return None

        tl_dir = os.path.join(game_dir, "tl", lang)
        self.log(f"[TL] Carpeta destino: {tl_dir}")

        # Intentar ejecutar el generador nativo
        success = self._run_renpy_translate(exe_path, lang, game_dir)

        if not success or not os.path.isdir(tl_dir):
            # Fallback: generar los archivos nosotros mismos
            self.log("[TL] Generador nativo no disponible. Usando parser directo...")
            return None

        rpy_files = [f for f in os.listdir(tl_dir) if f.endswith('.rpy')]
        self.log(f"[TL] Generados {len(rpy_files)} archivos en tl/{lang}/")
        return tl_dir

    def _find_game_dir(self, exe_path: str) -> Optional[str]:
        root = os.path.dirname(os.path.abspath(exe_path))
        for candidate in ["game", "scripts", "scenario"]:
            path = os.path.join(root, candidate)
            if os.path.isdir(path):
                return path
        return root if any(f.endswith('.rpy') for f in os.listdir(root)) else None

    def _run_renpy_translate(self, exe_path: str, lang: str, game_dir: str) -> bool:
        """Intenta invocar el exe con comando de traducción."""
        try:
            # Método 1: exe directo con --translate
            result = subprocess.run(
                [exe_path, os.path.dirname(game_dir), "translate", lang],
                capture_output=True, timeout=60, cwd=os.path.dirname(exe_path)
            )
            if result.returncode == 0:
                self.log("[TL] Generación nativa exitosa.")
                return True
        except Exception as e:
            self.log(f"[TL] Método nativo falló: {e}")

        try:
            # Método 2: python renpy.py translate
            renpy_py = os.path.join(os.path.dirname(exe_path), "renpy.py")
            if os.path.exists(renpy_py):
                result = subprocess.run(
                    ["python", renpy_py, os.path.dirname(game_dir), "translate", lang],
                    capture_output=True, timeout=60
                )
                if result.returncode == 0:
                    return True
        except Exception:
            pass

        return False

    def scan_tl_dir(self, tl_dir: str) -> List[TLSegment]:
        """
        Escanea los archivos .rpy en tl/<lang>/ y extrae todos los segmentos.
        Captura tanto los ya traducidos como los vacíos.
        """
        segments = []
        for fname in sorted(os.listdir(tl_dir)):
            if not fname.endswith('.rpy'):
                continue
            fpath = os.path.join(tl_dir, fname)
            segs = self._parse_tl_file(fpath)
            segments.extend(segs)
            self.log(f"[TL] {fname}: {len(segs)} segmentos")
        return segments

    def _parse_tl_file(self, filepath: str) -> List['TLSegment']:
        """Parsea un archivo .rpy de tl/ generado por Ren'Py."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except Exception as e:
            self.log(f"[TL] Error leyendo {filepath}: {e}")
            return []

        segments = []
        i = 0
        while i < len(lines):
            line = lines[i].rstrip('\n')
            stripped = line.lstrip()

            # Buscar cabecera: translate lang label:
            if re.match(r'\s*translate\s+\w+\s+\S+\s*:', line):
                block_header = line
                i += 1
                # Leer el bloque
                comment_lines = []
                active_line = None
                indent = "    "

                while i < len(lines):
                    bl = lines[i].rstrip('\n')
                    bc = bl.lstrip()
                    cur_indent = len(bl) - len(bc)

                    if not bc:
                        i += 1
                        continue

                    # Si dedentamos al nivel de la cabecera o menos, fin del bloque
                    header_indent = len(line) - len(line.lstrip())
                    if bc and cur_indent <= header_indent and not bc.startswith('#'):
                        break

                    if bc.startswith('#'):
                        comment_lines.append(bl)
                        i += 1
                        continue

                    # Línea activa
                    active_line = bl
                    indent = ' ' * cur_indent
                    i += 1
                    break

                if active_line is not None:
                    # Extraer texto de la línea activa
                    text, qchar = self._extract_text(active_line)
                    orig_text = ""
                    if comment_lines:
                        orig_text, _ = self._extract_text(comment_lines[-1])

                    seg = TLSegment(
                        file=filepath,
                        line=i,
                        block_header=block_header,
                        orig_comment='\n'.join(comment_lines),
                        active_line=active_line,
                        translated=text,
                        indent=indent,
                        quote_char=qchar,
                    )
                    segments.append(seg)
                continue

            i += 1

        return segments

    def _extract_text(self, line: str) -> Tuple[str, str]:
        """Extrae el texto entre comillas de una línea."""
        for q in ('"', "'"):
            pattern = re.compile(
                q + r'((?:[^' + q + r'\\]|\\.)*)' + q
            )
            m = pattern.search(line)
            if m:
                return m.group(1), q
        return "", '"'

    def needs_translation(self, seg: 'TLSegment') -> bool:
        """¿Este segmento necesita ser traducido? (está vacío o igual al original)"""
        if not seg.translated.strip():
            return True
        if seg.orig_comment:
            orig, _ = self._extract_text(seg.orig_comment)
            if seg.translated.strip() == orig.strip():
                return True
        return False

    def apply_translations(
        self,
        segments: List['TLSegment'],
        translations: dict,  # TLSegment.line -> texto traducido
    ) -> int:
        """Reinserta las traducciones en los archivos tl/."""
        # Agrupar por archivo
        by_file = {}
        for seg in segments:
            by_file.setdefault(seg.file, []).append(seg)

        modified = 0
        for filepath, segs in by_file.items():
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()

                for seg in segs:
                    if seg.line not in translations:
                        continue
                    new_text = translations[seg.line]
                    if not new_text:
                        continue

                    # Reconstruir la línea activa con el nuevo texto
                    new_line = self._rebuild_line(seg.active_line, new_text, seg.quote_char)
                    if new_line:
                        idx = seg.line - 1
                        if 0 <= idx < len(lines):
                            lines[idx] = new_line + '\n'
                            modified += 1

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.writelines(lines)

            except Exception as e:
                self.log(f"[TL] Error escribiendo {filepath}: {e}")

        return modified

    def _rebuild_line(self, original: str, new_text: str, quote_char: str) -> str:
        """Reemplaza el texto en la línea manteniendo la estructura."""
        q = quote_char
        # Escapar comillas en el nuevo texto
        new_text_escaped = new_text.replace('\\', '\\\\').replace(q, '\\' + q)
        pattern = re.compile(q + r'(?:[^' + q + r'\\]|\\.)*' + q)
        result = pattern.sub(q + new_text_escaped + q, original, count=1)
        return result
