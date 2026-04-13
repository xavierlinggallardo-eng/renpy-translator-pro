"""
Google Gemini API engine (free tier available).
Requires: pip install google-generativeai
"""

import time
import re
from typing import List, Optional
from .base import TranslationEngine, protect_tokens, restore_tokens


SYSTEM_PROMPT = (
    "You are a professional translator for visual novel games. "
    "Translate only the text provided. "
    "Preserve ALL formatting tokens exactly as-is: "
    "{variables}, [player_name], %s, %d, \\n, \\t, {p}, {w}, <tags>. "
    "Do NOT add explanations, notes, or alternative translations. "
    "Output ONLY the translated text."
)

TRANSLATION_PROMPT_TEMPLATE = (
    "Translate the following text to {target_lang}. "
    "Preserve formatting, variables, and special tokens exactly. "
    "Do not add explanations.\n\n"
    "Text:\n{text}"
)

BATCH_PROMPT_TEMPLATE = (
    "Translate each of the following lines to {target_lang}. "
    "Preserve formatting, variables, and special tokens exactly. "
    "Output ONLY the translations, one per line, in the same order. "
    "Do not add explanations, numbering, or extra text.\n\n"
    "{numbered_lines}"
)


class GeminiEngine(TranslationEngine):

    name = "Google Gemini"
    requires_api_key = True
    BATCH_SIZE = 30
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 3.0

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("gemini_api_key", "")
        self._model = None
        self._init_model()

    def _init_model(self):
        if not self.api_key:
            self._model = None
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                system_instruction=SYSTEM_PROMPT,
            )
        except Exception:
            self._model = None

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self._model is not None)

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

            translated = self._translate_batch_with_retry(protected_batch, target_lang)

            for j, (trans, toks) in enumerate(zip(translated, token_list)):
                idx = batch_start + j
                results[idx] = restore_tokens(trans, toks) if trans else None

        return results

    def _translate_batch_with_retry(
        self, texts: List[str], target_lang: str
    ) -> List[Optional[str]]:
        for attempt in range(self.RETRY_ATTEMPTS):
            try:
                return self._translate_batch_api(texts, target_lang)
            except Exception as e:
                err = str(e)
                # Rate limit
                if "429" in err or "quota" in err.lower():
                    wait = self.RETRY_DELAY * (attempt + 1) * 2
                    time.sleep(wait)
                elif attempt < self.RETRY_ATTEMPTS - 1:
                    time.sleep(self.RETRY_DELAY)
        return [None] * len(texts)

    def _translate_batch_api(
        self, texts: List[str], target_lang: str
    ) -> List[Optional[str]]:
        import google.generativeai as genai

        if len(texts) == 1:
            # Single text — simpler prompt
            prompt = TRANSLATION_PROMPT_TEMPLATE.format(
                target_lang=target_lang, text=texts[0]
            )
            response = self._model.generate_content(prompt)
            return [response.text.strip() if response.text else None]

        # Batch: number lines
        numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
        prompt = BATCH_PROMPT_TEMPLATE.format(
            target_lang=target_lang, numbered_lines=numbered
        )
        response = self._model.generate_content(prompt)
        raw = response.text.strip() if response.text else ""
        lines = raw.split("\n")

        # Strip leading numbers if model re-numbered
        parsed = []
        for line in lines:
            line = line.strip()
            line = re.sub(r'^\d+\.\s*', '', line)
            parsed.append(line)

        # Pad or trim to match input count
        while len(parsed) < len(texts):
            parsed.append(None)
        return parsed[:len(texts)]
