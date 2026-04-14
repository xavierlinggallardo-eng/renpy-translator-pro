"""
Argos Translate engine (offline, gratis).
Detecta automáticamente si el pack de idioma está instalado y lo descarga si no.
"""

from typing import List, Optional
from .base import TranslationEngine, protect_tokens, restore_tokens


class ArgosEngine(TranslationEngine):

    name = "Argos Translate (Offline)"
    requires_api_key = False

    _LANG_MAP = {
        "Spanish": "es", "French": "fr", "German": "de", "Italian": "it",
        "Portuguese": "pt", "Russian": "ru", "Japanese": "ja", "Chinese": "zh",
        "Korean": "ko", "Arabic": "ar", "Dutch": "nl", "Polish": "pl",
        "Turkish": "tr", "Hindi": "hi", "Vietnamese": "vi", "Indonesian": "id",
        "Thai": "th", "Czech": "cs", "Swedish": "sv", "Ukrainian": "uk",
        "Greek": "el", "Romanian": "ro", "Danish": "da", "Finnish": "fi",
        "Hungarian": "hu", "Bulgarian": "bg",
        "es": "es", "fr": "fr", "de": "de", "it": "it", "pt": "pt",
        "ru": "ru", "ja": "ja", "zh": "zh", "ko": "ko", "ar": "ar",
        "nl": "nl", "pl": "pl", "tr": "tr", "uk": "uk", "el": "el",
        "cs": "cs", "sv": "sv", "hi": "hi", "vi": "vi", "id": "id",
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self._available = False
        self._translate_fn = None
        self._loaded_pair = None  # (from, to) pair that's confirmed working
        self._init()

    def _init(self):
        try:
            import argostranslate.translate  # noqa
            self._available = True
        except ImportError:
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def _resolve_lang(self, lang: str) -> str:
        return self._LANG_MAP.get(lang, lang.lower()[:2])

    def _get_translate_fn(self, tgt: str):
        """Obtiene la función de traducción verificando que el par en→tgt esté instalado."""
        pair_key = ("en", tgt)
        if self._loaded_pair == pair_key and self._translate_fn is not None:
            return self._translate_fn

        try:
            from argostranslate import translate
            installed = translate.get_installed_languages()
            from_lang = next((l for l in installed if l.code == "en"), None)
            if from_lang is None:
                return None
            to_lang = next((t for t in from_lang.translations_to if t.code == tgt), None)
            if to_lang is None:
                return None
            fn = from_lang.get_translation(to_lang)
            if fn is None:
                return None
            # Verificar con una cadena de prueba
            test = fn.translate("hello")
            if not test or test == "hello":
                # pack no funciona bien
                return None
            self._translate_fn = fn.translate
            self._loaded_pair = pair_key
            return self._translate_fn
        except Exception:
            return None

    def ensure_language_pack(self, target_lang: str, log=None) -> bool:
        """Descarga e instala el pack de idioma si no está disponible."""
        if not self._available:
            if log:
                log("[Argos] argostranslate no está instalado. Ejecuta: pip install argostranslate")
            return False

        tgt = self._resolve_lang(target_lang)

        # Comprobar si ya funciona
        fn = self._get_translate_fn(tgt)
        if fn is not None:
            if log:
                log(f"[Argos] Pack en→{tgt} ya está instalado y funcional.")
            return True

        if log:
            log(f"[Argos] Descargando pack en→{tgt} (puede tardar unos minutos)...")
        try:
            from argostranslate import package, translate
            package.update_package_index()
            available = package.get_available_packages()
            pkgs = [p for p in available if p.from_code == "en" and p.to_code == tgt]
            if not pkgs:
                if log:
                    log(f"[Argos] ⚠ No hay pack disponible para en→{tgt}")
                    log("[Argos] Prueba con LibreTranslate o Google Gemini en su lugar.")
                return False
            if log:
                log(f"[Argos] Instalando pack en→{tgt} ({pkgs[0].package_version})...")
            pkgs[0].install()
            # Verificar que funciona
            fn = self._get_translate_fn(tgt)
            if fn:
                if log:
                    log(f"[Argos] ✓ Pack en→{tgt} instalado y verificado.")
                return True
            else:
                if log:
                    log(f"[Argos] ⚠ Pack instalado pero no funciona. Intenta reiniciar.")
                return False
        except Exception as e:
            if log:
                log(f"[Argos] Error descargando pack: {e}")
            return False

    def translate_batch(self, texts: List[str], target_lang: str) -> List[Optional[str]]:
        if not self._available:
            return [None] * len(texts)

        tgt = self._resolve_lang(target_lang)
        fn = self._get_translate_fn(tgt)

        if fn is None:
            # Pack no instalado — intentar instalar en segundo plano no es posible aquí
            # Retornar None con indicador especial
            return [None] * len(texts)

        results = []
        for text in texts:
            if not text or not text.strip():
                results.append(text)
                continue
            protected, tokens = protect_tokens(text)
            try:
                translated = fn(protected)
                if translated and translated != protected:
                    results.append(restore_tokens(translated, tokens))
                else:
                    results.append(None)
            except Exception:
                results.append(None)
        return results
