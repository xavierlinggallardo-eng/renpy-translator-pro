"""
DeepL engine (free tier via unofficial API wrapper or official API).
Requires: pip install deepl
"""

import time
from typing import List, Optional
from .base import TranslationEngine, protect_tokens, restore_tokens


class DeepLEngine(TranslationEngine):

    name = "DeepL"
    requires_api_key = True
    BATCH_SIZE = 50
    RETRY_ATTEMPTS = 3

    _LANG_MAP = {
        "Spanish": "ES", "French": "FR", "German": "DE", "Italian": "IT",
        "Portuguese": "PT-PT", "Russian": "RU", "Japanese": "JA",
        "Chinese": "ZH", "Korean": "KO", "Dutch": "NL", "Polish": "PL",
        "Turkish": "TR", "Swedish": "SV", "Danish": "DA", "Finnish": "FI",
        "Hungarian": "HU", "Romanian": "RO", "Ukrainian": "UK",
        "Czech": "CS", "Greek": "EL", "Bulgarian": "BG", "Indonesian": "ID",
        "es": "ES", "fr": "FR", "de": "DE", "it": "IT", "pt": "PT-PT",
        "ru": "RU", "ja": "JA", "zh": "ZH", "ko": "KO", "nl": "NL",
        "pl": "PL", "tr": "TR", "sv": "SV", "uk": "UK", "cs": "CS",
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("deepl_api_key", "")
        self._translator = None
        self._init()

    def _init(self):
        if not self.api_key:
            return
        try:
            import deepl
            self._translator = deepl.Translator(self.api_key)
        except Exception:
            self._translator = None

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self._translator is not None)

    def _resolve_lang(self, lang: str) -> str:
        return self._LANG_MAP.get(lang, lang.upper())

    def translate_batch(self, texts: List[str], target_lang: str) -> List[Optional[str]]:
        if not self.is_available:
            return [None] * len(texts)

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
                    translated_results = self._translator.translate_text(
                        protected_batch,
                        target_lang=tgt,
                        source_lang="EN",
                    )
                    for j, (res, toks) in enumerate(zip(translated_results, token_list)):
                        idx = batch_start + j
                        results[idx] = restore_tokens(res.text, toks)
                    break
                except Exception:
                    if attempt < self.RETRY_ATTEMPTS - 1:
                        time.sleep(2)

        return results
