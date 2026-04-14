"""
Ren'Py Translator Pro — GUI v3.0
Implementa el mismo enfoque que Zenpy:
- Modo Zenpy: usa renpy translate para generar tl/ y traduce esos archivos
- Modo Parser: extrae texto con parser propio (fallback)
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
    collect_rpy_files, preview_rpy_stats,
)
from engines.registry import ENGINE_NAMES, get_engine
from core.translator import Translator
from core.parser import RenpyParser

APP_VERSION = "3.0.0"

LANGUAGES = [
    "Spanish", "French", "German", "Italian", "Portuguese",
    "Russian", "Japanese", "Chinese", "Korean", "Arabic",
    "Dutch", "Polish", "Turkish", "Hindi", "Vietnamese",
    "Indonesian", "Thai", "Czech", "Swedish", "Danish",
    "Finnish", "Hungarian", "Romanian", "Ukrainian", "Greek",
    "Bulgarian", "Croatian", "Slovak", "Slovenian",
]

LANG_CODES = {
    "Spanish":"spanish","French":"french","German":"german","Italian":"italian",
    "Portuguese":"portuguese","Russian":"russian","Japanese":"japanese",
    "Chinese":"schinese","Korean":"korean","Arabic":"arabic","Dutch":"dutch",
    "Polish":"polish","Turkish":"turkish","Hindi":"hindi","Vietnamese":"vietnamese",
    "Indonesian":"indonesian","Thai":"thai","Czech":"czech","Swedish":"swedish",
    "Ukrainian":"ukrainian","Greek":"greek","Romanian":"romanian",
}


# ─────────────────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────────────────

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, config, on_save):
        super().__init__(parent)
        self.title("⚙  Ajustes")
        self.geometry("520x580")
        self.resizable(False, False)
        self.grab_set()
        self.config_data = dict(config)
        self.on_save = on_save
        self._build()

    def _build(self):
        pad = {"padx": 20, "pady": 5}
        ctk.CTkLabel(self, text="API Keys y Preferencias",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(padx=20, pady=(16,6))
        fields = [
            ("Google Gemini API Key (gratis — aistudio.google.com/apikey):", "gemini_api_key"),
            ("OpenAI API Key:", "openai_api_key"),
            ("DeepL API Key:", "deepl_api_key"),
            ("LibreTranslate URL:", "libre_url"),
            ("LibreTranslate API Key (opcional):", "libre_api_key"),
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
        ctk.CTkOptionMenu(self, variable=self._engine_var, values=ENGINE_NAMES, width=460).pack(**pad)
        ctk.CTkButton(self, text="💾  Guardar", width=180, height=36, command=self._save).pack(pady=18)

    def _save(self):
        for key, var in self._vars.items():
            self.config_data[key] = var.get().strip()
        self.config_data["default_engine"] = self._engine_var.get()
        save_config(self.config_data)
        self.on_save(self.config_data)
        self.destroy()


class FilePreviewWindow(ctk.CTkToplevel):
    def __init__(self, parent, stats, on_confirm):
        super().__init__(parent)
        self.title("📂  Archivos .rpy detectados")
        self.geometry("600x420")
        self.grab_set()
        ctk.CTkLabel(self,
            text=f"{stats['total_files']} archivos  ·  {stats['total_lines']:,} líneas",
            font=ctk.CTkFont(size=14, weight="bold")).pack(padx=14, pady=(14,4))
        box = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Courier New", size=11))
        box.pack(fill="both", expand=True, padx=14, pady=4)
        box.configure(state="normal")
        for f in stats["files"]:
            box.insert("end", f"  {f['lines']:>6}  {f['name']}\n")
        box.configure(state="disabled")
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(pady=10)
        ctk.CTkButton(bf, text="✅  Continuar", width=180,
                      command=lambda: [on_confirm(), self.destroy()]).pack(side="left", padx=6)
        ctk.CTkButton(bf, text="✖  Cerrar", width=100,
                      fg_color="#7a1c1c", command=self.destroy).pack(side="left", padx=6)


# ─────────────────────────────────────────────────────────────────────────────
# Ventana principal
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(ctk.CTk):

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title(f"🎮  Ren'Py Translator Pro  v{APP_VERSION}")
        self.geometry("1080x720")
        self.minsize(900, 640)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.config_data = load_config()
        self.exe_path    = ""
        self.project_dir = ""
        self.script_dir  = ""
        self.output_dir  = ""
        self.temp_dir    = ""
        self.rpy_files   = []
        self.segments    = []
        self.translations = {}
        self._running    = False
        self._translator_obj = None

        self._build_ui()
        self._log(f"Ren'Py Translator Pro v{APP_VERSION} listo.")
        self._log("Selecciona el .exe del juego para empezar.")

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        top = ctk.CTkFrame(self, corner_radius=0, height=48)
        top.pack(fill="x")
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="🎮  Ren'Py Translator Pro",
                     font=ctk.CTkFont(size=19, weight="bold")).pack(side="left", padx=18, pady=12)
        ctk.CTkButton(top, text="⚙  Ajustes", width=100, height=30,
                      command=self._open_settings).pack(side="right", padx=14, pady=9)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(6,0))

        left = ctk.CTkScrollableFrame(body, width=310)
        left.pack(side="left", fill="y", padx=(0,8))

        right = ctk.CTkFrame(body)
        right.pack(side="left", fill="both", expand=True)

        self._build_left(left)
        self._build_right(right)

        self.status_var = tk.StringVar(value="Listo")
        sb = ctk.CTkFrame(self, corner_radius=0, height=24)
        sb.pack(fill="x", side="bottom")
        ctk.CTkLabel(sb, textvariable=self.status_var,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=10)

    def _build_left(self, p):
        W = 285

        self._sec(p, "📁  Proyecto")

        ctk.CTkButton(p, text="🎮  Seleccionar .exe del juego",
                      width=W, height=42,
                      fg_color="#1565c0", hover_color="#1976d2",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._select_exe).pack(pady=(2,4))

        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(pady=2)
        ctk.CTkButton(row, text="📂 Carpeta", width=138,
                      command=self._select_folder).pack(side="left", padx=(0,4))
        ctk.CTkButton(row, text="🗜 ZIP", width=138,
                      command=self._select_zip).pack(side="left")

        self.proj_label = ctk.CTkLabel(p, text="Ningún proyecto seleccionado",
                                       font=ctk.CTkFont(size=11), text_color="#78909c",
                                       wraplength=W)
        self.proj_label.pack(pady=(3,0))
        self.files_label = ctk.CTkLabel(p, text="", font=ctk.CTkFont(size=11),
                                        text_color="#4fc3f7", wraplength=W)
        self.files_label.pack()
        ctk.CTkButton(p, text="🔍  Ver archivos detectados", width=W, height=26,
                      command=self._show_preview).pack(pady=2)

        self._sec(p, "💾  Carpeta de salida")
        self.out_label = ctk.CTkLabel(p, text="Automática", font=ctk.CTkFont(size=11),
                                      text_color="#78909c", wraplength=W)
        self.out_label.pack(pady=(2,0))
        ctk.CTkButton(p, text="📂 Cambiar salida", width=W, height=26,
                      command=self._select_output).pack(pady=3)

        self._sec(p, "🌐  Traducción")
        ctk.CTkLabel(p, text="Motor:", font=ctk.CTkFont(size=12), anchor="w").pack(fill="x", padx=4)
        self.engine_var = ctk.StringVar(value=self.config_data.get("default_engine", ENGINE_NAMES[0]))
        ctk.CTkOptionMenu(p, variable=self.engine_var, values=ENGINE_NAMES, width=W).pack(pady=(0,4))
        ctk.CTkLabel(p, text="Idioma destino:", font=ctk.CTkFont(size=12), anchor="w").pack(fill="x", padx=4)
        self.lang_var = ctk.StringVar(value=self.config_data.get("default_target_lang", "Spanish"))
        ctk.CTkOptionMenu(p, variable=self.lang_var, values=LANGUAGES, width=W).pack(pady=(0,4))

        # ── Modo de extracción ────────────────────────────────────────────────
        self._sec(p, "⚙  Modo de extracción")
        self.mode_var = ctk.StringVar(value="zenpy")
        ctk.CTkRadioButton(p, text="🐸 Modo Zenpy (Recomendado)\nUsa renpy translate — captura TODO",
                           variable=self.mode_var, value="zenpy",
                           font=ctk.CTkFont(size=11)).pack(anchor="w", padx=8, pady=3)
        ctk.CTkRadioButton(p, text="🔍 Modo Parser\nExtracción manual de .rpy",
                           variable=self.mode_var, value="parser",
                           font=ctk.CTkFont(size=11)).pack(anchor="w", padx=8, pady=3)

        # ── Controles ─────────────────────────────────────────────────────────
        self._sec(p, "🎬  Controles")
        ctk.CTkButton(p, text="1.  Extraer texto", width=W, height=36,
                      command=self._run_extract).pack(pady=3)
        ctk.CTkButton(p, text="2.  Traducir", width=W, height=36,
                      command=self._run_translate).pack(pady=3)
        ctk.CTkButton(p, text="3.  Aplicar traducción", width=W, height=36,
                      command=self._run_apply).pack(pady=3)

        ctk.CTkButton(p, text="⚡  Auto completo (Recomendado)",
                      width=W, height=46,
                      fg_color="#1b5e20", hover_color="#2e7d32",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._run_full).pack(pady=(10,3))

        self.cancel_btn = ctk.CTkButton(
            p, text="⏹  Cancelar", width=W, height=30,
            fg_color="#7a1c1c", hover_color="#b71c1c",
            command=self._cancel, state="disabled")
        self.cancel_btn.pack(pady=3)
        ctk.CTkLabel(p, text="").pack(pady=8)

    def _build_right(self, p):
        pf = ctk.CTkFrame(p)
        pf.pack(fill="x", padx=8, pady=(8,4))
        self.progress_label = ctk.CTkLabel(pf, text="Progreso: —", font=ctk.CTkFont(size=12))
        self.progress_label.pack(anchor="w", padx=12, pady=(6,2))
        self.progress_bar = ctk.CTkProgressBar(pf)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=12, pady=(0,6))

        sf = ctk.CTkFrame(p, fg_color="transparent")
        sf.pack(fill="x", padx=8, pady=2)
        self.stat_files = ctk.CTkLabel(sf, text="Archivos: 0",   font=ctk.CTkFont(size=11), text_color="gray")
        self.stat_segs  = ctk.CTkLabel(sf, text="Segmentos: 0",  font=ctk.CTkFont(size=11), text_color="gray")
        self.stat_trans = ctk.CTkLabel(sf, text="Traducidos: 0", font=ctk.CTkFont(size=11), text_color="gray")
        self.stat_cache = ctk.CTkLabel(sf, text="Caché: 0",      font=ctk.CTkFont(size=11), text_color="gray")
        for w in (self.stat_files, self.stat_segs, self.stat_trans, self.stat_cache):
            w.pack(side="left", padx=8)

        sh = ctk.CTkFrame(p, fg_color="transparent")
        sh.pack(fill="x", padx=8, pady=(8,0))
        ctk.CTkLabel(sh, text="📋  Segmentos extraídos",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        self.seg_count_lbl = ctk.CTkLabel(sh, text="", font=ctk.CTkFont(size=11), text_color="#4fc3f7")
        self.seg_count_lbl.pack(side="left", padx=6)

        ff = ctk.CTkFrame(p, fg_color="transparent")
        ff.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(ff, text="Filtrar:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.filter_var = ctk.StringVar(value="Todos")
        ctk.CTkOptionMenu(ff, variable=self.filter_var,
                          values=["Todos","dialogue","narration","menu","ui","translate_block"],
                          width=160, command=self._apply_filter).pack(side="left", padx=6)
        ctk.CTkButton(ff, text="Limpiar log", width=90, height=24,
                      command=self._clear_log).pack(side="right", padx=4)

        self.seg_box = ctk.CTkTextbox(p, font=ctk.CTkFont(family="Courier New", size=11), height=150)
        self.seg_box.pack(fill="x", padx=8, pady=(2,4))
        self.seg_box.configure(state="disabled")

        ctk.CTkLabel(p, text="📝  Log", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(4,0))
        self.log_box = ctk.CTkTextbox(p, font=ctk.CTkFont(family="Courier New", size=11))
        self.log_box.pack(fill="both", expand=True, padx=8, pady=(2,8))
        self.log_box.configure(state="disabled")

    def _sec(self, p, text):
        ctk.CTkLabel(p, text=text, font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(12,2))

    # ── Selección ─────────────────────────────────────────────────────────────

    def _select_exe(self):
        path = filedialog.askopenfilename(
            title="Selecciona el .exe del juego Ren'Py",
            filetypes=[("Ejecutable", "*.exe *.sh"), ("Todos", "*.*")])
        if not path: return
        self._cleanup_temp()
        self.exe_path = path
        self._log(f"[EXE] {path}")
        project_root, script_dir, rpy_files = find_project_from_exe(path, log=self._log)
        if not rpy_files:
            messagebox.showwarning("Sin archivos .rpy",
                "No se encontraron archivos .rpy.\n\n"
                "Los juegos distribuidos solo incluyen .rpyc.\n"
                "Necesitas el código fuente .rpy.")
            return
        self.project_dir = project_root
        self.script_dir  = script_dir
        self.rpy_files   = rpy_files
        name = get_game_name_from_exe(path)
        self.proj_label.configure(text=f"🎮 {name}")
        self._update_files_label()
        self._auto_output(project_root, "_traducido")
        stats = preview_rpy_stats(rpy_files)
        self._log(f"[EXE] {len(rpy_files)} archivos · {stats['total_lines']:,} líneas")
        FilePreviewWindow(self, stats, on_confirm=lambda: None)

    def _select_folder(self):
        path = filedialog.askdirectory(title="Carpeta del proyecto Ren'Py")
        if not path: return
        self._cleanup_temp()
        self.project_dir = self.script_dir = path
        self.rpy_files = collect_rpy_files(path)
        self.proj_label.configure(text=os.path.basename(path))
        self._update_files_label()
        self._auto_output(path)
        self._log(f"[Carpeta] {path} — {len(self.rpy_files)} .rpy")

    def _select_zip(self):
        path = filedialog.askopenfilename(
            title="ZIP del proyecto", filetypes=[("ZIP","*.zip"),("Todos","*.*")])
        if not path: return
        self._cleanup_temp()
        try:
            extracted = extract_zip(path, log=self._log)
            self.temp_dir = extracted
            self.project_dir = self.script_dir = extracted
            self.rpy_files = collect_rpy_files(extracted)
            name = os.path.splitext(os.path.basename(path))[0]
            self.proj_label.configure(text=f"{name} (ZIP)")
            self._update_files_label()
            self._auto_output(path, "_traducido")
            self._log(f"[ZIP] {len(self.rpy_files)} .rpy extraídos")
        except Exception as e:
            messagebox.showerror("Error ZIP", str(e))

    def _select_output(self):
        path = filedialog.askdirectory(title="Carpeta de salida")
        if path:
            self.output_dir = path
            self.out_label.configure(text=path)

    def _auto_output(self, src, suffix="_traducido"):
        parent = os.path.dirname(src)
        name   = os.path.splitext(os.path.basename(src))[0]
        self.output_dir = os.path.join(parent, name + suffix)
        self.out_label.configure(text=self.output_dir)

    def _update_files_label(self):
        n = len(self.rpy_files)
        self.files_label.configure(
            text=f"✓ {n} archivo{'s' if n!=1 else ''} .rpy detectado{'s' if n!=1 else ''}",
            text_color="#4fc3f7" if n > 0 else "#ef9a9a")
        self.stat_files.configure(text=f"Archivos: {n}")

    def _show_preview(self):
        if not self.rpy_files:
            messagebox.showinfo("Sin archivos", "Selecciona un proyecto primero.")
            return
        FilePreviewWindow(self, preview_rpy_stats(self.rpy_files), on_confirm=lambda: None)

    def _open_settings(self):
        SettingsWindow(self, self.config_data,
                       on_save=lambda c: [setattr(self,'config_data',c), self._log("[Config] Guardado.")])

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def _run_extract(self):
        if not self._check(): return
        self._start(self._do_extract)

    def _run_translate(self):
        if not self.segments:
            messagebox.showinfo("Primero extrae", "Haz clic en '1. Extraer texto' primero.")
            return
        self._start(self._do_translate)

    def _run_apply(self):
        if not self.translations:
            messagebox.showinfo("Primero traduce", "Haz clic en '2. Traducir' primero.")
            return
        self._start(self._do_apply)

    def _run_full(self):
        if not self._check(): return
        self._start(self._do_full)

    def _cancel(self):
        if self._running and self._translator_obj:
            self._translator_obj.cancel()

    def _start(self, fn):
        if self._running:
            messagebox.showwarning("Ocupado", "Ya hay una tarea en curso.")
            return
        self._running = True
        self.after(0, lambda: self.cancel_btn.configure(state="normal"))
        threading.Thread(target=fn, daemon=True).start()

    def _done(self):
        self._running = False
        self.after(0, lambda: self.cancel_btn.configure(state="disabled"))

    # ── Workers ───────────────────────────────────────────────────────────────

    def _do_extract(self):
        try:
            mode = self.mode_var.get()
            self._set_status("Extrayendo...")

            if mode == "zenpy" and self.exe_path:
                self._extract_zenpy_mode()
            else:
                self._extract_parser_mode()

        except Exception as e:
            import traceback
            self._log(f"[Extraer] Error: {e}\n{traceback.format_exc()}")
        finally:
            self._done()

    def _extract_zenpy_mode(self):
        """
        Modo Zenpy: usa renpy translate para generar tl/ automáticamente.
        Si no funciona, cae al modo parser.
        """
        lang = self.lang_var.get()
        lang_code = LANG_CODES.get(lang, lang.lower())

        self._log(f"[Zenpy] Generando archivos de traducción para '{lang_code}'...")
        self._log(f"[Zenpy] Esto puede tardar unos segundos...")

        import subprocess, shutil

        game_dir = self.script_dir
        tl_dir = os.path.join(game_dir, "tl", lang_code)

        # Intentar invocar renpy translate
        success = False
        try:
            # Método: exe del juego con argumentos de Ren'Py
            project_dir = os.path.dirname(game_dir)
            cmd = [self.exe_path, project_dir, "translate", lang_code]
            self._log(f"[Zenpy] Ejecutando: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, timeout=120,
                                    cwd=os.path.dirname(self.exe_path))
            if result.returncode == 0 and os.path.isdir(tl_dir):
                success = True
                self._log(f"[Zenpy] ✓ Archivos de traducción generados en: {tl_dir}")
            else:
                out = result.stdout.decode(errors='replace')[:300]
                err = result.stderr.decode(errors='replace')[:300]
                self._log(f"[Zenpy] Salida: {out}")
                if err: self._log(f"[Zenpy] Error: {err}")
        except subprocess.TimeoutExpired:
            self._log("[Zenpy] Timeout al ejecutar el juego.")
        except Exception as e:
            self._log(f"[Zenpy] No se pudo invocar el exe: {e}")

        if success and os.path.isdir(tl_dir):
            # Parsear los archivos tl/ generados
            self._log(f"[Zenpy] Parseando archivos de tl/{lang_code}/...")
            parser = RenpyParser(log_callback=self._log)
            self.segments = []
            rpy_files = [os.path.join(tl_dir, f) for f in os.listdir(tl_dir) if f.endswith('.rpy')]
            total = len(rpy_files)
            for i, fpath in enumerate(rpy_files, 1):
                segs = parser.parse_file(fpath)
                self.segments.extend(segs)
                self._set_progress(i/total, f"{i}/{total} archivos tl/")
            n = len(self.segments)
            self._log(f"[Zenpy] ✓ {n} segmentos extraídos desde tl/")
            # Guardar el tl_dir para el apply
            self._tl_dir = tl_dir
            self._tl_lang_code = lang_code
        else:
            self._log("[Zenpy] Fallback al modo parser directo...")
            self._extract_parser_mode()
            return

        self._refresh_segtable()
        self._update_stats()
        self._set_progress(1.0, f"✓ {len(self.segments)} segmentos")
        self._set_status(f"Extraídos {len(self.segments)} segmentos (modo Zenpy).")

    def _extract_parser_mode(self):
        """Modo parser: extracción directa de los .rpy."""
        self._log("[Parser] Extrayendo texto directamente de los .rpy...")
        parser = RenpyParser(log_callback=self._log)
        self.segments = []
        files = self.rpy_files or collect_rpy_files(self.script_dir or self.project_dir)
        total = max(len(files), 1)
        for i, fpath in enumerate(files, 1):
            segs = parser.parse_file(fpath)
            self.segments.extend(segs)
            if i % 5 == 0 or i == total:
                self._set_progress(i/total * 0.95, f"{i}/{total} archivos")
        n = len(self.segments)
        self._log(f"[Parser] ✓ {n} segmentos extraídos")
        self._refresh_segtable()
        self._update_stats()
        self._set_progress(1.0, f"✓ {n} segmentos")
        self._set_status(f"Extraídos {n} segmentos (modo Parser).")

    def _do_translate(self):
        try:
            engine = self._make_engine()
            if not engine: return
            lang = self.lang_var.get()
            self._set_status(f"Traduciendo al {lang}...")
            t = self._make_translator()
            self.translations = t.translate(self.segments, engine, lang)
            n = len([v for v in self.translations.values() if v])
            self._log(f"[Traducir] ✓ {n} segmentos traducidos")
            if n == 0:
                self._log("[Traducir] ⚠ NINGÚN segmento fue traducido.")
                self._log("[Traducir] → Para Argos: descarga el pack de idioma primero")
                self._log("[Traducir] → Para Gemini/OpenAI: verifica tu API key en ⚙ Ajustes")
                self.after(0, lambda: messagebox.showwarning(
                    "Sin traducciones",
                    "No se tradujo ningún segmento.\n\n"
                    "• Argos: necesita el pack de español instalado\n"
                    "• Gemini: verifica tu API key en ⚙ Ajustes\n\n"
                    "Recomendado: usa Google Gemini (gratis)\n"
                    "Key en: aistudio.google.com/apikey"
                ))
            self._update_stats()
            self._set_status(f"Traducidos {n}/{len(self.segments)} segmentos.")
        except Exception as e:
            self._log(f"[Traducir] Error: {e}")
        finally:
            self._done()

    def _do_apply(self):
        try:
            self._set_status("Aplicando...")
            t = self._make_translator()
            src = self.script_dir or self.project_dir
            count = t.apply(self.segments, self.translations, src, self.output_dir)
            self._log(f"[Aplicar] ✓ {count} líneas modificadas → {self.output_dir}")
            self._set_progress(1.0, "✓ Listo")
            self._set_status(f"✓ Listo — {self.output_dir}")
            self.after(0, lambda: messagebox.showinfo("¡Listo!",
                f"✓ Traducción aplicada\nLíneas: {count}\n\nSalida:\n{self.output_dir}"))
        except Exception as e:
            self._log(f"[Aplicar] Error: {e}")
        finally:
            self._done()

    def _do_full(self):
        try:
            engine = self._make_engine()
            if not engine: return
            lang = self.lang_var.get()
            mode = self.mode_var.get()

            # 1. Extraer
            self._log(f"[Auto] 1/3 Extrayendo ({mode} mode)...")
            if mode == "zenpy" and self.exe_path:
                self._extract_zenpy_mode()
            else:
                self._extract_parser_mode()

            if not self.segments:
                self._set_status("Sin texto encontrado.")
                return

            n = len(self.segments)
            self._log(f"[Auto] {n} segmentos encontrados")

            # 2. Traducir
            self._log(f"[Auto] 2/3 Traduciendo al {lang}...")
            t = self._make_translator()
            self.translations = t.translate(self.segments, engine, lang)
            translated = len([v for v in self.translations.values() if v])
            self._update_stats()
            self._log(f"[Auto] {translated} traducciones producidas")

            if translated == 0:
                self._log("[Auto] ⚠ No se produjo ninguna traducción. Abortando apply.")
                self.after(0, lambda: messagebox.showwarning(
                    "Sin traducciones",
                    "No se tradujo nada.\n\n"
                    "Verifica el motor y la API key en ⚙ Ajustes.\n"
                    "Recomendado: Google Gemini (gratis)"
                ))
                return

            # 3. Aplicar
            self._log("[Auto] 3/3 Aplicando traducciones...")
            self._set_progress(0.95, "Aplicando...")
            src = self.script_dir or self.project_dir
            count = t.apply(self.segments, self.translations, src, self.output_dir)

            self._set_progress(1.0, "✓ Completo")
            self._log(f"[Auto] ✓ {count} líneas modificadas → {self.output_dir}")
            self._set_status(f"✓ Completo")
            self.after(0, lambda: messagebox.showinfo(
                "¡Traducción completa!",
                f"✅ ¡Listo!\n\n"
                f"Segmentos: {n}\n"
                f"Traducidos: {translated}\n"
                f"Líneas modificadas: {count}\n\n"
                f"Salida:\n{self.output_dir}"
            ))
        except Exception as e:
            import traceback
            self._log(f"[Auto] Error: {e}\n{traceback.format_exc()}")
            self._set_status("Error.")
        finally:
            self._done()

    # ── Tabla segmentos ───────────────────────────────────────────────────────

    def _refresh_segtable(self, ftype="Todos"):
        segs = self.segments if ftype == "Todos" else [s for s in self.segments if s.seg_type == ftype]
        self.seg_box.configure(state="normal")
        self.seg_box.delete("1.0", "end")
        self.seg_box.insert("end", f"{'TIPO':<16} {'LÍN':>5}  TEXTO\n")
        self.seg_box.insert("end", "─" * 70 + "\n")
        for seg in segs[:500]:
            txt = seg.text[:60].replace('\n','↵')
            self.seg_box.insert("end", f"{seg.seg_type:<16} {seg.line:>5}  {txt}\n")
        if len(segs) > 500:
            self.seg_box.insert("end", f"\n  ... y {len(segs)-500} más\n")
        self.seg_box.configure(state="disabled")
        self.seg_count_lbl.configure(text=f"({len(segs)} segmentos)")

    def _apply_filter(self, v):
        if self.segments: self._refresh_segtable(v)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _check(self):
        if not self.project_dir:
            messagebox.showwarning("Sin proyecto", "Selecciona el .exe, carpeta o ZIP primero.")
            return False
        return True

    def _make_translator(self):
        t = Translator(config=self.config_data, log_callback=self._log,
                       progress_callback=self._on_progress)
        self._translator_obj = t
        return t

    def _make_engine(self):
        name = self.engine_var.get()
        try:
            engine = get_engine(name, self.config_data)
        except Exception as e:
            messagebox.showerror("Error de motor", str(e))
            self._done()
            return None
        if not engine.is_available:
            if engine.requires_api_key:
                self.after(0, lambda: messagebox.showwarning(
                    "API Key requerida",
                    f"{name} necesita una API key.\n"
                    f"Abre ⚙ Ajustes y añádela.\n\n"
                    f"Gemini es gratis en: aistudio.google.com/apikey"))
                self._done()
                return None
            elif "Argos" in name:
                self._log("[Argos] Instalando pack de idioma...")
                engine.ensure_language_pack(self.lang_var.get(), log=self._log)
                if not engine.is_available:
                    self.after(0, lambda: messagebox.showwarning(
                        "Argos no disponible",
                        "Ejecuta en terminal:\npip install argostranslate\n\n"
                        "O usa Google Gemini (gratis)."))
                    self._done()
                    return None
            else:
                self.after(0, lambda: messagebox.showwarning(
                    "Motor no disponible", f"Instala el paquete para {name}"))
                self._done()
                return None
        return engine

    def _on_progress(self, current, total):
        if total > 0: self._set_progress(current/total, f"{current}/{total}")

    def _set_progress(self, v, label=""):
        self.after(0, lambda: self.progress_bar.set(min(max(v,0),1)))
        if label:
            self.after(0, lambda: self.progress_label.configure(text=f"Progreso: {label}"))

    def _set_status(self, text):
        self.after(0, lambda: self.status_var.set(text))

    def _update_stats(self):
        def _do():
            self.stat_files.configure(text=f"Archivos: {len(self.rpy_files)}")
            self.stat_segs.configure(text=f"Segmentos: {len(self.segments)}")
            n = len([v for v in self.translations.values() if v])
            self.stat_trans.configure(text=f"Traducidos: {n}")
            try:
                c = self._translator_obj.memory.size() if self._translator_obj else 0
                self.stat_cache.configure(text=f"Caché: {c}")
            except: pass
        self.after(0, _do)

    def _log(self, msg):
        def _do():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _do)

    def _clear_log(self):
        for box in (self.log_box, self.seg_box):
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.configure(state="disabled")

    def _cleanup_temp(self):
        if self.temp_dir:
            cleanup_temp(self.temp_dir)
            self.temp_dir = ""

    def _on_close(self):
        if self._running and not messagebox.askyesno("Salir","Tarea en curso. ¿Salir?"): return
        self._cleanup_temp()
        self.destroy()
