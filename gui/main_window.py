"""
Main application window — CustomTkinter-based GUI.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# ── path fix so we can import core/engines/utils when run as script ─────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from utils.config import load_config, save_config
from engines.registry import ENGINE_NAMES, get_engine
from core.translator import Translator
from utils.zip_handler import extract_zip, cleanup_temp


LANGUAGES = [
    "Spanish", "French", "German", "Italian", "Portuguese",
    "Russian", "Japanese", "Chinese", "Korean", "Arabic",
    "Dutch", "Polish", "Turkish", "Hindi", "Vietnamese",
    "Indonesian", "Thai", "Czech", "Swedish", "Danish",
    "Finnish", "Hungarian", "Romanian", "Ukrainian", "Greek",
    "Bulgarian", "Croatian", "Slovak", "Slovenian",
]

APP_VERSION = "1.0.0"


class SettingsWindow(ctk.CTkToplevel):
    """Floating settings dialog."""

    def __init__(self, parent, config: dict, on_save):
        super().__init__(parent)
        self.title("Settings — Ren'Py Translator Pro")
        self.geometry("500x520")
        self.resizable(False, False)
        self.grab_set()

        self.config_data = dict(config)
        self.on_save = on_save

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 20, "pady": 6}

        ctk.CTkLabel(self, text="API Keys & Preferences",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(**pad, pady=(20, 4))

        # ── Gemini ──
        ctk.CTkLabel(self, text="Google Gemini API Key:").pack(**pad, anchor="w")
        self.gemini_var = ctk.StringVar(value=self.config_data.get("gemini_api_key", ""))
        ctk.CTkEntry(self, textvariable=self.gemini_var, width=440,
                     show="*").pack(**pad)

        # ── OpenAI ──
        ctk.CTkLabel(self, text="OpenAI API Key:").pack(**pad, anchor="w")
        self.openai_var = ctk.StringVar(value=self.config_data.get("openai_api_key", ""))
        ctk.CTkEntry(self, textvariable=self.openai_var, width=440,
                     show="*").pack(**pad)

        # ── DeepL ──
        ctk.CTkLabel(self, text="DeepL API Key:").pack(**pad, anchor="w")
        self.deepl_var = ctk.StringVar(value=self.config_data.get("deepl_api_key", ""))
        ctk.CTkEntry(self, textvariable=self.deepl_var, width=440,
                     show="*").pack(**pad)

        # ── LibreTranslate URL ──
        ctk.CTkLabel(self, text="LibreTranslate URL:").pack(**pad, anchor="w")
        self.libre_url_var = ctk.StringVar(value=self.config_data.get("libre_url", ""))
        ctk.CTkEntry(self, textvariable=self.libre_url_var, width=440).pack(**pad)

        # ── LibreTranslate API key ──
        ctk.CTkLabel(self, text="LibreTranslate API Key (if required):").pack(**pad, anchor="w")
        self.libre_key_var = ctk.StringVar(value=self.config_data.get("libre_api_key", ""))
        ctk.CTkEntry(self, textvariable=self.libre_key_var, width=440,
                     show="*").pack(**pad)

        # ── Default engine ──
        ctk.CTkLabel(self, text="Default Engine:").pack(**pad, anchor="w")
        self.engine_var = ctk.StringVar(value=self.config_data.get("default_engine", ENGINE_NAMES[0]))
        ctk.CTkOptionMenu(self, variable=self.engine_var,
                          values=ENGINE_NAMES, width=440).pack(**pad)

        # ── Save button ──
        ctk.CTkButton(self, text="Save Settings", command=self._save,
                      width=200, height=36).pack(pady=20)

    def _save(self):
        self.config_data["gemini_api_key"] = self.gemini_var.get().strip()
        self.config_data["openai_api_key"] = self.openai_var.get().strip()
        self.config_data["deepl_api_key"] = self.deepl_var.get().strip()
        self.config_data["libre_url"] = self.libre_url_var.get().strip()
        self.config_data["libre_api_key"] = self.libre_key_var.get().strip()
        self.config_data["default_engine"] = self.engine_var.get()
        save_config(self.config_data)
        self.on_save(self.config_data)
        self.destroy()


class MainWindow(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(f"Ren'Py Translator Pro  v{APP_VERSION}")
        self.geometry("900x720")
        self.minsize(760, 600)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.config_data = load_config()
        self.project_dir: str = ""
        self.output_dir: str = ""
        self.temp_dir: str = ""          # set if a zip was extracted
        self.segments = []
        self.translations = {}
        self._running = False

        self._build_ui()
        self._log(f"Ren'Py Translator Pro v{APP_VERSION} ready.")
        self._log("Select a Ren'Py project folder or .zip to get started.")

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────────────────────
        top_bar = ctk.CTkFrame(self, corner_radius=0, height=50)
        top_bar.pack(fill="x")
        ctk.CTkLabel(
            top_bar,
            text="🎮  Ren'Py Translator Pro",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left", padx=20, pady=10)
        ctk.CTkButton(
            top_bar, text="⚙  Settings", width=110, height=32,
            command=self._open_settings,
        ).pack(side="right", padx=16, pady=9)

        # ── Main body ────────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(8, 0))

        left = ctk.CTkFrame(body, width=320)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        right = ctk.CTkFrame(body)
        right.pack(side="left", fill="both", expand=True)

        self._build_left_panel(left)
        self._build_right_panel(right)

        # ── Status bar ───────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ctk.CTkFrame(self, corner_radius=0, height=28)
        status_bar.pack(fill="x", side="bottom")
        ctk.CTkLabel(
            status_bar, textvariable=self.status_var,
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=12)

    def _build_left_panel(self, parent):
        pad = {"padx": 12, "pady": 4}

        # ── Project section ───────────────────────────────────────────────────
        self._section_label(parent, "📁  Project")
        self.proj_label = ctk.CTkLabel(
            parent, text="No project selected",
            font=ctk.CTkFont(size=11),
            text_color="gray", wraplength=280,
        )
        self.proj_label.pack(**pad, anchor="w")

        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(**pad, fill="x")
        ctk.CTkButton(btn_frame, text="📂 Select Folder", width=130,
                      command=self._select_folder).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_frame, text="🗜 Select ZIP", width=130,
                      command=self._select_zip).pack(side="left")

        # ── Output section ────────────────────────────────────────────────────
        self._section_label(parent, "💾  Output Folder")
        self.out_label = ctk.CTkLabel(
            parent, text="Same as project (auto)",
            font=ctk.CTkFont(size=11),
            text_color="gray", wraplength=280,
        )
        self.out_label.pack(**pad, anchor="w")
        ctk.CTkButton(parent, text="📂 Select Output", width=264,
                      command=self._select_output).pack(**pad)

        # ── Translation settings ──────────────────────────────────────────────
        self._section_label(parent, "🌐  Translation Settings")

        ctk.CTkLabel(parent, text="Engine:", font=ctk.CTkFont(size=12)).pack(**pad, anchor="w")
        self.engine_var = ctk.StringVar(
            value=self.config_data.get("default_engine", ENGINE_NAMES[0])
        )
        self.engine_menu = ctk.CTkOptionMenu(
            parent, variable=self.engine_var,
            values=ENGINE_NAMES, width=264,
            command=self._on_engine_change,
        )
        self.engine_menu.pack(**pad)

        ctk.CTkLabel(parent, text="Target Language:", font=ctk.CTkFont(size=12)).pack(**pad, anchor="w")
        self.lang_var = ctk.StringVar(
            value=self.config_data.get("default_target_lang", "Spanish")
        )
        self.lang_menu = ctk.CTkOptionMenu(
            parent, variable=self.lang_var,
            values=LANGUAGES, width=264,
        )
        self.lang_menu.pack(**pad)

        # ── Controls ──────────────────────────────────────────────────────────
        self._section_label(parent, "🎬  Controls")

        ctk.CTkButton(parent, text="1. Extract Text", width=264, height=36,
                      command=self._run_extract).pack(**pad)
        ctk.CTkButton(parent, text="2. Translate", width=264, height=36,
                      command=self._run_translate).pack(**pad)
        ctk.CTkButton(parent, text="3. Apply Translation", width=264, height=36,
                      command=self._run_apply).pack(**pad)

        ctk.CTkButton(
            parent,
            text="⚡ Full Auto (Recommended)",
            width=264, height=44,
            fg_color="#1e6e2e",
            hover_color="#27933e",
            command=self._run_full,
        ).pack(padx=12, pady=(10, 4))

        self.cancel_btn = ctk.CTkButton(
            parent, text="⏹ Cancel", width=264, height=32,
            fg_color="#7a1c1c", hover_color="#a02424",
            command=self._cancel,
            state="disabled",
        )
        self.cancel_btn.pack(**pad)

    def _build_right_panel(self, parent):
        # ── Progress ─────────────────────────────────────────────────────────
        prog_frame = ctk.CTkFrame(parent)
        prog_frame.pack(fill="x", padx=8, pady=(8, 4))

        self.progress_label = ctk.CTkLabel(
            prog_frame, text="Progress: —",
            font=ctk.CTkFont(size=12),
        )
        self.progress_label.pack(anchor="w", padx=12, pady=(8, 2))

        self.progress_bar = ctk.CTkProgressBar(prog_frame, width=500)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 8))

        # ── Segment stats ─────────────────────────────────────────────────────
        stats_frame = ctk.CTkFrame(parent, fg_color="transparent")
        stats_frame.pack(fill="x", padx=8, pady=2)

        self.stat_segs = ctk.CTkLabel(stats_frame, text="Segments: 0",
                                       font=ctk.CTkFont(size=11), text_color="gray")
        self.stat_segs.pack(side="left", padx=12)
        self.stat_trans = ctk.CTkLabel(stats_frame, text="Translated: 0",
                                        font=ctk.CTkFont(size=11), text_color="gray")
        self.stat_trans.pack(side="left", padx=12)
        self.stat_cache = ctk.CTkLabel(stats_frame, text=f"Cache: {0} entries",
                                        font=ctk.CTkFont(size=11), text_color="gray")
        self.stat_cache.pack(side="left", padx=12)

        # ── Log panel ─────────────────────────────────────────────────────────
        log_header = ctk.CTkFrame(parent, fg_color="transparent")
        log_header.pack(fill="x", padx=8, pady=(8, 0))
        ctk.CTkLabel(log_header, text="📋  Logs",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkButton(log_header, text="Clear", width=60, height=24,
                      command=self._clear_log).pack(side="right", padx=8)

        self.log_box = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(family="Courier New", size=11),
            state="disabled",
            wrap="word",
        )
        self.log_box.pack(fill="both", expand=True, padx=8, pady=(4, 8))

    def _section_label(self, parent, text: str):
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(padx=12, pady=(12, 2), anchor="w")

    # ── Event handlers ───────────────────────────────────────────────────────

    def _select_folder(self):
        path = filedialog.askdirectory(title="Select Ren'Py Project Folder")
        if path:
            self._cleanup_temp()
            self.project_dir = path
            self.proj_label.configure(text=os.path.basename(path))
            self._auto_set_output(path)
            self.segments = []
            self.translations = {}
            self._log(f"Project: {path}")

    def _select_zip(self):
        path = filedialog.askopenfilename(
            title="Select Ren'Py Project ZIP",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
        )
        if path:
            self._cleanup_temp()
            self._log(f"Extracting ZIP: {path}")
            try:
                extracted = extract_zip(path, log=self._log)
                self.temp_dir = extracted
                self.project_dir = extracted
                name = os.path.splitext(os.path.basename(path))[0]
                self.proj_label.configure(text=f"{name} (from ZIP)")
                self._auto_set_output(path, suffix="_translated")
                self.segments = []
                self.translations = {}
                self._log(f"Extracted to: {extracted}")
            except Exception as e:
                messagebox.showerror("ZIP Error", str(e))

    def _select_output(self):
        path = filedialog.askdirectory(title="Select Output Folder")
        if path:
            self.output_dir = path
            self.out_label.configure(text=path)

    def _auto_set_output(self, source_path: str, suffix: str = "_translated"):
        parent = os.path.dirname(source_path)
        name = os.path.splitext(os.path.basename(source_path))[0]
        self.output_dir = os.path.join(parent, name + suffix)
        self.out_label.configure(text=self.output_dir)

    def _open_settings(self):
        SettingsWindow(self, self.config_data, on_save=self._on_settings_saved)

    def _on_settings_saved(self, new_config: dict):
        self.config_data = new_config
        self._log("[Config] Settings saved.")
        self.stat_cache.configure(
            text=f"Cache: {self._make_translator().memory.size()} entries"
        )

    def _on_engine_change(self, value: str):
        self._log(f"[Engine] Selected: {value}")

    def _cancel(self):
        if self._running:
            self._translator_obj.cancel()
            self._log("[Cancel] Cancellation requested…")

    # ── Translation controls ─────────────────────────────────────────────────

    def _run_extract(self):
        if not self._check_project():
            return
        self._start_thread(self._do_extract)

    def _run_translate(self):
        if not self.segments:
            messagebox.showinfo("Extract first", "Please run 'Extract Text' first.")
            return
        self._start_thread(self._do_translate)

    def _run_apply(self):
        if not self.translations:
            messagebox.showinfo("Translate first", "Please run 'Translate' first.")
            return
        self._start_thread(self._do_apply)

    def _run_full(self):
        if not self._check_project():
            return
        self._start_thread(self._do_full)

    def _start_thread(self, fn):
        if self._running:
            messagebox.showwarning("Busy", "A translation job is already running.")
            return
        self._running = True
        self.cancel_btn.configure(state="normal")
        threading.Thread(target=fn, daemon=True).start()

    def _finish_thread(self):
        self._running = False
        self.cancel_btn.configure(state="disabled")

    # ── Worker functions (run in threads) ────────────────────────────────────

    def _do_extract(self):
        try:
            t = self._make_translator()
            self._set_status("Extracting text…")
            self.segments = t.extract(self.project_dir)
            n = len(self.segments)
            self._log(f"[Extract] ✓ Found {n} segments.")
            self._update_stats()
            self._set_status(f"Extracted {n} segments.")
            self._set_progress(1.0, f"Done — {n} segments")
        except Exception as e:
            self._log(f"[Extract] Error: {e}")
            self._set_status("Extract failed.")
        finally:
            self._finish_thread()

    def _do_translate(self):
        try:
            t = self._make_translator()
            engine = self._make_engine()
            if engine is None:
                return
            lang = self.lang_var.get()
            self._set_status(f"Translating to {lang}…")
            self.translations = t.translate(self.segments, engine, lang)
            n = len(self.translations)
            self._log(f"[Translate] ✓ {n} translations produced.")
            self._update_stats()
            self._set_status(f"Translated {n}/{len(self.segments)} segments.")
        except Exception as e:
            self._log(f"[Translate] Error: {e}")
            self._set_status("Translation failed.")
        finally:
            self._finish_thread()

    def _do_apply(self):
        try:
            t = self._make_translator()
            self._set_status("Applying translations…")
            count = t.apply(
                self.segments, self.translations,
                self.project_dir, self.output_dir,
            )
            self._log(f"[Apply] ✓ Modified {count} lines → {self.output_dir}")
            self._set_status(f"Done! Output: {self.output_dir}")
            self._set_progress(1.0, "Applied!")
            self.after(0, lambda: messagebox.showinfo(
                "Done",
                f"Translation applied!\n\nModified {count} lines.\nOutput: {self.output_dir}"
            ))
        except Exception as e:
            self._log(f"[Apply] Error: {e}")
            self._set_status("Apply failed.")
        finally:
            self._finish_thread()

    def _do_full(self):
        try:
            t = self._make_translator()
            engine = self._make_engine()
            if engine is None:
                return
            lang = self.lang_var.get()
            self._set_status("Running full pipeline…")

            # Extract
            self._log("[Pipeline] Step 1/3: Extracting…")
            self._set_progress(0, "Extracting…")
            self.segments = t.extract(self.project_dir)
            self._update_stats()
            n = len(self.segments)
            self._log(f"[Pipeline] Found {n} segments.")

            if not self.segments:
                self._log("[Pipeline] No text found.")
                self._set_status("No translatable text found.")
                return

            # Translate
            self._log(f"[Pipeline] Step 2/3: Translating to {lang}…")
            self.translations = t.translate(self.segments, engine, lang)
            self._update_stats()

            # Apply
            self._log("[Pipeline] Step 3/3: Applying translations…")
            self._set_progress(0.95, "Applying…")
            count = t.apply(
                self.segments, self.translations,
                self.project_dir, self.output_dir,
            )
            self._set_progress(1.0, "✓ Complete!")
            self._log(f"[Pipeline] ✓ Done! {count} lines modified.")
            self._set_status(f"✓ Complete! Output: {self.output_dir}")
            self.after(0, lambda: messagebox.showinfo(
                "Translation Complete",
                f"✓ Translation finished!\n\n"
                f"Segments found: {n}\n"
                f"Translations applied: {count}\n"
                f"Output folder: {self.output_dir}"
            ))
        except Exception as e:
            import traceback
            self._log(f"[Pipeline] Fatal: {e}")
            self._log(traceback.format_exc())
            self._set_status("Pipeline failed — see logs.")
        finally:
            self._finish_thread()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _check_project(self) -> bool:
        if not self.project_dir:
            messagebox.showwarning("No Project", "Please select a project folder or ZIP first.")
            return False
        if not os.path.isdir(self.project_dir):
            messagebox.showerror("Not Found", f"Project directory not found:\n{self.project_dir}")
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
        engine_name = self.engine_var.get()
        try:
            engine = get_engine(engine_name, self.config_data)
        except Exception as e:
            self._log(f"[Engine] Load error: {e}")
            messagebox.showerror("Engine Error", str(e))
            self._finish_thread()
            return None

        if not engine.is_available:
            if engine.requires_api_key:
                self.after(0, lambda: messagebox.showwarning(
                    "API Key Required",
                    f"{engine_name} requires an API key.\n"
                    "Please open Settings and add your key."
                ))
            else:
                self.after(0, lambda: messagebox.showwarning(
                    "Engine Unavailable",
                    f"{engine_name} is not available.\n"
                    "Make sure the required package is installed."
                ))
            self._finish_thread()
            return None
        return engine

    def _on_progress(self, current: int, total: int):
        if total > 0:
            frac = current / total
            self._set_progress(frac, f"{current}/{total}")

    def _set_progress(self, value: float, label: str = ""):
        self.after(0, lambda: self.progress_bar.set(min(max(value, 0), 1)))
        if label:
            self.after(0, lambda: self.progress_label.configure(
                text=f"Progress: {label}"
            ))

    def _set_status(self, text: str):
        self.after(0, lambda: self.status_var.set(text))

    def _update_stats(self):
        def _do():
            segs = len(self.segments)
            trans = len(self.translations)
            cache_size = 0
            try:
                cache_size = self._translator_obj.memory.size()
            except Exception:
                pass
            self.stat_segs.configure(text=f"Segments: {segs}")
            self.stat_trans.configure(text=f"Translated: {trans}")
            self.stat_cache.configure(text=f"Cache: {cache_size} entries")
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

    def _cleanup_temp(self):
        if self.temp_dir:
            cleanup_temp(self.temp_dir)
            self.temp_dir = ""

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno("Quit", "Translation is running. Quit anyway?"):
                return
        self._cleanup_temp()
        self.destroy()
