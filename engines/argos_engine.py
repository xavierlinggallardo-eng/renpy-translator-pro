"""
Argos Translate engine (fully offline, free).
Requires: pip install argostranslate
"""

from typing import List, Optional
from .base import TranslationEngine, protect_tokens, restore_tokens


class ArgosEngine(TranslationEngine):

    name = "Argos Translate (Offline)"
    requires_api_key = False

    # Map common language names/codes to argos language codes
    _LANG_MAP = {
        "Spanish": "es", "French": "fr", "German": "de", "Italian": "it",
        "Portuguese": "pt", "Russian": "ru", "Japanese": "ja", "Chinese": "zh",
        "Korean": "ko", "Arabic": "ar", "Dutch": "nl", "Polish": "pl",
        "Turkish": "tr", "Hindi": "hi", "Vietnamese": "vi", "Indonesian": "id",
        "Thai": "th", "Czech": "cs", "Swedish": "sv", "Danish": "da",
        "Finnish": "fi", "Hungarian": "hu", "Romanian": "ro", "Ukrainian": "uk",
        "Greek": "el", "Bulgarian": "bg", "Croatian": "hr", "Slovak": "sk",
        "Slovenian": "sl", "Estonian": "et", "Latvian": "lv", "Lithuanian": "lt",
        "en": "en", "es": "es", "fr": "fr", "de": "de", "it": "it",
        "pt": "pt", "ru": "ru", "ja": "ja", "zh": "zh", "ko": "ko",
        "ar": "ar", "nl": "nl", "pl": "pl", "tr": "tr", "hi": "hi",
        "vi": "vi", "id": "id", "th": "th", "cs": "cs", "sv": "sv",
        "uk": "uk", "el": "el",
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self._translate_fn = None
        self._init_argos()

    def _init_argos(self):
        try:
            from argostranslate import package, translate
            self._translate_fn = translate.translate
            self._available = True
        except ImportError:
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def _resolve_lang(self, lang: str) -> str:
        return self._LANG_MAP.get(lang, lang.lower()[:2])

    def translate_batch(self, texts: List[str], target_lang: str) -> List[Optional[str]]:
        if not self._available or self._translate_fn is None:
            return [None] * len(texts)

        tgt = self._resolve_lang(target_lang)
        results = []
        for text in texts:
            protected, tokens = protect_tokens(text)
            try:
                translated = self._translate_fn(protected, "en", tgt)
                results.append(restore_tokens(translated, tokens))
            except Exception:
                results.append(None)
        return results

    def ensure_language_pack(self, target_lang: str, log=None):
        """Download and install language pack if not present."""
        try:
            from argostranslate import package, translate
            tgt = self._resolve_lang(target_lang)
            installed = {p.to_code for p in translate.get_installed_languages()
                         if hasattr(p, 'to_code')}
            if tgt in installed:
                if log:
                    log(f"[Argos] Language pack for '{tgt}' already installed.")
                return True

            if log:
                log(f"[Argos] Downloading language pack: en→{tgt}...")
            package.update_package_index()
            available = package.get_available_packages()
            pkgs = [p for p in available
                    if p.from_code == "en" and p.to_code == tgt]
            if not pkgs:
                if log:
                    log(f"[Argos] No package found for en→{tgt}")
                return False
            pkgs[0].install()
            if log:
                log(f"[Argos] Installed en→{tgt} successfully.")
            return True
        except Exception as e:
            if log:
                log(f"[Argos] Pack install error: {e}")
            return False
