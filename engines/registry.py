"""Engine registry — maps display names to engine classes."""

from .argos_engine import ArgosEngine
from .libre_engine import LibreTranslateEngine
from .gemini_engine import GeminiEngine
from .openai_engine import OpenAIEngine
from .deepl_engine import DeepLEngine

ENGINE_CLASSES = {
    "Argos Translate (Offline)": ArgosEngine,
    "LibreTranslate": LibreTranslateEngine,
    "Google Gemini": GeminiEngine,
    "OpenAI GPT": OpenAIEngine,
    "DeepL": DeepLEngine,
}

ENGINE_NAMES = list(ENGINE_CLASSES.keys())


def get_engine(name: str, config: dict):
    cls = ENGINE_CLASSES.get(name)
    if cls is None:
        raise ValueError(f"Unknown engine: {name}")
    return cls(config)
