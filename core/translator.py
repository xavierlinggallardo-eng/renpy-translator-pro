"""
Main translation orchestrator.
Ties together parser, engine, memory cache, and reinserter.
"""

import os
import threading
from typing import List, Dict, Callable, Optional

from .parser import RenpyParser, Segment
from .memory import TranslationMemory
from .reinserter import reinsert


class TranslationJob:
    """Holds state for a single translation run."""

    def __init__(self):
        self.segments: List[Segment] = []
        self.translations: Dict[int, str] = {}   # line_no -> translated text
        self.project_dir: str = ""
        self.output_dir: str = ""
        self.target_lang: str = ""
        self.engine_name: str = ""

    @property
    def total(self) -> int:
        return len(self.segments)

    @property
    def translated_count(self) -> int:
        return sum(1 for v in self.translations.values() if v)


class Translator:
    """Orchestrates extract → translate → reinsert pipeline."""

    BATCH_SIZE = 50

    def __init__(
        self,
        config: dict,
        log_callback: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
    ):
        self.config = config
        self.log = log_callback or (lambda m: None)
        self.progress = progress_callback or (lambda current, total: None)
        cache_path = config.get("cache_path", "cache.json")
        # Make cache relative to config dir
        if not os.path.isabs(cache_path):
            try:
                from utils.config import get_config_path
            except ImportError:
                import sys
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                from utils.config import get_config_path
            cfg_dir = os.path.dirname(get_config_path())
            cache_path = os.path.join(cfg_dir, cache_path)
        self.memory = TranslationMemory(cache_path)
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def reset_cancel(self):
        self._cancel_event.clear()

    # ── STEP 1: Extract ──────────────────────────────────────────────────────

    def extract(self, project_dir: str) -> List[Segment]:
        self.log(f"[Extract] Scanning: {project_dir}")
        parser = RenpyParser(log_callback=self.log)
        segments = parser.parse_project(project_dir)
        self.log(f"[Extract] Total segments: {len(segments)}")
        return segments

    # ── STEP 2: Translate ────────────────────────────────────────────────────

    def translate(
        self,
        segments: List[Segment],
        engine,
        target_lang: str,
    ) -> Dict[int, str]:
        """
        Translate all segments using the given engine.
        Returns dict: line_no -> translated_text.
        """
        self.reset_cancel()
        translations: Dict[int, str] = {}
        engine_name = engine.name

        # De-duplicate texts (many segments may share text)
        unique_texts: Dict[str, List[int]] = {}  # text -> [line_nos]
        for seg in segments:
            unique_texts.setdefault(seg.text, []).append(seg.line)

        # Check cache first
        all_texts = list(unique_texts.keys())
        cache_results = self.memory.bulk_get(all_texts, target_lang, engine_name)

        texts_to_translate: List[str] = []
        for text in all_texts:
            cached = cache_results.get(text)
            if cached is not None:
                for line_no in unique_texts[text]:
                    translations[line_no] = cached
            else:
                texts_to_translate.append(text)

        cache_hits = len(all_texts) - len(texts_to_translate)
        self.log(f"[Translate] Cache hits: {cache_hits}/{len(all_texts)}")
        self.log(f"[Translate] Segments to translate: {len(texts_to_translate)}")

        # Translate in batches
        total = len(texts_to_translate)
        done = 0

        for batch_start in range(0, total, self.BATCH_SIZE):
            if self._cancel_event.is_set():
                self.log("[Translate] Cancelled.")
                break

            batch = texts_to_translate[batch_start: batch_start + self.BATCH_SIZE]
            try:
                results = engine.translate_batch(batch, target_lang)
            except Exception as e:
                self.log(f"[Translate] Engine error: {e}")
                results = [None] * len(batch)

            new_pairs: Dict[str, str] = {}
            for text, result in zip(batch, results):
                if result:
                    new_pairs[text] = result
                    for line_no in unique_texts[text]:
                        translations[line_no] = result
                else:
                    self.log(f"[Translate] Failed: {text[:60]!r}")

            if new_pairs:
                self.memory.bulk_set(new_pairs, target_lang, engine_name)

            done += len(batch)
            self.progress(cache_hits + done, len(all_texts))
            self.log(
                f"[Translate] {cache_hits + done}/{len(all_texts)} "
                f"({(cache_hits + done)/max(len(all_texts),1)*100:.1f}%)"
            )

        translated_count = sum(1 for v in translations.values() if v)
        failed_count = len(all_texts) - translated_count
        if failed_count > 0:
            self.log(f"[Translate] ⚠ {failed_count} segmentos sin traducir.")
            if translated_count == 0:
                self.log("[Translate] ⚠ NINGÚN segmento fue traducido.")
                self.log("[Translate] Verifica que el motor esté bien configurado.")
                self.log("[Translate] Para Argos: el pack de idioma debe estar instalado.")
                self.log("[Translate] Para Gemini/OpenAI: verifica tu API key en Ajustes.")
        self.log(
            f"[Translate] Listo: {translated_count}/{len(all_texts)} únicos traducidos."
        )
        return translations

    # ── STEP 3: Reinsert ─────────────────────────────────────────────────────

    def apply(
        self,
        segments: List[Segment],
        translations: Dict[int, str],
        project_dir: str,
        output_dir: str,
    ) -> int:
        self.log(f"[Apply] Writing to: {output_dir}")
        count = reinsert(
            segments=segments,
            translations=translations,
            project_dir=project_dir,
            output_dir=output_dir,
            log_callback=self.log,
        )
        self.log(f"[Apply] Modified {count} lines.")
        return count

    # ── Full pipeline ────────────────────────────────────────────────────────

    def run_full(
        self,
        project_dir: str,
        output_dir: str,
        engine,
        target_lang: str,
    ) -> bool:
        try:
            segments = self.extract(project_dir)
            if not segments:
                self.log("[Pipeline] No translatable text found.")
                return False

            translations = self.translate(segments, engine, target_lang)
            if not translations:
                self.log("[Pipeline] No translations produced.")
                return False

            self.apply(segments, translations, project_dir, output_dir)
            self.log("[Pipeline] ✓ Complete!")
            return True

        except Exception as e:
            self.log(f"[Pipeline] Fatal error: {e}")
            import traceback
            self.log(traceback.format_exc())
            return False
