"""
Translation memory / cache backed by a JSON file.
Avoids re-translating identical strings.
"""

import json
import os
import hashlib
import threading
from typing import Optional, Dict


class TranslationMemory:
    """Thread-safe translation cache."""

    def __init__(self, cache_path: str = "cache.json"):
        self.cache_path = cache_path
        self._lock = threading.Lock()
        self._data: Dict[str, str] = {}
        self._load()

    # ── key derivation ───────────────────────────────────────────────────────

    @staticmethod
    def make_key(text: str, target_lang: str, engine: str) -> str:
        raw = f"{engine}|{target_lang}|{text}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    # ── public API ───────────────────────────────────────────────────────────

    def get(self, text: str, target_lang: str, engine: str) -> Optional[str]:
        key = self.make_key(text, target_lang, engine)
        with self._lock:
            return self._data.get(key)

    def set(self, text: str, target_lang: str, engine: str, translation: str) -> None:
        key = self.make_key(text, target_lang, engine)
        with self._lock:
            self._data[key] = translation
        self._save()

    def bulk_get(self, texts: list, target_lang: str, engine: str) -> Dict[str, Optional[str]]:
        result = {}
        with self._lock:
            for t in texts:
                key = self.make_key(t, target_lang, engine)
                result[t] = self._data.get(key)
        return result

    def bulk_set(self, pairs: Dict[str, str], target_lang: str, engine: str) -> None:
        with self._lock:
            for text, translation in pairs.items():
                key = self.make_key(text, target_lang, engine)
                self._data[key] = translation
        self._save()

    def size(self) -> int:
        with self._lock:
            return len(self._data)

    def clear(self) -> None:
        with self._lock:
            self._data = {}
        self._save()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        try:
            with self._lock:
                data_copy = dict(self._data)
            os.makedirs(os.path.dirname(os.path.abspath(self.cache_path)), exist_ok=True)
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(data_copy, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
