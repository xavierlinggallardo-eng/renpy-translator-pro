"""
OpenAI engine (GPT-3.5/GPT-4). Optional, paid.
Requires: pip install openai
"""

import time
import re
from typing import List, Optional
from .base import TranslationEngine, protect_tokens, restore_tokens


SYSTEM_MSG = (
    "You are a professional translator for visual novel games. "
    "Preserve ALL tokens: {variables}, [player_name], %s, \\n, {p}, {w}. "
    "Output ONLY the translated text with no explanations."
)

BATCH_PROMPT = (
    "Translate each line to {target_lang}. "
    "Output ONLY the translations, one per line, same order. No numbering.\n\n"
    "{lines}"
)


class OpenAIEngine(TranslationEngine):

    name = "OpenAI GPT"
    requires_api_key = True
    BATCH_SIZE = 40
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 2.0

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("openai_api_key", "")
        self.model = config.get("openai_model", "gpt-3.5-turbo")
        self._client = None
        self._init_client()

    def _init_client(self):
        if not self.api_key:
            return
        try:
            import openai
            self._client = openai.OpenAI(api_key=self.api_key)
        except Exception:
            self._client = None

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self._client is not None)

    def translate_batch(self, texts: List[str], target_lang: str) -> List[Optional[str]]:
        if not self.is_available:
            return [None] * len(texts)

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
                    translated = self._call_api(protected_batch, target_lang)
                    for j, (trans, toks) in enumerate(zip(translated, token_list)):
                        idx = batch_start + j
                        results[idx] = restore_tokens(trans, toks) if trans else None
                    break
                except Exception:
                    if attempt < self.RETRY_ATTEMPTS - 1:
                        time.sleep(self.RETRY_DELAY)

        return results

    def _call_api(self, texts: List[str], target_lang: str) -> List[Optional[str]]:
        prompt = BATCH_PROMPT.format(
            target_lang=target_lang,
            lines="\n".join(texts)
        )
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        raw = resp.choices[0].message.content.strip()
        lines = raw.split("\n")
        lines = [re.sub(r'^\d+\.\s*', '', l.strip()) for l in lines]
        while len(lines) < len(texts):
            lines.append(None)
        return lines[:len(texts)]
