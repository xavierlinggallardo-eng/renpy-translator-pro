"""Base class for all translation engines."""

import re
from abc import ABC, abstractmethod
from typing import List, Optional


# ── token preservation ───────────────────────────────────────────────────────

# Matches {variable}, [name], %s, %d, \n, \t, {p}, {w}, etc.
_TOKEN_RE = re.compile(
    r'(\{[^}]*\}|\[[^\]]*\]|%[sdifg]|\\[ntr]|<[^>]+>)'
)


def protect_tokens(text: str) -> tuple[str, list]:
    """Replace special tokens with placeholders, return (protected_text, token_list)."""
    tokens = []
    def replacer(m):
        tokens.append(m.group(0))
        return f"__TOK{len(tokens)-1}__"
    protected = _TOKEN_RE.sub(replacer, text)
    return protected, tokens


def restore_tokens(text: str, tokens: list) -> str:
    """Restore placeholders back to original tokens."""
    for i, tok in enumerate(tokens):
        text = text.replace(f"__TOK{i}__", tok)
    return text


# ── base engine ──────────────────────────────────────────────────────────────

class TranslationEngine(ABC):

    name: str = "base"
    requires_api_key: bool = False

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def translate_batch(self, texts: List[str], target_lang: str) -> List[Optional[str]]:
        """
        Translate a list of texts to target_lang.
        Returns a list of the same length; None entries mean failure.
        """
        ...

    def translate(self, text: str, target_lang: str) -> Optional[str]:
        results = self.translate_batch([text], target_lang)
        return results[0] if results else None

    @property
    def is_available(self) -> bool:
        """Check if this engine can be used (dependencies installed, key set, etc.)."""
        return True

    def _safe_translate_text(self, text: str, target_lang: str) -> Optional[str]:
        """Translate a single string with token protection."""
        protected, tokens = protect_tokens(text)
        try:
            results = self.translate_batch([protected], target_lang)
            result = results[0] if results else None
            if result is None:
                return None
            return restore_tokens(result, tokens)
        except Exception:
            return None
