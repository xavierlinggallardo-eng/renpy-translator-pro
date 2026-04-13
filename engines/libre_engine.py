"""
LibreTranslate engine.
Can use the public API (https://libretranslate.com) or a self-hosted instance.
Free with rate limits on public API; unlimited if self-hosted.
"""

import time
import requests
from typing import List, Optional
from .base import TranslationEngine, protect_tokens, restore_tokens


class LibreTranslateEngine(TranslationEngine):

    name = "LibreTranslate"
    requires_api_key = False

    DEFAULT_URL = "https://libretranslate.com"
    BATCH_SIZE = 20
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 2.0

    _LANG_MAP = {
        "Spanish": "es", "French": "fr", "German": "de", "Italian": "it",
        "Portuguese": "pt", "Russian": "ru", "Japanese": "ja", "Chinese": "zh",
        "Korean": "ko", "Arabic": "ar", "Dutch": "nl", "Polish": "pl",
        "Turkish": "tr", "Hindi": "hi", "Vietnamese": "vi", "Indonesian": "id",
        "Thai": "th", "Czech": "cs", "Swedish": "sv",
        "en": "en", "es": "es", "fr": "fr", "de": "de", "it": "it",
        "pt": "pt", "ru": "ru", "ja": "ja", "zh": "zh", "ko": "ko",
        "ar": "ar", "nl": "nl", "pl": "pl", "tr": "tr", "uk": "uk",
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config.get("libre_url", self.DEFAULT_URL).rstrip("/")
        self.api_key = config.get("libre_api_key", "")

    @property
    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/languages", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def _resolve_lang(self, lang: str) -> str:
        return self._LANG_MAP.get(lang, lang.lower()[:2])

    def translate_batch(self, texts: List[str], target_lang: str) -> List[Optional[str]]:
        tgt = self._resolve_lang(target_lang)
        results: List[Optional[str]] = [None] * len(texts)

        for batch_start in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[batch_start: batch_start + self.BATCH_SIZE]
            protected_batch = []
            token_list = []
            for t in batch:
                p, toks = protect_tokens(t)
                protected_batch.append(p)
                token_list.append(toks)

            for attempt in range(self.RETRY_ATTEMPTS):
                try:
                    translated = self._call_api(protected_batch, tgt)
                    if translated:
                        for j, (trans, toks) in enumerate(zip(translated, token_list)):
                            idx = batch_start + j
                            results[idx] = restore_tokens(trans, toks) if trans else None
                        break
                except Exception as e:
                    if attempt < self.RETRY_ATTEMPTS - 1:
                        time.sleep(self.RETRY_DELAY)

        return results

    def _call_api(self, texts: List[str], target_lang: str) -> Optional[List[str]]:
        results = []
        for text in texts:
            payload = {
                "q": text,
                "source": "en",
                "target": target_lang,
                "format": "text",
            }
            if self.api_key:
                payload["api_key"] = self.api_key

            r = requests.post(
                f"{self.base_url}/translate",
                json=payload,
                timeout=30,
            )
            if r.status_code == 200:
                data = r.json()
                results.append(data.get("translatedText", ""))
            else:
                results.append(None)
        return results
