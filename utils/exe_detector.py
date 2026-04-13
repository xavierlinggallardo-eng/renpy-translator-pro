"""
Detección automática de proyectos Ren'Py desde el .exe del juego.
Replica el comportamiento de herramientas como Zenpy/RenPy Translator.

Estructura típica de un juego Ren'Py:
  MiJuego/
  ├── MiJuego.exe          ← el usuario selecciona esto
  ├── MiJuego.sh           ← (Linux/Mac)
  ├── game/                ← carpeta con los .rpy
  │   ├── script.rpy
  │   ├── screens.rpy
  │   ├── gui.rpy
  │   └── ...
  ├── renpy/               ← motor Ren'Py
  └── lib/
"""

import os
import re
from typing import Optional, List, Tuple


# Nombres de carpetas donde Ren'Py guarda los scripts
SCRIPT_DIRS = ["game", "scripts", "scenario"]

# Señales de que es una instalación Ren'Py
RENPY_MARKERS = ["renpy", "lib", "game"]


def find_project_from_exe(exe_path: str, log=None) -> Tuple[Optional[str], Optional[str], List[str]]:
    """
    Dado el path al .exe de un juego Ren'Py, devuelve:
      (project_root, script_dir, lista_rpy_files)

    - project_root: carpeta raíz del juego (donde está el .exe)
    - script_dir:   carpeta donde están los .rpy (normalmente game/)
    - rpy_files:    lista de paths absolutos a todos los .rpy encontrados
    """
    def _log(msg):
        if log:
            log(msg)

    if not exe_path or not os.path.exists(exe_path):
        _log(f"[EXE] Archivo no encontrado: {exe_path}")
        return None, None, []

    # La raíz del proyecto es la carpeta que contiene el .exe
    project_root = os.path.dirname(os.path.abspath(exe_path))
    _log(f"[EXE] Raíz del proyecto: {project_root}")

    # Verificar que parece un juego Ren'Py
    entries = set(os.listdir(project_root))
    is_renpy = any(m in entries for m in RENPY_MARKERS)
    if not is_renpy:
        # Quizás el exe está un nivel más arriba (distribución alternativa)
        parent = os.path.dirname(project_root)
        parent_entries = set(os.listdir(parent))
        if any(m in parent_entries for m in RENPY_MARKERS):
            project_root = parent
            entries = parent_entries
            _log(f"[EXE] Ajustando raíz a: {project_root}")

    # Buscar carpeta de scripts
    script_dir = None
    for candidate in SCRIPT_DIRS:
        path = os.path.join(project_root, candidate)
        if os.path.isdir(path):
            script_dir = path
            _log(f"[EXE] Carpeta de scripts: {script_dir}")
            break

    # Si no encontramos subcarpeta conocida, usar la raíz
    if script_dir is None:
        # Comprobar si hay .rpy directamente en la raíz
        rpy_in_root = [f for f in os.listdir(project_root) if f.endswith('.rpy')]
        if rpy_in_root:
            script_dir = project_root
            _log(f"[EXE] .rpy encontrados en raíz: {len(rpy_in_root)} archivos")
        else:
            _log("[EXE] No se encontró carpeta de scripts. Usando raíz del proyecto.")
            script_dir = project_root

    # Recopilar todos los .rpy recursivamente
    rpy_files = collect_rpy_files(script_dir, log=log)
    _log(f"[EXE] Total .rpy encontrados: {len(rpy_files)}")

    return project_root, script_dir, rpy_files


def collect_rpy_files(directory: str, log=None) -> List[str]:
    """Recorre recursivamente un directorio y devuelve todos los .rpy."""
    rpy_files = []
    for root, dirs, files in os.walk(directory):
        # Ignorar carpetas ocultas y cache
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__',)]
        for fname in files:
            if fname.endswith('.rpy'):
                rpy_files.append(os.path.join(root, fname))
    rpy_files.sort()
    return rpy_files


def get_game_name_from_exe(exe_path: str) -> str:
    """Extrae el nombre del juego del .exe."""
    name = os.path.splitext(os.path.basename(exe_path))[0]
    # Limpiar caracteres especiales
    name = re.sub(r'[_\-]+', ' ', name).strip()
    return name if name else "Juego Ren'Py"


def is_likely_renpy_exe(path: str) -> bool:
    """
    Heurística: comprueba si el exe probablemente es un juego Ren'Py.
    Busca la carpeta game/ o renpy/ al lado del exe.
    """
    if not path or not os.path.isfile(path):
        return False
    parent = os.path.dirname(os.path.abspath(path))
    entries = set(os.listdir(parent))
    return bool(entries & {"game", "renpy", "lib"})


def preview_rpy_stats(rpy_files: List[str]) -> dict:
    """
    Da un resumen rápido de los archivos encontrados sin parsear completo.
    Útil para mostrar al usuario antes de extraer.
    """
    stats = {
        "total_files": len(rpy_files),
        "total_lines": 0,
        "files": [],
    }
    for fpath in rpy_files:
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            stats["total_lines"] += len(lines)
            stats["files"].append({
                "name": os.path.basename(fpath),
                "path": fpath,
                "lines": len(lines),
            })
        except Exception:
            pass
    return stats
