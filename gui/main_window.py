"""
Ren'Py Translator Pro — GUI principal con CustomTkinter.
Soporte para: carpeta, .zip, y selección directa del .exe del juego.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from utils.config import load_config, save_config
from utils.zip_handler import extract_zip, cleanup_temp
from utils.exe_detector import (
    find_project_from_exe, get_game_name_from_exe,
    collect_rpy_files, preview_rpy_stats, is_likely_renpy_exe,
)
from engines.registry import ENGINE_NAMES, get_engine
from core.translator import Translator

APP_VERSION = "2.0.0"

LANGUAGES = [
    "Spanish", "French", "German", "Italian", "Portuguese",
    "Russian", "Japanese", "Chinese", "Korean", "Arabic",
    "Dutch", "Polish", "Turkish", "Hindi", "Vietnamese",
    "Indonesian", "Thai", "Czech", "Swedish", "Danish",
    "Finnish", "Hungarian", "Romanian", "Ukrainian", "Greek",
    "Bulgarian", "Croatian", "Slovak", "Slovenian",
]

TYPE_COLORS = {
    "dialogue":       "#4fc3f7",
    "narration":      "#a5d6a7",
    "menu":           "#ffcc80",
    "ui":             "#ce93d8",
    "translate_block":"#90caf9",
}


# ─────────────────────────────────────────────────────────────────────────────
# Ventana de Configuración
# ─────────────────────────────────────────────────────────────────────────────

class SettingsWindow(ctk.CTkToplevel):

    def __init__(self, parent, config: dict, on_save):
        super().__init__(parent)
        self.title("⚙  Configuración — Ren'Py Translator Pro")
        self.geometry("520x580")
        self.resizable(False, False)
        self.grab_set()
        self.config_data = dict(config)
        self.on_save = on_save
        self._build()

    def _build(self):
        pad = {"padx": 20, "pady": 5}
        ctk.CTkLabel(self, text="API Keys y Preferencias",
                     font=ctk.CTkFont(size=17, weight="bold")).pack(padx=20, pady=(18,6))

        fields = [
            ("Google Gemini API Key (gratis):", "gemini_api_key"),
            ("OpenAI API Key:",                 "openai_api_key"),
            ("DeepL API Key:",                  "deepl_api_key"),
            ("LibreTranslate URL:",             "libre_url"),
            ("LibreTranslate API Key:",         "libre_api_key"),
        ]
        self._vars = {}
        for label, key in fields:
            ctk.CTkLabel(self, text=label, anchor="w").pack(**pad, fill="x")
            show = "*" if "key" in key.lower() else ""
            var = ctk.StringVar(value=self.config_data.get(key, ""))
            ctk.CTkEntry(self, textvariable=var, width=460, show=show).pack(**pad)
            self._vars[key] = var

        ctk.CTkLabel(self, text="Motor por defecto:", anchor="w").pack(**pad, fill="x")
        self._engine_var = ctk.StringVar(value=self.config_data.get("default_engine", ENGINE_NAMES[0]))
        ctk.CTkOptionMenu(self, variable=self._engine_var,
                          values=ENGINE_NAMES, width=460).pack(**pad)

        ctk.CTkButton(self, text="💾  Guardar", width=200, height=38,
                      command=self._save).pack(pady=22)

    def _save(self):
        for key, var in self._vars.items():
            self.config_data[key] = var.get().strip()
        self.config_data["default_engine"] = self._engine_var.get()
        save_config(self.config_data)
        self.on_save(self.config_data)
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Ventana de Preview de archivos
# ─────────────────────────────────────────────────────────────────────────────

class FilePreviewWindow(ctk.CTkToplevel):
    """Muestra todos los .rpy detectados antes de extraer."""

    def __init__(self, parent, stats: dict, on_confirm):
        super().__init__(parent)
        self.title("📂  Archivos .rpy detectados")
        self.geometry("640x480")
        self.grab_set()
        self.on_confirm = on_confirm
        self._build(stats)

    def _build(self, stats):
        ctk.CTkLabel(
            self,
            text=f"Se encontraron {stats['total_files']} archivos .rpy "
                 f"({stats['total_lines']:,} líneas en total)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=16, pady=(16, 6))

        box = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Courier New", size=11))
        box.pack(fill="both", expand=True, padx=16, pady=4)
        box.configure(state="normal")
        for f in stats["files"]:
            box.insert("end", f"  {f['lines']:>5} líneas  {f['name']}\n")
        box.configure(state="disabled")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=12)
        ctk.CTkButton(btn_frame, text="✅  Continuar con estos archivos",
                      width=240, command=self._confirm).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="✖  Cancelar",
                      width=120, fg_color="#7a1c1c",
                      command=self.destroy).pack(side="left", padx=8)

    def _confirm(self):
        self.on_confirm()
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Ventana principal
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(ctk.CTk):

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(f"🎮  Ren'Py Translator Pro  v{APP_VERSION}")
        self.geometry("1000x740")
        self.minsize(820, 600)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.config_data = load_config()

        # Estado
        self.project_dir: str = ""
        self.script_dir: str = ""    # game/ o carpeta con .rpy
        self.output_dir: str = ""
        self.temp_dir: str = ""
        self.rpy_files: list = []    # lista de .rpy detectados
        self.segments = []
        self.translations = {}
        self._running = False
        self._translator_obj = None

        self._build_ui()
        self._log(f"Ren'Py Translator Pro v{APP_VERSION} listo.")
        self._log("Selecciona el .exe del juego, una carpeta o un .zip para empezar.")

    # ── Construcción UI ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Barra superior
        top = ctk.CTkFrame(self, corner_radius=0, height=52)
        top.pack(fill="x")
        ctk.CTkLabel(top, text="🎮  Ren'Py Translator Pro",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=20, pady=12)
        ctk.CTkButton(top, text="⚙  Ajustes", width=110, height=32,
                      command=self._open_settings).pack(side="right", padx=16, pady=10)

        # Cuerpo
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=(6, 0))

        left = ctk.CTkFrame(body, width=330)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        right = ctk.CTkFrame(body)
        right.pack(side="left", fill="both", expand=True)

        self._build_left(left)
        self._build_right(right)

        # Barra de estado
        self.status_var = tk.StringVar(value="Listo")
        sb = ctk.CTkFrame(self, corner_radius=0, height=26)
        sb.pack(fill="x", side="bottom")
        ctk.CTkLabel(sb, textvariable=self.status_var,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=12)

    def _build_left(self, parent):
        pad = {"padx": 12, "pady": 4}

        # ── Selección de proyecto ─────────────────────────────────────────────
        self._section(parent, "📁  Proyecto")

        # Botón EXE — el más prominente
        ctk.CTkButton(
            parent,
            text="🎮  Seleccionar .exe del juego",
            width=290, height=42,
            fg_color="#1565c0", hover_color="#1976d2",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._select_exe,
        ).pack(**pad)

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(**pad, fill="x")
        ctk.CTkButton(btn_row, text="📂 Carpeta", width=136,
                      command=self._select_folder).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_row, text="🗜 ZIP", width=136,
                      command=self._select_zip).pack(side="left")

        self.proj_label = ctk.CTkLabel(
            parent, text="Ningún proyecto seleccionado",
            font=ctk.CTkFont(size=11), text_color="#78909c", wraplength=290,
        )
        self.proj_label.pack(**pad, anchor="w")

        # Archivos detectados
        self.files_label = ctk.CTkLabel(
            parent, text="",
            font=ctk.CTkFont(size=11), text_color="#4fc3f7", wraplength=290,
        )
        self.files_label.pack(**pad, anchor="w")

        ctk.CTkButton(parent, text="🔍  Ver archivos detectados", width=290, height=28,
                      command=self._show_file_preview).pack(**pad)

        # ── Carpeta de salida ─────────────────────────────────────────────────
        self._section(parent, "💾  Carpeta de salida")
        self.out_label = ctk.CTkLabel(
            parent, text="Automática (junto al juego)",
            font=ctk.CTkFont(size=11), text_color="#78909c", wraplength=290,
        )
        self.out_label.pack(**pad, anchor="w")
        ctk.CTkButton(parent, text="📂 Cambiar salida", width=290,
                      command=self._select_output).pack(**pad)

        # ── Motor y lengua ────────────────────────────────────────────────────
        self._section(parent, "🌐  Traducción")

        ctk.CTkLabel(parent, text="Motor:", font=ctk.CTkFont(size=12)).pack(**pad, anchor="w")
        self.engine_var = ctk.StringVar(
            value=self.config_data.get("default_engine", ENGINE_NAMES[0]))
        ctk.CTkOptionMenu(parent, variable=self.engine_var,
                          values=ENGINE_NAMES, width=290).pack(**pad)

        ctk.CTkLabel(parent, text="Idioma de destino:", font=ctk.CTkFont(size=12)).pack(**pad, anchor="w")
        self.lang_var = ctk.StringVar(
            value=self.config_data.get("default_target_lang", "Spanish"))
        ctk.CTkOptionMenu(parent, variable=self.lang_var,
                          values=LANGUAGES, width=290).pack(**pad)

        # ── Controles ─────────────────────────────────────────────────────────
        self._section(parent, "🎬  Controles")

        ctk.CTkButton(parent, text="1.  Extraer texto", width=290, height=34,
                      command=self._run_extract).pack(**pad)
        ctk.CTkButton(parent, text="2.  Traducir", width=290, height=34,
                      command=self._run_translate).pack(**pad)
        ctk.CTkButton(parent, text="3.  Aplicar traducción", width=290, height=34,
                      command=self._run_apply).pack(**pad)

        ctk.CTkButton(
            parent,
            text="⚡  Auto completo (Recomendado)",
            width=290, height=46,
            fg_color="#1b5e20", hover_color="#2e7d32",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._run_full,
        ).pack(padx=12, pady=(10, 4))

        self.cancel_btn = ctk.CTkButton(
            parent, text="⏹  Cancelar", width=290, height=30,
            fg_color="#7a1c1c", hover_color="#b71c1c",
            command=self._cancel, state="disabled",
        )
        self.cancel_btn.pack(**pad)

    def _build_right(self, parent):
        # ── Progreso ──────────────────────────────────────────────────────────
        pf = ctk.CTkFrame(parent)
        pf.pack(fill="x", padx=8, pady=(8, 4))
        self.progress_label = ctk.CTkLabel(
            pf, text="Progreso: —", font=ctk.CTkFont(size=12))
        self.progress_label.pack(anchor="w", padx=12, pady=(8, 2))
        self.progress_bar = ctk.CTkProgressBar(pf)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 8))

        # ── Stats ─────────────────────────────────────────────────────────────
        sf = ctk.CTkFrame(parent, fg_color="transparent")
        sf.pack(fill="x", padx=8, pady=2)
        self.stat_files  = ctk.CTkLabel(sf, text="Archivos: 0",  font=ctk.CTkFont(size=11), text_color="gray")
        self.stat_segs   = ctk.CTkLabel(sf, text="Segmentos: 0", font=ctk.CTkFont(size=11), text_color="gray")
        self.stat_trans  = ctk.CTkLabel(sf, text="Traducidos: 0",font=ctk.CTkFont(size=11), text_color="gray")
        self.stat_cache  = ctk.CTkLabel(sf, text="Caché: 0",     font=ctk.CTkFont(size=11), text_color="gray")
        for w in (self.stat_files, self.stat_segs, self.stat_trans, self.stat_cache):
            w.pack(side="left", padx=10)

        # ── Tabla de segmentos ────────────────────────────────────────────────
        seg_header = ctk.CTkFrame(parent, fg_color="transparent")
        seg_header.pack(fill="x", padx=8, pady=(10, 0))
        ctk.CTkLabel(seg_header, text="📋  Segmentos extraídos",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        self.seg_count_label = ctk.CTkLabel(
            seg_header, text="", font=ctk.CTkFont(size=11), text_color="#4fc3f7")
        self.seg_count_label.pack(side="left", padx=8)

        # Filtro por tipo
        filter_frame = ctk.CTkFrame(parent, fg_color="transparent")
        filter_frame.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(filter_frame, text="Filtrar:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.filter_var = ctk.StringVar(value="Todos")
        filter_opts = ["Todos", "dialogue", "narration", "menu", "ui", "translate_block"]
        ctk.CTkOptionMenu(filter_frame, variable=self.filter_var, values=filter_opts,
                          width=160, command=self._apply_filter).pack(side="left", padx=6)
        ctk.CTkButton(filter_frame, text="Limpiar logs", width=90, height=24,
                      command=self._clear_log).pack(side="right", padx=8)

        # Tabla (Textbox simulada con columnas)
        self.seg_box = ctk.CTkTextbox(
            parent, font=ctk.CTkFont(family="Courier New", size=11), height=180)
        self.seg_box.pack(fill="x", padx=8, pady=(2, 4))
        self.seg_box.configure(state="disabled")

        # ── Log ───────────────────────────────────────────────────────────────
        ctk.CTkLabel(parent, text="📝  Log",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(6,0))
        self.log_box = ctk.CTkTextbox(
            parent, font=ctk.CTkFont(family="Courier New", size=11))
        self.log_box.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        self.log_box.configure(state="disabled")

    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
            padx=12, pady=(14, 2), anchor="w")

    # ── Selección de proyecto ─────────────────────────────────────────────────

    def _select_exe(self):
        """Seleccionar el .exe del juego — detecta automáticamente la carpeta game/."""
        path = filedialog.askopenfilename(
            title="Selecciona el .exe del juego Ren'Py",
            filetypes=[
                ("Ejecutables Ren'Py", "*.exe *.sh *.app"),
                ("Ejecutable Windows", "*.exe"),
                ("Todos los archivos", "*.*"),
            ],
        )
        if not path:
            return

        self._cleanup_temp()
        self._log(f"[EXE] Seleccionado: {path}")

        # Detectar automáticamente la carpeta del proyecto
        project_root, script_dir, rpy_files = find_project_from_exe(path, log=self._log)

        if not rpy_files:
            # Puede que no tenga .rpy pero sí .rpyc — aviso
            messagebox.showwarning(
                "Sin archivos .rpy",
                "No se encontraron archivos .rpy en este juego.\n\n"
                "Nota: Los juegos distribuidos solo incluyen archivos .rpyc (compilados).\n"
                "Necesitas el código fuente .rpy del juego para traducirlo."
            )
            return

        game_name = get_game_name_from_exe(path)
        self.project_dir = project_root
        self.script_dir  = script_dir
        self.rpy_files   = rpy_files

        self.proj_label.configure(text=f"🎮 {game_name}")
        self._update_files_label()
        self._auto_set_output(project_root, suffix="_traducido")

        # Mostrar preview de archivos detectados
        stats = preview_rpy_stats(rpy_files)
        self._log(f"[EXE] Juego: {game_name}")
        self._log(f"[EXE] Scripts en: {script_dir}")
        self._log(f"[EXE] Archivos .rpy: {len(rpy_files)}")
        self._log(f"[EXE] Líneas totales: {stats['total_lines']:,}")

        # Mostrar ventana de preview
        FilePreviewWindow(self, stats, on_confirm=lambda: self._log("[EXE] Listo para extraer."))

    def _select_folder(self):
        path = filedialog.askdirectory(title="Selecciona la carpeta del proyecto Ren'Py")
        if not path:
            return
        self._cleanup_temp()
        self.project_dir = path
        self.script_dir  = path
        self.rpy_files   = collect_rpy_files(path)
        self.proj_label.configure(text=os.path.basename(path))
        self._update_files_label()
        self._auto_set_output(path)
        self.segments = []
        self.translations = {}
        self._log(f"[Carpeta] {path} — {len(self.rpy_files)} archivos .rpy")

    def _select_zip(self):
        path = filedialog.askopenfilename(
            title="Selecciona el ZIP del proyecto",
            filetypes=[("ZIP", "*.zip"), ("Todos", "*.*")],
        )
        if not path:
            return
        self._cleanup_temp()
        self._log(f"[ZIP] Extrayendo: {path}")
        try:
            extracted = extract_zip(path, log=self._log)
            self.temp_dir    = extracted
            self.project_dir = extracted
            self.script_dir  = extracted
            self.rpy_files   = collect_rpy_files(extracted)
            name = os.path.splitext(os.path.basename(path))[0]
            self.proj_label.configure(text=f"{name} (ZIP)")
            self._update_files_label()
            self._auto_set_output(path, suffix="_traducido")
            self.segments = []
            self.translations = {}
            self._log(f"[ZIP] Extraído — {len(self.rpy_files)} archivos .rpy")
        except Exception as e:
            messagebox.showerror("Error ZIP", str(e))

    def _select_output(self):
        path = filedialog.askdirectory(title="Selecciona carpeta de salida")
        if path:
            self.output_dir = path
            self.out_label.configure(text=path)

    def _auto_set_output(self, source_path: str, suffix: str = "_traducido"):
        parent = os.path.dirname(source_path)
        name   = os.path.splitext(os.path.basename(source_path))[0]
        self.output_dir = os.path.join(parent, name + suffix)
        self.out_label.configure(text=self.output_dir)

    def _update_files_label(self):
        n = len(self.rpy_files)
        if n == 0:
            self.files_label.configure(text="⚠ Sin archivos .rpy", text_color="#ef9a9a")
        else:
            self.files_label.configure(
                text=f"✓ {n} archivo{'s' if n!=1 else ''} .rpy detectado{'s' if n!=1 else ''}",
                text_color="#4fc3f7")
        self.stat_files.configure(text=f"Archivos: {n}")

    def _show_file_preview(self):
        if not self.rpy_files:
            messagebox.showinfo("Sin archivos", "Primero selecciona un proyecto.")
            return
        stats = preview_rpy_stats(self.rpy_files)
        FilePreviewWindow(self, stats, on_confirm=lambda: None)

    # ── Ajustes ───────────────────────────────────────────────────────────────

    def _open_settings(self):
        SettingsWindow(self, self.config_data, on_save=self._on_settings_saved)

    def _on_settings_saved(self, new_config):
        self.config_data = new_config
        self._log("[Config] Ajustes guardados.")

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def _run_extract(self):
        if not self._check_project(): return
        self._start_thread(self._do_extract)

    def _run_translate(self):
        if not self.segments:
            messagebox.showinfo("Primero extrae", "Haz clic en 'Extraer texto' primero.")
            return
        self._start_thread(self._do_translate)

    def _run_apply(self):
        if not self.translations:
            messagebox.showinfo("Primero traduce", "Haz clic en 'Traducir' primero.")
            return
        self._start_thread(self._do_apply)

    def _run_full(self):
        if not self._check_project(): return
        self._start_thread(self._do_full)

    def _cancel(self):
        if self._running and self._translator_obj:
            self._translator_obj.cancel()
            self._log("[Cancel] Cancelando...")

    def _start_thread(self, fn):
        if self._running:
            messagebox.showwarning("Ocupado", "Ya hay una tarea en curso.")
            return
        self._running = True
        self.cancel_btn.configure(state="normal")
        threading.Thread(target=fn, daemon=True).start()

    def _finish_thread(self):
        self._running = False
        self.after(0, lambda: self.cancel_btn.configure(state="disabled"))

    # ── Workers ───────────────────────────────────────────────────────────────

    def _do_extract(self):
        try:
            t = self._make_translator()
            self._set_status("Extrayendo texto...")
            self._set_progress(0.05, "Escaneando archivos...")

            # Usar la lista de .rpy ya detectada si está disponible
            if self.rpy_files:
                from core.parser import RenpyParser
                parser = RenpyParser(log_callback=self._log)
                self.segments = []
                total = len(self.rpy_files)
                for i, fpath in enumerate(self.rpy_files, 1):
                    segs = parser.parse_file(fpath)
                    self.segments.extend(segs)
                    self._set_progress(i / total * 0.9, f"Analizando {i}/{total} archivos...")
            else:
                self.segments = t.extract(self.script_dir or self.project_dir)

            n = len(self.segments)
            self._log(f"[Extraer] ✓ {n} segmentos encontrados")
            self._refresh_segment_table()
            self._update_stats()
            self._set_status(f"Extraídos {n} segmentos.")
            self._set_progress(1.0, f"✓ {n} segmentos")
        except Exception as e:
            self._log(f"[Extraer] Error: {e}")
            self._set_status("Error al extraer.")
        finally:
            self._finish_thread()

    def _do_translate(self):
        try:
            t = self._make_translator()
            engine = self._make_engine()
            if not engine: return
            lang = self.lang_var.get()
            self._set_status(f"Traduciendo al {lang}...")
            self.translations = t.translate(self.segments, engine, lang)
            n = len(self.translations)
            self._log(f"[Traducir] ✓ {n} traducciones producidas")
            self._update_stats()
            self._set_status(f"Traducidos {n}/{len(self.segments)} segmentos.")
        except Exception as e:
            self._log(f"[Traducir] Error: {e}")
            self._set_status("Error al traducir.")
        finally:
            self._finish_thread()

    def _do_apply(self):
        try:
            t = self._make_translator()
            self._set_status("Aplicando traducciones...")
            src = self.script_dir or self.project_dir
            count = t.apply(self.segments, self.translations, src, self.output_dir)
            self._log(f"[Aplicar] ✓ {count} líneas modificadas → {self.output_dir}")
            self._set_status(f"✓ Listo. Salida: {self.output_dir}")
            self._set_progress(1.0, "✓ Aplicado")
            self.after(0, lambda: messagebox.showinfo(
                "¡Listo!",
                f"✓ Traducción aplicada\n\n"
                f"Líneas modificadas: {count}\n"
                f"Carpeta de salida:\n{self.output_dir}"
            ))
        except Exception as e:
            self._log(f"[Aplicar] Error: {e}")
            self._set_status("Error al aplicar.")
        finally:
            self._finish_thread()

    def _do_full(self):
        try:
            t = self._make_translator()
            engine = self._make_engine()
            if not engine: return
            lang = self.lang_var.get()

            # Paso 1: Extraer
            self._log("[Auto] 1/3 Extrayendo...")
            self._set_progress(0.02, "Extrayendo...")
            if self.rpy_files:
                from core.parser import RenpyParser
                parser = RenpyParser(log_callback=self._log)
                self.segments = []
                total = len(self.rpy_files)
                for i, fpath in enumerate(self.rpy_files, 1):
                    segs = parser.parse_file(fpath)
                    self.segments.extend(segs)
                    self._set_progress(0.02 + (i/total)*0.28, f"Analizando {i}/{total}...")
            else:
                self.segments = t.extract(self.script_dir or self.project_dir)

            n = len(self.segments)
            self._log(f"[Auto] Encontrados {n} segmentos")
            self._refresh_segment_table()
            self._update_stats()

            if not self.segments:
                self._log("[Auto] Sin texto que traducir.")
                self._set_status("No se encontró texto traducible.")
                return

            # Paso 2: Traducir
            self._log(f"[Auto] 2/3 Traduciendo al {lang}...")
            self.translations = t.translate(self.segments, engine, lang)
            self._update_stats()

            # Paso 3: Aplicar
            self._log("[Auto] 3/3 Aplicando...")
            self._set_progress(0.95, "Aplicando...")
            src = self.script_dir or self.project_dir
            count = t.apply(self.segments, self.translations, src, self.output_dir)

            self._set_progress(1.0, "✓ Completo")
            self._log(f"[Auto] ✓ Terminado. {count} líneas modificadas.")
            self._set_status(f"✓ Completo — {self.output_dir}")
            self.after(0, lambda: messagebox.showinfo(
                "¡Traducción completa!",
                f"✅ El juego ha sido traducido\n\n"
                f"Segmentos encontrados: {n}\n"
                f"Traducciones aplicadas: {count}\n\n"
                f"Carpeta de salida:\n{self.output_dir}"
            ))
        except Exception as e:
            import traceback
            self._log(f"[Auto] Error fatal: {e}")
            self._log(traceback.format_exc())
            self._set_status("Error en el pipeline.")
        finally:
            self._finish_thread()

    # ── Tabla de segmentos ────────────────────────────────────────────────────

    def _refresh_segment_table(self, filter_type: str = "Todos"):
        segs = self.segments
        if filter_type != "Todos":
            segs = [s for s in segs if s.seg_type == filter_type]

        self.seg_box.configure(state="normal")
        self.seg_box.delete("1.0", "end")

        header = f"{'TIPO':<16} {'LÍNEA':>5}  {'TEXTO'}\n"
        self.seg_box.insert("end", header)
        self.seg_box.insert("end", "─" * 72 + "\n")

        shown = 0
        for seg in segs[:500]:  # máx 500 en la tabla
            tipo  = seg.seg_type[:14]
            texto = seg.text[:60].replace('\n', '↵')
            fname = os.path.basename(seg.file)
            line  = f"{tipo:<16} {seg.line:>5}  {texto}\n"
            self.seg_box.insert("end", line)
            shown += 1

        if len(segs) > 500:
            self.seg_box.insert("end", f"\n  ... y {len(segs)-500} más\n")

        self.seg_box.configure(state="disabled")
        self.seg_count_label.configure(
            text=f"({len(segs)} segmentos{' filtrados' if filter_type!='Todos' else ''})"
        )

    def _apply_filter(self, value: str):
        if self.segments:
            self._refresh_segment_table(value)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _check_project(self) -> bool:
        if not self.project_dir:
            messagebox.showwarning(
                "Sin proyecto",
                "Selecciona el .exe del juego, una carpeta o un .zip primero."
            )
            return False
        src = self.script_dir or self.project_dir
        if not os.path.isdir(src):
            messagebox.showerror("No encontrado", f"La carpeta no existe:\n{src}")
            return False
        return True

    def _make_translator(self) -> Translator:
        t = Translator(
            config=self.config_data,
            log_callback=self._log,
            progress_callback=self._on_progress,
        )
        self._translator_obj = t
        return t

    def _make_engine(self):
        name = self.engine_var.get()
        try:
            engine = get_engine(name, self.config_data)
        except Exception as e:
            self._log(f"[Motor] Error: {e}")
            messagebox.showerror("Error de motor", str(e))
            self._finish_thread()
            return None

        if not engine.is_available:
            if engine.requires_api_key:
                self.after(0, lambda: messagebox.showwarning(
                    "API Key requerida",
                    f"{name} necesita una API key.\n"
                    "Abre ⚙ Ajustes y añade tu clave."
                ))
            else:
                # Para Argos: intentar instalar el pack automáticamente
                if "Argos" in name:
                    self._log("[Argos] Intentando instalar pack de idioma...")
                    engine.ensure_language_pack(self.lang_var.get(), log=self._log)
                    if not engine.is_available:
                        self.after(0, lambda: messagebox.showwarning(
                            "Motor no disponible",
                            f"Instala: pip install argostranslate"
                        ))
                        self._finish_thread()
                        return None
                else:
                    self.after(0, lambda: messagebox.showwarning(
                        "Motor no disponible",
                        f"{name} no está disponible.\n"
                        "Revisa que el paquete esté instalado."
                    ))
                    self._finish_thread()
                    return None
        return engine

    def _on_progress(self, current: int, total: int):
        if total > 0:
            self._set_progress(current / total, f"{current}/{total}")

    def _set_progress(self, value: float, label: str = ""):
        v = min(max(value, 0), 1)
        self.after(0, lambda: self.progress_bar.set(v))
        if label:
            self.after(0, lambda: self.progress_label.configure(
                text=f"Progreso: {label}"))

    def _set_status(self, text: str):
        self.after(0, lambda: self.status_var.set(text))

    def _update_stats(self):
        def _do():
            self.stat_files.configure(text=f"Archivos: {len(self.rpy_files)}")
            self.stat_segs.configure(text=f"Segmentos: {len(self.segments)}")
            self.stat_trans.configure(text=f"Traducidos: {len(self.translations)}")
            try:
                cache_size = self._translator_obj.memory.size() if self._translator_obj else 0
                self.stat_cache.configure(text=f"Caché: {cache_size}")
            except Exception:
                pass
        self.after(0, _do)

    def _log(self, message: str):
        def _do():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", message + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _do)

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.seg_box.configure(state="normal")
        self.seg_box.delete("1.0", "end")
        self.seg_box.configure(state="disabled")

    def _cleanup_temp(self):
        if self.temp_dir:
            cleanup_temp(self.temp_dir)
            self.temp_dir = ""

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno("Salir", "Hay una traducción en curso. ¿Salir de todas formas?"):
                return
        self._cleanup_temp()
        self.destroy()
